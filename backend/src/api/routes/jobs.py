"""
jobs.py — Job lifecycle API routes
=====================================
Stub endpoints for:
  POST /jobs                  — create a new job
  POST /jobs/{id}/resumes     — upload resume PDFs
  GET  /jobs/{id}/extract     — SSE stream extraction progress
  POST /jobs/{id}/score       — score & rank candidates

These are STUBS that return placeholder responses.
They do NOT call into pipeline.py or any core logic yet.
Integration with ExtractionService / RankingService will
happen in a later phase.
"""

import asyncio
import json
import uuid
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

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


# ── In-memory job store (stub) ────────────────────────────────────────────────

_jobs: dict = {}


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
        "status": "created",
    }
    return CreateJobResponse(id=job_id, title=body.title, status="created")


@router.post("/{job_id}/resumes", response_model=UploadResponse)
async def upload_resumes(job_id: str, files: List[UploadFile] = File(...)):
    """Upload resume PDFs for a job.

    Server-side validation:
    - Only .pdf files accepted
    - Max 10 MB per file
    """
    if job_id not in _jobs:
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

        # Accept the file (store in-memory for now)
        accepted.append(f.filename)
        _jobs[job_id]["resumes"].append({
            "filename": f.filename,
            "size": len(content),
        })

    return UploadResponse(
        job_id=job_id,
        accepted=accepted,
        rejected=rejected,
        total_accepted=len(_jobs[job_id]["resumes"]),
    )


async def _extraction_event_stream(job_id: str):
    """Generator that yields SSE events simulating extraction progress.

    In a future phase this will call ExtractionService.extract_single()
    for each uploaded resume. For now it yields stub events.
    """
    job = _jobs.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    resumes = job.get("resumes", [])
    total = len(resumes) if resumes else 3  # fallback for demo

    for i in range(total):
        filename = resumes[i]["filename"] if i < len(resumes) else f"resume_{i+1}.pdf"
        # Simulate extraction delay
        await asyncio.sleep(0.5)

        event_data = json.dumps({
            "type": "extraction_progress",
            "current": i + 1,
            "total": total,
            "filename": filename,
            "status": "extracted",
        })
        yield f"event: progress\ndata: {event_data}\n\n"

    # Final complete event
    yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total})}\n\n"


@router.get("/{job_id}/extract")
async def extract_resumes(job_id: str):
    """Start extraction as a Server-Sent Events stream.

    Stub implementation — yields simulated progress events.
    Will integrate with ExtractionService in a future phase.
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

    Stub implementation — returns placeholder scored candidates.
    Will integrate with RankingService in a future phase.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    # Stub: return mock scored candidates
    _jobs[job_id]["status"] = "scored"
    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": len(_jobs[job_id].get("resumes", [])),
        "weights_applied": body.weights,
        "candidates": [],  # Will be populated by RankingService
    }
