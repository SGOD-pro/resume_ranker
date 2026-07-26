"""
jobs_v2.py — Job lifecycle API routes (/api/v2/jobs/*)
========================================================
Endpoints:
  POST   /api/v2/jobs                            — create job
  PATCH  /api/v2/jobs/{id}                       — update JD config + weights
  POST   /api/v2/jobs/{id}/resumes               — upload resume PDFs (multipart)
  GET    /api/v2/jobs/{id}/extract               — SSE extraction progress stream
  POST   /api/v2/jobs/{id}/score                 — score & rank candidates
  GET    /api/v2/jobs/{id}/results               — retrieve stored scoring results
  GET    /api/v2/jobs/{id}/candidates            — list candidates (paginated)
  GET    /api/v2/jobs/{id}/candidates/export     — CSV export
  GET    /api/v2/jobs/{id}/candidates/{cid}      — candidate detail
  GET    /api/v2/jobs/{id}/resumes/{doc_id}/download — download PDF

Lambda-safe: uses SSE (EventSource) for streaming, NOT WebSockets.
"""

import asyncio
import io
import csv
import hashlib
import json
import logging
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.errors import NotFoundError

# ── Infrastructure repos (full, not thin wrappers) ────────────────────────────
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.storage.storage_service import StorageService

# ── Extraction + scoring services ─────────────────────────────────────────────
from src.services.extraction_service import ExtractionService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/jobs", tags=["Jobs V2"])

# ── Service singletons ────────────────────────────────────────────────────────

_jobs_repo = JobsRepository()
_docs_repo = DocumentsRepository()
_scoring_repo = ScoringRepository()
_storage = StorageService()
_extraction_service = ExtractionService()
_scorer = CandidateScorer()


# ── DTOs ──────────────────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    title: str
    department: str = ""
    description: str = ""
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    min_years: int = 0
    max_years: int = 99
    education_level: str = "any"
    education_field: str = ""
    keywords: List[str] = Field(default_factory=list)
    weights: Dict[str, float] = Field(default_factory=lambda: {
        "skills": 40.0,
        "experience": 25.0,
        "keywords": 20.0,
        "education": 15.0,
    })


class UpdateJobRequest(BaseModel):
    """Partial update — sync JD form state + weights before extraction."""
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
    weights: Dict[str, float] | None = None


class ScoreRequest(BaseModel):
    weights: Dict[str, float]

    @field_validator("weights")
    @classmethod
    def weights_must_sum_to_100(cls, v: Dict[str, float]) -> Dict[str, float]:
        total = sum(v.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f"Weights must sum to 100, got {total}")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_single_sync(pdf_path: str) -> Dict[str, Any]:
    """CPU-bound extraction — called via asyncio.to_thread()."""
    result = _extraction_service.extract_single(pdf_path)
    fields = json.loads(json.dumps(
        result.fields,
        default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
    ))
    fields["_document_id"] = result.document_id
    if "extraction_quality" not in fields:
        fields["extraction_quality"] = 0.0
    return {
        "fields": fields,
        "document_id": result.document_id,
        "extraction_quality": getattr(result, "extraction_quality", 0.0),
        "page_count": getattr(result, "page_count", 0),
        "domain": getattr(result, "domain", ""),
    }


