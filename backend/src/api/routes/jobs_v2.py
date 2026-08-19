"""
jobs_v2.py — Job lifecycle API routes  (API version: v2)
==========================================================
Public API prefix: /api/v2/jobs

NOTE on versioning naming:
  - This file is "v2" because it is the second PUBLIC API version (v1 was the
    in-memory prototype, now deleted). The frontend calls /api/v2/jobs/*.
  - Internally, extraction uses ExtractionPipeline (see extraction_pipeline.py),
    which orchestrates StructuralParsingService + MarkdownExtractionService.
    That is separate from the older PDFPipelineV3 in src/core/pipeline.py, which
    is the THIRD internal iteration of the V1 PDF parsing core (unrelated to the
    public API version number). We intentionally kept the API version and internal
    pipeline version numbers separate to avoid confusion when one evolves faster
    than the other.

Endpoints:
  POST   /jobs                  — create a new job
  PATCH  /jobs/{id}             — update JD config
  POST   /jobs/{id}/resumes     — upload resume PDFs
  GET    /jobs/{id}/extract     — SSE stream real extraction progress
  POST   /jobs/{id}/score       — score & rank candidates
  GET    /jobs/{id}/results     — retrieve stored scoring results

Persistence: DynamoDB (ResumePlatform single table) + S3 (resume-ranker bucket).
Replaces the previous in-memory _jobs dict.
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile, BackgroundTasks, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, field_validator

from src.services.extraction_service import ExtractionService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

# ── Infrastructure imports ────────────────────────────────────────────────────
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.storage.storage_service import StorageService

logger = logging.getLogger(__name__)

# ── Phase 6: Bounded Concurrency ──────────────────────────────────────────────
# MAX_CONCURRENT_EXTRACTIONS caps simultaneous asyncio.to_thread calls so a
# large upload (e.g. 500 PDFs) cannot spawn 500 OS threads and OOM the process.
# Default of 8 matches the benchmark's existing 8-thread pattern
# (tests/benchmark_v4/main.py).  Tune via env var without a code deploy.
#
# The semaphore is created lazily on the first extraction call because
# asyncio.Semaphore must be bound to the running event loop — creating it at
# module-import time (before uvicorn starts the loop) raises a DeprecationWarning
# in Python 3.10+ and a RuntimeError in 3.12+.
_MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_EXTRACTIONS", "8"))
_extraction_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Return the module-level semaphore, creating it on first call."""
    global _extraction_semaphore
    if _extraction_semaphore is None:
        _extraction_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _extraction_semaphore

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    title: str
    department: str = ""
    description: str = ""
    must_have_skills: List[str] = []
    nice_to_have_skills: List[str] = []
    min_years: int = 0
    max_years: int = 99
    education_level: str = "any"
    education_field: str = ""
    keywords: List[str] = []


class CreateJobResponse(BaseModel):
    id: str
    title: str
    status: str  # "created"


class UpdateJobRequest(BaseModel):
    """Partial update for a job's JD config.

    All fields are optional — only supplied fields are merged into
    the stored config.  This is called by the frontend right before
    extraction/scoring so the config reflects whatever the user typed
    into the JD form *after* the initial upload-time createJob call.
    """
    title: str | None = None
    department: str | None = None
    description: str | None = None
    must_have_skills: List[str] | None = None
    nice_to_have_skills: List[str] | None = None
    min_years: int | None = None
    max_years: int | None = None
    education_level: str | None = None
    education_field: str | None = None
    keywords: List[str] | None = None


class ScoreRequest(BaseModel):
    weights: dict  # {"skills": 40, "experience": 25, "keywords": 20, "education": 15}

    @field_validator("weights")
    @classmethod
    def weights_must_sum_to_100(cls, v: dict) -> dict:
        total = sum(v.values())
        if abs(total - 100) > 0.01:
            raise ValueError(
                f"Weights must sum to 100, got {total}"
            )
        return v


class UploadResponse(BaseModel):
    job_id: str
    accepted: List[str]    # filenames that were accepted
    rejected: List[dict]   # [{"filename": "x.txt", "reason": "Not a PDF"}]
    total_accepted: int


from src.core.lazy_proxy import LazyProxy

# ── Shared service instances ─────────────────────────────────────────────────

_extraction_service = LazyProxy(ExtractionService)
_scorer = LazyProxy(CandidateScorer)

