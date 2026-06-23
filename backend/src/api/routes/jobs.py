"""
jobs.py — Job lifecycle API routes
=====================================
Endpoints:
  POST /jobs                  — create a new job
  POST /jobs/{id}/resumes     — upload resume PDFs
  GET  /jobs/{id}/extract     — SSE stream real extraction progress
  POST /jobs/{id}/score       — score & rank candidates (real scorer)
  GET  /jobs/{id}/results     — retrieve stored scoring results
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from src.services.extraction_service import ExtractionService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

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


# ── In-memory job store ───────────────────────────────────────────────────────

_jobs: dict = {}

# ── Shared service instances ─────────────────────────────────────────────────

_extraction_service = ExtractionService()
_scorer = CandidateScorer()


# ── Upload directory ─────────────────────────────────────────────────────────

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse)
async def create_job(body: CreateJobRequest):
    """Create a new screening job."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "id": job_id,
        "title": body.title,
        "config": body.model_dump(),
        "resumes": [],
        "extracted_candidates": [],
        "scored_results": None,
        "status": "created",
    }
    return CreateJobResponse(id=job_id, title=body.title, status="created")


@router.patch("/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest):
    """Update the JD config for an existing job.

    Merges only the supplied (non-None) fields into the stored config.
    Called by the frontend before extraction/scoring so that the config
    reflects the JD form state the user filled in after uploading resumes.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = body.model_dump(exclude_none=True)
    _jobs[job_id]["config"].update(updates)

    # Keep top-level title in sync
    if "title" in updates:
        _jobs[job_id]["title"] = updates["title"]

    logger.info(f"Job {job_id} config updated with fields: {list(updates.keys())}")

    return {
        "id": job_id,
        "config": _jobs[job_id]["config"],
        "status": "updated",
    }


@router.post("/{job_id}/resumes", response_model=UploadResponse)
async def upload_resumes(job_id: str, files: List[UploadFile] = File(...)):
    """Upload resume PDFs for a job.

    Server-side validation:
    - Only .pdf files accepted
    - Max 10 MB per file
    - Duplicate detection via SHA256

    Files are saved to disk so the extraction pipeline can process them.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB

    # Create job-specific upload directory
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    # Initialize dedup index for this job if not exists
    if "_hash_index" not in _jobs[job_id]:
        _jobs[job_id]["_hash_index"] = {}

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
        import hashlib
        file_hash = hashlib.sha256(content).hexdigest()
        if file_hash in _jobs[job_id]["_hash_index"]:
            original = _jobs[job_id]["_hash_index"][file_hash]
            rejected.append({
                "filename": f.filename,
                "reason": f"Duplicate of '{original}' (SHA256 match)",
            })
            continue
        _jobs[job_id]["_hash_index"][file_hash] = f.filename

        # Save file to disk
        # Use UUID prefix to avoid filename collisions across uploads
        safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
        file_path = job_upload_dir / safe_name
        file_path.write_bytes(content)

        accepted.append(f.filename)
        _jobs[job_id]["resumes"].append({
            "filename": f.filename,
            "size": len(content),
            "path": str(file_path),
            "sha256": file_hash,
        })

    return UploadResponse(
        job_id=job_id,
        accepted=accepted,
        rejected=rejected,
        total_accepted=len(_jobs[job_id]["resumes"]),
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
    return fields


async def _extraction_event_stream(job_id: str):
    """Generator that yields SSE events from REAL extraction.

    Runs PDFPipelineV3.extract() concurrently via asyncio.to_thread()
    for each uploaded resume. Progress events are yielded as each file
    completes.
    """
    job = _jobs.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    resumes = job.get("resumes", [])
    if not resumes:
        yield f"event: error\ndata: {json.dumps({'error': 'No resumes uploaded'})}\n\n"
        return

    total = len(resumes)
    succeeded = 0
    failed = 0
    job["extracted_candidates"] = []

    # Use a queue for clean task→result mapping
    result_queue: asyncio.Queue = asyncio.Queue()

    async def _extract_one(resume_info: dict) -> None:
        """Extract a single resume and push result to queue."""
        filename = resume_info["filename"]
        pdf_path = resume_info["path"]
        try:
            fields = await asyncio.to_thread(_extract_single_sync, pdf_path)
            await result_queue.put(("ok", filename, fields))
        except Exception as e:
            logger.error(f"Extraction failed for {filename}: {e}", exc_info=True)
            await result_queue.put(("error", filename, str(e)))

    # Launch all extractions concurrently
    tasks = [asyncio.create_task(_extract_one(r)) for r in resumes]

    # Read results as they complete
    for completed in range(1, total + 1):
        status, filename, payload = await result_queue.get()

        if status == "ok":
            succeeded += 1
            job["extracted_candidates"].append(payload)
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

    # Wait for all tasks to finish (should already be done)
    await asyncio.gather(*tasks, return_exceptions=True)

    # Final complete event
    yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total, 'succeeded': succeeded, 'failed': failed})}\n\n"


@router.get("/{job_id}/extract")
async def extract_resumes(job_id: str):
    """Start extraction as a Server-Sent Events stream.

    Runs real PDF extraction concurrently across all uploaded resumes.
    """
    if job_id not in _jobs:
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

    Calls CandidateScorer.rank() on the full batch of extracted candidates.
    Weights arrive as 0-100 from the frontend; converted to 0.0-1.0 fractions
    for the scorer.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    candidates = job.get("extracted_candidates", [])

    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No candidates have been extracted yet. Run extraction first."
        )

    config = job.get("config", {})

    # Convert weights from 0-100 scale to 0.0-1.0 fractions for the scorer
    raw_weights = body.weights
    fractional_weights = {k: v / 100.0 for k, v in raw_weights.items()}

    # Build the JobDescription for the scorer
    jd = JobDescription(
        title=config.get("title", ""),
        department=config.get("department", ""),
        description=config.get("description", ""),
        must_have_skills=config.get("must_have_skills", []),
        nice_to_have_skills=config.get("nice_to_have_skills", []),
        min_years=config.get("min_years", 0),
        max_years=config.get("max_years", 99),
        required_degree=config.get("education_level", "any"),
        preferred_field=config.get("education_field", ""),
        keywords=config.get("keywords", []),
        weights=fractional_weights,
    )

    try:
        print(jd)
        results = _scorer.rank(jd, candidates)
    except Exception as e:
        logger.error(f"Scoring failed for job {job_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Scoring failed: {str(e)}"
        )

    # Convert ScoredCandidate dataclasses to dicts
    scored_dicts = [asdict(r) for r in results]

    # Store results for GET /results
    job["scored_results"] = scored_dicts
    job["status"] = "scored"

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": len(scored_dicts),
        "weights_applied": raw_weights,
        "candidates": scored_dicts,
        "debug_jd": asdict(jd),
    }


@router.get("/{job_id}/results")
async def get_results(job_id: str):
    """Retrieve stored scoring results for a job.

    Returns the last scored results without re-running analysis.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    scored = job.get("scored_results")

    if scored is None:
        raise HTTPException(
            status_code=400,
            detail="No scoring results available. Run analysis first."
        )

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": len(scored),
        "candidates": scored,
    }