async def _extraction_event_stream(job_id: str):
    """
    SSE generator — Lambda-safe streaming.
    Downloads PDFs from S3 → extracts → uploads JSON → yields progress events.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    documents = _docs_repo.list_for_job(job_id)
    if not documents:
        yield f"event: error\ndata: {json.dumps({'error': 'No resumes uploaded'})}\n\n"
        return

    _jobs_repo.update_status(job_id, JobStatus.EXTRACTING, expected_version=job.version)

    total = len(documents)
    succeeded = 0
    failed = 0
    result_queue: asyncio.Queue = asyncio.Queue()

    async def _extract_one(doc: DocumentItem) -> None:
        try:
            _docs_repo.update_status(
                doc.job_id, doc.document_id,
                DocumentStatus.EXTRACTING, expected_version=doc.version,
            )

            pdf_bytes = _storage.get_resume(doc.job_id, doc.document_id)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            try:
                extraction_result = await asyncio.to_thread(_extract_single_sync, tmp_path)
                fields = extraction_result["fields"]

                s3_extracted_key = _storage.upload_extracted_json(
                    doc.job_id, doc.document_id, fields,
                )

                candidate_name = fields.get("name", "") or ""
                _docs_repo.update_extraction(
                    job_id=doc.job_id,
                    document_id=doc.document_id,
                    s3_extracted_key=s3_extracted_key,
                    extraction_quality=extraction_result.get("extraction_quality", 0.0),
                    candidate_name=candidate_name,
                    page_count=extraction_result.get("page_count", 0),
                    expected_version=doc.version + 1,
                )
                await result_queue.put(("ok", doc.filename, fields))
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("Extraction failed for %s: %s", doc.filename, e, exc_info=True)
            try:
                fresh_doc = _docs_repo.get(doc.job_id, doc.document_id)
                if fresh_doc:
                    _docs_repo.update_status(
                        doc.job_id, doc.document_id,
                        DocumentStatus.EXTRACTION_FAILED,
                        expected_version=fresh_doc.version,
                    )
            except Exception:
                pass
            await result_queue.put(("error", doc.filename, str(e)))

    tasks = [asyncio.create_task(_extract_one(doc)) for doc in documents]

    for completed in range(1, total + 1):
        status_str, filename, payload = await result_queue.get()

        if status_str == "ok":
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

    await asyncio.gather(*tasks, return_exceptions=True)

    updated_job = _jobs_repo.get(job_id)
    if updated_job:
        new_status = JobStatus.EXTRACTED if succeeded > 0 else JobStatus.CREATED
        _jobs_repo.update_status(job_id, new_status, expected_version=updated_job.version)

    yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total, 'succeeded': succeeded, 'failed': failed})}\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(req: CreateJobRequest):
    """POST /api/v2/jobs — Create a new screening job."""
    job = JobItem(
        title=req.title,
        department=req.department,
        description=req.description,
        must_have_skills=req.must_have_skills,
        nice_to_have_skills=req.nice_to_have_skills,
        min_years=req.min_years,
        max_years=req.max_years,
        education_level=req.education_level,
        education_field=req.education_field,
        keywords=req.keywords,
    )
    _jobs_repo.create(job)
    logger.info("Created job v2: %s (%s)", job.job_id, req.title)
    return {"id": job.job_id, "title": req.title, "status": "created"}


@router.patch("/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest):
    """
    PATCH /api/v2/jobs/{job_id}
    Sync JD config and weights from the frontend form before analysis.
    Merges only supplied (non-None) fields.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"id": job_id, "status": "unchanged"}

    _jobs_repo.update(job_id, updates, expected_version=job.version)
    logger.info("Updated job %s: %s", job_id, list(updates.keys()))
    return {"id": job_id, "status": "updated", "config": updates}


@router.post("/{job_id}/resumes")
async def upload_resumes(
    job_id: str,
    files: List[UploadFile] = File(...),
):
    """
    POST /api/v2/jobs/{job_id}/resumes
    Upload resume PDFs (multipart/form-data).
    UUID-keyed in S3, SHA256 dedup, metadata in DynamoDB.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    accepted: List[str] = []
    rejected: List[dict] = []

    for f in files:
        filename = f.filename or "resume.pdf"

        if not filename.lower().endswith(".pdf"):
            rejected.append({"filename": filename, "reason": "Not a PDF file"})
            continue

        content = await f.read()

        if len(content) > MAX_SIZE:
            size_mb = round(len(content) / (1024 * 1024), 1)
            rejected.append({"filename": filename, "reason": f"File too large: {size_mb}MB (max 10MB)"})
            continue

        # SHA256 dedup
        file_hash = hashlib.sha256(content).hexdigest()
        existing = _docs_repo.find_by_hash(job_id, file_hash)
        if existing:
            rejected.append({
                "filename": filename,
                "reason": f"Duplicate of '{existing.filename}' (SHA256 match)",
            })
            continue

        doc_id = str(uuid.uuid4())
        try:
            s3_key = _storage.upload_resume(job_id, doc_id, content, filename)
        except Exception as e:
            logger.error("S3 upload failed for %s: %s", filename, e)
            rejected.append({"filename": filename, "reason": f"Storage error: {e}"})
            continue

        doc = DocumentItem(
            document_id=doc_id,
            job_id=job_id,
            filename=filename,
            file_size=len(content),
            content_hash=file_hash,
            s3_pdf_key=s3_key,
        )
        _docs_repo.create(doc)

        # Increment job doc count
        fresh_job = _jobs_repo.get(job_id)
        if fresh_job:
            _jobs_repo.increment_document_count(job_id, expected_version=fresh_job.version)

        accepted.append(filename)
        logger.info("Uploaded resume: job=%s doc=%s file=%s", job_id, doc_id, filename)

    all_docs = _docs_repo.list_for_job(job_id)
    return {
        "job_id": job_id,
        "accepted": accepted,
        "rejected": rejected,
        "total_accepted": len(all_docs),
    }


@router.get("/{job_id}/extract")
async def extract_resumes(job_id: str):
    """
    GET /api/v2/jobs/{job_id}/extract
    SSE stream — Lambda-safe extraction progress.
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
    """
    POST /api/v2/jobs/{job_id}/score
    Score & rank candidates. Loads extraction JSONs from S3, runs scorer,
    saves ranking back to S3 and DynamoDB.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    documents = _docs_repo.list_for_job(job_id)
    extracted_docs = [d for d in documents if d.status == DocumentStatus.EXTRACTED]

    if not extracted_docs:
        raise HTTPException(
            status_code=400,
            detail="No candidates have been extracted yet. Run extraction first.",
        )

    _jobs_repo.update_status(job_id, JobStatus.SCORING, expected_version=job.version)

    # Load extraction JSONs from S3
    candidates: List[Dict[str, Any]] = []
    for doc in extracted_docs:
        try:
            fields = _storage.get_extracted_json(doc.job_id, doc.document_id)
            fields["_document_id"] = doc.document_id
            if "extraction_quality" not in fields:
                fields["extraction_quality"] = doc.extraction_quality or 0.0
            candidates.append(fields)
        except Exception as e:
            logger.warning("Failed to load extraction for doc %s: %s", doc.document_id, e)

    if not candidates:
        raise HTTPException(status_code=400, detail="Failed to load any extraction results from storage.")

    # Weights are 0–100 scale from frontend; scorer expects 0.0–1.0 fractions
    raw_weights = body.weights
    fractional_weights = {k: v / 100.0 for k, v in raw_weights.items()}

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
        _scoring_repo.fail(job_id, scoring.scoring_id, expected_version=scoring.version)
        fresh_job = _jobs_repo.get(job_id)
        if fresh_job:
            _jobs_repo.update_status(job_id, JobStatus.EXTRACTED, expected_version=fresh_job.version)
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    scored_dicts = [asdict(r) for r in results]

    # Inject pdf_url for each candidate
    for sd in scored_dicts:
        doc_id = sd.get("document_id", "")
        if doc_id:
            sd["pdf_url"] = f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download"

    s3_result_key = _storage.upload_ranking(job_id, scoring.scoring_id, scored_dicts)

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
    """GET /api/v2/jobs/{job_id}/results — Retrieve stored scoring results."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    latest_scoring = _scoring_repo.get_latest(job_id)
    if not latest_scoring or latest_scoring.status != ScoringStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="No scoring results available. Run analysis first.")

    try:
        candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
    except Exception as e:
        logger.error("Failed to load ranking from S3: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load scoring results from storage.")

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": latest_scoring.candidate_count,
        "candidates": candidates,
    }