# ── Infrastructure singletons ────────────────────────────────────────────────

_jobs_repo = LazyProxy(JobsRepository)
_docs_repo = LazyProxy(DocumentsRepository)
_scoring_repo = LazyProxy(ScoringRepository)
_storage = LazyProxy(StorageService)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse)
async def create_job(body: CreateJobRequest):
    """Create a new screening job.

    Persists to DynamoDB: PK=JOB#{id}, SK=METADATA.
    """
    job = JobItem(
        title=body.title,
        department=body.department,
        description=body.description,
        must_have_skills=body.must_have_skills,
        nice_to_have_skills=body.nice_to_have_skills,
        min_years=body.min_years,
        max_years=body.max_years,
        education_level=body.education_level,
        education_field=body.education_field,
        keywords=body.keywords,
    )

    _jobs_repo.create(job)
    logger.info("Created job: %s (%s)", job.job_id, body.title)

    return CreateJobResponse(id=job.job_id, title=body.title, status="created")


@router.patch("/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest):
    """Update the JD config for an existing job.

    Merges only the supplied (non-None) fields.
    Uses optimistic locking via version counter.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"id": job_id, "config": {}, "status": "unchanged"}

    updated_job = _jobs_repo.update(job_id, updates, expected_version=job.version)
    logger.info("Job %s config updated with fields: %s", job_id, list(updates.keys()))

    return {
        "id": job_id,
        "config": updates,
        "status": "updated",
    }


@router.post("/{job_id}/resumes", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resumes(job_id: str, background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Upload resume PDFs for a job.

    Server-side validation:
    - Only .pdf files accepted
    - Max 10 MB per file
    - Duplicate detection via SHA256

    Files are uploaded to S3 and metadata stored in DynamoDB.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB

    accepted: List[str] = []
    rejected: List[dict] = []

    for f in files:
        # Check extension
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            rejected.append({"filename": f.filename or "unknown", "reason": "Not a PDF file"})
            continue

        # Check content type
        if f.content_type and f.content_type != "application/pdf":
            rejected.append({"filename": f.filename, "reason": f"Invalid content type: {f.content_type}"})
            continue

        # Check size (read content)
        content = await f.read()
        if len(content) > MAX_SIZE:
            size_mb = round(len(content) / (1024 * 1024), 1)
            rejected.append({"filename": f.filename, "reason": f"File too large: {size_mb}MB (max 10MB)"})
            continue

        # ── Duplicate detection via SHA256 ────────────────────────────
        file_hash = hashlib.sha256(content).hexdigest()
        existing = _docs_repo.find_by_hash(job_id, file_hash)
        if existing:
            rejected.append({
                "filename": f.filename,
                "reason": f"Duplicate of '{existing.filename}' (SHA256 match)",
            })
            continue

        # ── Generate document ID and upload to S3 ─────────────────────
        doc_id = str(uuid.uuid4())
        s3_key = _storage.upload_resume(job_id, doc_id, content, f.filename)

        # ── Create document record in DynamoDB ────────────────────────
        doc = DocumentItem(
            document_id=doc_id,
            job_id=job_id,
            filename=f.filename,
            file_size=len(content),
            content_hash=file_hash,
            s3_pdf_key=s3_key,
        )
        _docs_repo.create(doc)

        # ── Increment job document count ──────────────────────────────
        # Re-read job to get latest version for optimistic lock
        job = _jobs_repo.get(job_id)
        if job:
            _jobs_repo.increment_document_count(job_id, expected_version=job.version)

        accepted.append(f.filename)

    # Get final document count
    all_docs = _docs_repo.list_for_job(job_id)

    from src.config.aws import is_running_in_lambda
    if not is_running_in_lambda():
        background_tasks.add_task(_run_extraction_background, job_id)

    return UploadResponse(
        job_id=job_id,
        accepted=accepted,
        rejected=rejected,
        total_accepted=len(all_docs),
    )


def _extract_single_sync(pdf_path: str, doc_id: str, s3_bucket: str, s3_key: str) -> Dict[str, Any]:
    """Run extraction for a single PDF (CPU-bound, called via to_thread)."""
    from src.extraction.extraction_pipeline import ExtractionPipeline
    pipeline = ExtractionPipeline()
    result = pipeline.run_pipeline(pdf_path, doc_id, s3_bucket, s3_key)
    
    if result.get("error_reason"):
        # Log it but proceed with the degraded PyMuPDF Markdown
        import logging
        logging.getLogger(__name__).warning(f"Extraction fell back to degraded PyMuPDF due to: {result['error_reason']}")
        
    return result


async def _run_extraction_background(job_id: str):
    """Background task to run extraction synchronously in local dev."""
    job = _jobs_repo.get(job_id)
    if not job:
        return

    # R-14: idempotency guard — do not re-process if already extracted or scored.
    if job.status in (JobStatus.SCORED, JobStatus.EXTRACTED, JobStatus.EXTRACTING):
        logger.info(
            "Job %s already in status %s — skipping re-extraction (R-14)",
            job_id, job.status,
        )
        return

    documents = _docs_repo.list_for_job(job_id)
    if not documents:
        return

    # Update job status to extracting
    _jobs_repo.update_status(job_id, JobStatus.EXTRACTING, expected_version=job.version)

    succeeded = 0
    semaphore = _get_semaphore()
    logger.info(
        "Starting extraction for job %s — %d document(s), max concurrency: %d",
        job_id, len(documents), _MAX_CONCURRENT,
    )

    async def _extract_one(doc: DocumentItem) -> None:
        nonlocal succeeded
        # R-14: skip already-processed documents (don't burn a semaphore slot)
        if doc.status in (DocumentStatus.PARSED, DocumentStatus.SCORED):
            succeeded += 1
            return

        try:
            # Acquire semaphore BEFORE any work — caps in-flight threads to
            # MAX_CONCURRENT_EXTRACTIONS.  The context manager guarantees release
            # even if extraction raises, so one failing doc cannot starve others.
            async with semaphore:
                # Mark document as parsing
                _docs_repo.update_status(
                    doc.job_id, doc.document_id,
                    DocumentStatus.PARSING, expected_version=doc.version,
                )

                # Download PDF from S3 to a temp file
                pdf_bytes = _storage.get_resume(doc.job_id, doc.document_id)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                try:
                    from src.config.aws import get_settings
                    settings = get_settings()
                    # Run extraction in a thread (CPU-bound — keeps event loop free)
                    extraction_result = await asyncio.to_thread(
                        _extract_single_sync,
                        tmp_path,
                        doc.document_id,
                        settings.s3_bucket_name,
                        doc.s3_pdf_key
                    )
                    fields = extraction_result["fields"]

                    # Upload extraction JSON to S3
                    s3_extracted_key = _storage.upload_extracted_json(
                        doc.job_id, doc.document_id, fields,
                    )

                    # Update document in DynamoDB
                    candidate_name = fields.get("name", "") or ""
                    _docs_repo.update_extraction(
                        job_id=doc.job_id,
                        document_id=doc.document_id,
                        s3_extracted_key=s3_extracted_key,
                        extraction_quality=extraction_result.get("extraction_quality", 0.0),
                        candidate_name=candidate_name,
                        page_count=extraction_result.get("page_count", 0),
                        expected_version=doc.version + 1,  # +1 because update_status already incremented
                    )

                    succeeded += 1
                finally:
                    # Clean up temp file regardless of success or failure
                    Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("Extraction failed for %s: %s", doc.filename, e, exc_info=True)
            # Best-effort: mark document as failed so the SSE stream doesn't
            # wait for it forever.  Re-fetch to get the current version first.
            try:
                fresh_doc = _docs_repo.get(doc.job_id, doc.document_id)
                if fresh_doc:
                    _docs_repo.update_status(
                        doc.job_id, doc.document_id,
                        DocumentStatus.PARSE_FAILED,
                        expected_version=fresh_doc.version,
                    )
            except Exception:
                pass  # Best-effort status update

    # Launch all tasks concurrently — the semaphore inside _extract_one bounds
    # how many actually run at once.  return_exceptions=True ensures one task
    # failure does not cancel the gather (per-document isolation).
    tasks = [asyncio.create_task(_extract_one(doc)) for doc in documents]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        "Extraction complete for job %s — %d/%d succeeded",
        job_id, succeeded, len(documents),
    )

    # Update job status
    updated_job = _jobs_repo.get(job_id)
    if updated_job:
        new_status = JobStatus.EXTRACTED if succeeded > 0 else JobStatus.CREATED
        _jobs_repo.update_status(job_id, new_status, expected_version=updated_job.version)


async def _extraction_event_stream(job_id: str):
    """Generator that yields SSE events by polling DynamoDB state (resumable)."""
    job = _jobs_repo.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    seen_completed = set()

    while True:
        documents = _docs_repo.list_for_job(job_id)
        if not documents:
            yield f"event: error\ndata: {json.dumps({'error': 'No resumes uploaded'})}\n\n"
            return

        total = len(documents)
        completed_docs = 0
        succeeded = 0
        failed = 0

        for doc in documents:
            is_completed = doc.status in (DocumentStatus.PARSED, DocumentStatus.PARSE_FAILED, DocumentStatus.SCORED)
            if is_completed:
                completed_docs += 1
                if doc.status == DocumentStatus.PARSE_FAILED:
                    failed += 1
                else:
                    succeeded += 1

                if doc.document_id not in seen_completed:
                    seen_completed.add(doc.document_id)
                    event_data = json.dumps({
                        "type": "extraction_progress",
                        "current": len(seen_completed),
                        "total": total,
                        "filename": doc.filename,
                        "status": "failed" if doc.status == DocumentStatus.PARSE_FAILED else "extracted",
                    })
                    yield f"event: progress\ndata: {event_data}\n\n"

        if completed_docs == total:
            yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total, 'succeeded': succeeded, 'failed': failed})}\n\n"
            break

        await asyncio.sleep(2.0)


@router.get("/{job_id}/extract")
async def extract_resumes(job_id: str):
    """Start extraction as a Server-Sent Events stream.

    Downloads PDFs from S3, runs extraction, uploads results back to S3,
    and updates DynamoDB metadata.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _extraction_event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/score")
async def score_job(job_id: str, body: ScoreRequest):
    """Score and rank candidates for a job.

    1. Loads extracted JSON from S3 for each document
    2. Runs CandidateScorer.rank()
    3. Uploads full ranking JSON to S3
    4. Stores scoring metadata in DynamoDB
    5. Returns scored candidates to frontend
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Load all extracted documents from DynamoDB
    documents = _docs_repo.list_for_job(job_id)
    extracted_docs = [d for d in documents if d.status == DocumentStatus.PARSED]

    if not extracted_docs:
        raise HTTPException(
            status_code=400,
            detail="No candidates have been extracted yet. Run extraction first."
        )

    # Update job status to scoring
    _jobs_repo.update_status(job_id, JobStatus.SCORING, expected_version=job.version)

    # Load extraction JSONs from S3
    candidates: List[Dict[str, Any]] = []
    for doc in extracted_docs:
        try:
            fields = _storage.get_extracted_json(doc.job_id, doc.document_id)
            fields['_document_id'] = doc.document_id
            if 'extraction_quality' not in fields:
                fields['extraction_quality'] = doc.extraction_quality or 0.0
            candidates.append(fields)
        except Exception as e:
            logger.warning("Failed to load extraction for doc %s: %s", doc.document_id, e)

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="Failed to load any extraction results from storage."
        )

    # Convert weights from 0-100 scale to 0.0-1.0 fractions for the scorer
    raw_weights = body.weights
    fractional_weights = {k: v / 100.0 for k, v in raw_weights.items()}

    # Build the JobDescription for the scorer
    jd = JobDescription(
        title=job.title,
        department=job.department,
        description=job.description,
        must_have_skills=job.must_have_skills,
        nice_to_have_skills=job.nice_to_have_skills,
        min_years=job.min_years,
        max_years=job.max_years,
        required_degree=job.education_level,
        preferred_field=job.education_field,
        keywords=job.keywords,
        weights=fractional_weights,
    )

    # ── Create scoring record (status=SCORING) ────────────────────────────
    scoring = ScoringItem(
        job_id=job_id,
        weights_used={k: float(v) for k, v in raw_weights.items()},
        s3_result_key=f"jobs/{job_id}/scoring/pending.json",
    )
    _scoring_repo.create(scoring)

    try:
        from src.ats.ats_scoring_service import AtsScoringService
        ats_service = AtsScoringService()

        async def run_scoring():
            return await asyncio.to_thread(_scorer.rank, jd, candidates)

        async def run_ats(candidate):
            return await asyncio.to_thread(ats_service.score, candidate.get("elements", []), candidate.get("extraction_quality", 0.0))

        score_task = asyncio.create_task(run_scoring())
        ats_tasks = [asyncio.create_task(run_ats(c)) for c in candidates]
        
        gathered_results = await asyncio.gather(score_task, *ats_tasks)
        results = gathered_results[0]
        ats_results = gathered_results[1:]
        
        # Merge ATS results using document_id
        ats_by_doc_id = {c.get("_document_id"): ats for c, ats in zip(candidates, ats_results)}
        
        for r in results:
            ats = ats_by_doc_id.get(r.document_id)
            if ats:
                r.ats_score = ats.ats_score
                r.ats_warnings = ats.warnings
                
    except Exception as e:
        logger.error("Scoring failed for job %s: %s", job_id, e, exc_info=True)
        # Mark scoring as failed
        _scoring_repo.fail(job_id, scoring.scoring_id, expected_version=scoring.version)
        # Reset job status
        fresh_job = _jobs_repo.get(job_id)
        if fresh_job:
            _jobs_repo.update_status(job_id, JobStatus.EXTRACTED, expected_version=fresh_job.version)
        raise HTTPException(
            status_code=500,
            detail=f"Scoring failed: {str(e)}"
        )

    # Convert ScoredCandidate dataclasses to dicts
    scored_dicts = [asdict(r) for r in results]

    # Inject pdf_url for each candidate using their document_id
    for sd in scored_dicts:
        doc_id = sd.get('document_id', '')
        if doc_id:
            sd['pdf_url'] = f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download"

    # ── Upload full ranking JSON to S3 ────────────────────────────────────
    s3_result_key = _storage.upload_ranking(job_id, scoring.scoring_id, scored_dicts)

    # ── Complete scoring record in DynamoDB ────────────────────────────────
    top_name = scored_dicts[0]["name"] if scored_dicts else ""
    top_score = scored_dicts[0]["final_score"] if scored_dicts else 0.0
    _scoring_repo.complete(
        job_id=job_id,
        scoring_id=scoring.scoring_id,
        top_candidate_name=top_name,
        top_candidate_score=top_score,
        candidate_count=len(scored_dicts),
        expected_version=scoring.version,
    )

    # ── Update job status to scored ───────────────────────────────────────
    fresh_job = _jobs_repo.get(job_id)
    if fresh_job:
        _jobs_repo.update_status(job_id, JobStatus.SCORED, expected_version=fresh_job.version)

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": len(scored_dicts),
        "weights_applied": raw_weights,
        "candidates": scored_dicts,
    }


@router.get("/{job_id}/results")
async def get_results(job_id: str):
    """Retrieve stored scoring results for a job.

    Loads the latest ranking JSON from S3 via the ScoringRepository.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get the latest scoring result from DynamoDB
    latest_scoring = _scoring_repo.get_latest(job_id)
    if not latest_scoring or latest_scoring.status != ScoringStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="No scoring results available. Run analysis first."
        )

    # Load the full ranking JSON from S3
    try:
        candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
    except Exception as e:
        logger.error("Failed to load ranking from S3: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to load scoring results from storage."
        )

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": latest_scoring.candidate_count,
        "candidates": candidates,
    }


