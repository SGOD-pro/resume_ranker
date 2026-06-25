"""
jobs.py — Job lifecycle API routes (Phase 10 — DynamoDB + S3)
================================================================
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
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
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


# ── Shared service instances ─────────────────────────────────────────────────

_extraction_service = ExtractionService()
_scorer = CandidateScorer()

# ── Infrastructure singletons ────────────────────────────────────────────────

_jobs_repo = JobsRepository()
_docs_repo = DocumentsRepository()
_scoring_repo = ScoringRepository()
_storage = StorageService()


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


@router.post("/{job_id}/resumes", response_model=UploadResponse)
async def upload_resumes(job_id: str, files: List[UploadFile] = File(...)):
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

    return UploadResponse(
        job_id=job_id,
        accepted=accepted,
        rejected=rejected,
        total_accepted=len(all_docs),
    )


def _extract_single_sync(pdf_path: str) -> Dict[str, Any]:
    """Run extraction for a single PDF (CPU-bound, called via to_thread).

    Returns the fields dict on success, or raises on failure.
    """
    result = _extraction_service.extract_single(pdf_path)
    # Serialize complex field values to plain dicts/lists
    fields = json.loads(json.dumps(
        result.fields,
        default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
    ))
    # Add document_id and extraction_quality for the scorer
    fields['_document_id'] = result.document_id
    if 'extraction_quality' not in fields:
        fields['extraction_quality'] = 0.0
    return {
        "fields": fields,
        "document_id": result.document_id,
        "extraction_quality": getattr(result, 'extraction_quality', 0.0),
        "page_count": getattr(result, 'page_count', 0),
        "domain": getattr(result, 'domain', ''),
    }


async def _extraction_event_stream(job_id: str):
    """Generator that yields SSE events from REAL extraction.

    1. Downloads PDFs from S3 to temp dir
    2. Runs PDFPipelineV3.extract() concurrently via asyncio.to_thread()
    3. Uploads extraction JSON back to S3
    4. Updates DynamoDB document metadata
    5. Yields progress events as each file completes
    """
    job = _jobs_repo.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    documents = _docs_repo.list_for_job(job_id)
    if not documents:
        yield f"event: error\ndata: {json.dumps({'error': 'No resumes uploaded'})}\n\n"
        return

    # Update job status to extracting
    _jobs_repo.update_status(job_id, JobStatus.EXTRACTING, expected_version=job.version)

    total = len(documents)
    succeeded = 0
    failed = 0

    result_queue: asyncio.Queue = asyncio.Queue()

    async def _extract_one(doc: DocumentItem) -> None:
        """Download PDF from S3, extract, upload result JSON, update DynamoDB."""
        try:
            # Mark document as extracting
            _docs_repo.update_status(
                doc.job_id, doc.document_id,
                DocumentStatus.EXTRACTING, expected_version=doc.version,
            )

            # Download PDF from S3 to a temp file
            pdf_bytes = _storage.get_resume(doc.job_id, doc.document_id)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                # Run extraction (CPU-bound)
                extraction_result = await asyncio.to_thread(_extract_single_sync, tmp_path)
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

                await result_queue.put(("ok", doc.filename, fields))
            finally:
                # Clean up temp file
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("Extraction failed for %s: %s", doc.filename, e, exc_info=True)
            # Mark document as failed
            try:
                fresh_doc = _docs_repo.get(doc.job_id, doc.document_id)
                if fresh_doc:
                    _docs_repo.update_status(
                        doc.job_id, doc.document_id,
                        DocumentStatus.EXTRACTION_FAILED,
                        expected_version=fresh_doc.version,
                    )
            except Exception:
                pass  # Best-effort status update
            await result_queue.put(("error", doc.filename, str(e)))

    # Launch all extractions concurrently
    tasks = [asyncio.create_task(_extract_one(doc)) for doc in documents]

    # Read results as they complete
    for completed in range(1, total + 1):
        status, filename, payload = await result_queue.get()

        if status == "ok":
            succeeded += 1
            event_data = json.dumps({
                "type": "extraction_progress",
                "current": completed,
                "total": total,
                "filename": filename,
                "status": "extracted",
            })
        else:
            failed += 1
            event_data = json.dumps({
                "type": "extraction_progress",
                "current": completed,
                "total": total,
                "filename": filename,
                "status": "failed",
                "error": payload,
            })

        yield f"event: progress\ndata: {event_data}\n\n"

    # Wait for all tasks to finish
    await asyncio.gather(*tasks, return_exceptions=True)

    # Update job status
    updated_job = _jobs_repo.get(job_id)
    if updated_job:
        new_status = JobStatus.EXTRACTED if succeeded > 0 else JobStatus.CREATED
        _jobs_repo.update_status(job_id, new_status, expected_version=updated_job.version)

    # Final complete event
    yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total, 'succeeded': succeeded, 'failed': failed})}\n\n"


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
    extracted_docs = [d for d in documents if d.status == DocumentStatus.EXTRACTED]

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
        results = _scorer.rank(jd, candidates)
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
            sd['pdf_url'] = f"/jobs/{job_id}/resumes/{doc_id}/download"

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