@router.get("/{job_id}/candidates")
async def list_candidates(
    job_id: str,
    limit: int = Query(20, ge=1, le=100),
    cursor: int = Query(0, ge=0),
):
    """GET /api/v2/jobs/{job_id}/candidates — List candidates (paginated)."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    docs = _docs_repo.list_for_job(job_id)
    total = len(docs)
    paged = docs[cursor: cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None

    return {
        "job_id": job_id,
        "total_candidates": total,
        "limit": limit,
        "cursor": next_cursor,
        "candidates": [d.model_dump() for d in paged],
    }


@router.get("/{job_id}/candidates/export")
async def export_candidates_csv(job_id: str):
    """GET /api/v2/jobs/{job_id}/candidates/export — CSV export."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Try to get scored results first; fall back to doc list
    latest_scoring = _scoring_repo.get_latest(job_id)
    if latest_scoring and latest_scoring.status == ScoringStatus.COMPLETED:
        try:
            candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
        except Exception:
            candidates = []
    else:
        candidates = []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "candidate_id", "candidate_name", "composite_score", "skill_score",
        "experience_score", "education_score", "ats_score", "flags",
    ])
    for c in candidates:
        writer.writerow([
            c.get("document_id") or c.get("id") or c.get("candidate_id"),
            c.get("name", "Unknown Candidate"),
            c.get("final_score", c.get("composite_score", 0.0)),
            c.get("skill_score", 0.0),
            c.get("experience_score", 0.0),
            c.get("education_score", 0.0),
            c.get("ats_score", 0.0),
            "; ".join(c.get("knockout_reasons", [])) if isinstance(c.get("knockout_reasons"), list) else "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=job_{job_id}_candidates.csv"},
    )


@router.get("/{job_id}/candidates/{cid}")
async def get_candidate_detail(job_id: str, cid: str):
    """GET /api/v2/jobs/{job_id}/candidates/{cid} — Candidate detail."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = _docs_repo.get(job_id, cid)
    if not doc:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = doc.model_dump()

    # Ensure ats_result shape is present
    if not result.get("ats_result"):
        result["ats_result"] = {
            "ats_score": result.get("ats_score", 0.0),
            "signals": {},
            "flags": [],
            "bounding_boxes": [],
        }

    # Ensure extraction shape is present
    if not result.get("extraction"):
        result["extraction"] = {"explicit_skills": []}

    return result


@router.get("/{job_id}/resumes/{doc_id}/download")
async def download_resume(job_id: str, doc_id: str):
    """GET /api/v2/jobs/{job_id}/resumes/{doc_id}/download — Download PDF from S3."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = _docs_repo.get(job_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        pdf_bytes = _storage.get_resume(job_id, doc_id)
    except Exception as e:
        logger.error("Failed to download resume %s: %s", doc_id, e)
        raise HTTPException(status_code=500, detail="Failed to download resume")

    filename = doc.filename or f"{doc_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