@router.get("/{job_id}/resumes/{document_id}/download")
async def download_resume(job_id: str, document_id: str):
    """Download a resume PDF from S3 storage."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = _docs_repo.get(job_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        pdf_bytes = _storage.get_resume(job_id, document_id)
    except Exception as e:
        logger.error("Failed to download resume %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail="Failed to download resume")

    filename = doc.filename or f"{document_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )

@router.post("/ats-check")
async def ats_check(file: UploadFile = File(...)):
    """
    Standalone ATS checker.
    Uploads a PDF, runs through the V2 Extraction Pipeline, and returns a B2B ATS Report.
    """
    import tempfile
    import os
    import uuid
    from src.ats.b2b_ats_scorer import B2BAtsScorer

    try:
        content = await file.read()
        
        # 1. Upload to S3 for ODL to access
        doc_id = str(uuid.uuid4())
        job_id = "ats_check_job"
        s3_key = _storage.upload_resume(job_id, doc_id, content, file.filename or "resume.pdf")
        
        # Save temp file for PyMuPDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            scorer = B2BAtsScorer()
            ats_result = scorer.score(tmp_path, s3_bucket=_storage._bucket, s3_key=s3_key)
            return ats_result
        finally:
            os.remove(tmp_path)
            # Cleanup S3
            try:
                _storage._client.delete_object(Bucket=_storage._bucket, Key=s3_key)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"ATS check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
