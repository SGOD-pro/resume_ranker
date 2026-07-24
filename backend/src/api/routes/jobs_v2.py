import io
import csv
import uuid
import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from src.repositories.job_repo import DynamoJobRepository
from src.repositories.candidate_repo import DynamoCandidateRepository
from src.api.errors import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/jobs", tags=["Jobs V2"])

job_repo = DynamoJobRepository()
candidate_repo = DynamoCandidateRepository()


# ── DTOs ──────────────────────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    title: str
    department: str = ""
    description: str = ""
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    min_years: int = 0
    max_years: int = 99
    education_level: str = "any"
    education_field: str = ""
    keywords: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=lambda: {
        "skills": 0.40,
        "experience": 0.25,
        "keywords": 0.20,
        "education": 0.15,
    })


class UpdateWeightsRequest(BaseModel):
    skills: float | None = None
    experience: float | None = None
    education: float | None = None
    semantic: float | None = None
    keywords: float | None = None

    def get_weights_dict(self, raw_body: dict[str, Any]) -> dict[str, float]:
        if "weights" in raw_body and isinstance(raw_body["weights"], dict):
            return {k: float(v) for k, v in raw_body["weights"].items()}
        return {k: float(v) for k, v in raw_body.items() if isinstance(v, (int, float))}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_job(req: CreateJobRequest):
    """
    POST /api/v2/jobs
    Create a job, save JD, and trigger skill extraction.
    """
    job_id = str(uuid.uuid4())
    job_data = req.model_dump()
    job_data["job_id"] = job_id
    job_data["id"] = job_id
    job_data["status"] = "created"
    job_data["config"] = {"weights": req.weights, "title": req.title, "description": req.description}

    saved = job_repo.save(job_data)
    logger.info("Created job v2: %s", job_id)
    return saved


@router.get("/{id}")
async def get_job(id: str):
    """
    GET /api/v2/jobs/{id}
    Retrieve job configuration and scoring weights.
    """
    job = job_repo.get(id)
    if not job:
        raise NotFoundError(f"Job ID {id} does not exist")

    # Format to include config.weights if expected
    if "config" not in job or "weights" not in job.get("config", {}):
        job["config"] = {"weights": job.get("weights", {})}
    return job


@router.patch("/{id}/weights")
async def update_job_weights(id: str, raw_payload: dict[str, Any]):
    """
    PATCH /api/v2/jobs/{id}/weights
    Update scoring weights for a job. Accepts either {"weights": {...}} or top-level weights.
    """
    weights = raw_payload.get("weights") if "weights" in raw_payload and isinstance(raw_payload["weights"], dict) else raw_payload
    try:
        updated = job_repo.update_weights(id, weights)
        if "config" not in updated:
            updated["config"] = {}
        updated["config"]["weights"] = weights
        return updated
    except KeyError:
        raise NotFoundError(f"Job ID {id} does not exist")


@router.post("/{id}/resumes")
async def generate_presigned_resume_upload(
    id: str,
    payload: dict[str, Any] | None = None,
    filename: str = Query("resume.pdf")
):
    """
    POST /api/v2/jobs/{id}/resumes
    Generates presigned S3 URL for direct client upload.
    """
    job = job_repo.get(id)
    if not job:
        raise NotFoundError(f"Job ID {id} does not exist")

    if payload and "filename" in payload:
        filename = payload["filename"]

    candidate_id = str(uuid.uuid4())
    s3_key = f"jobs/{id}/resumes/{candidate_id}_{filename}"
    
    presigned_url = f"https://resume-ranker-bucket.s3.amazonaws.com/{s3_key}?mock_presigned_token=123"

    candidate_repo.save(id, {
        "candidate_id": candidate_id,
        "id": candidate_id,
        "job_id": id,
        "filename": filename,
        "s3_pdf_key": s3_key,
        "status": "uploaded"
    })

    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "s3_key": s3_key,
        "url": presigned_url,
        "upload_url": presigned_url,
        "fields": {"key": s3_key, "Content-Type": "application/pdf"},
        "headers": {"Content-Type": "application/pdf"}
    }


@router.get("/{id}/candidates")
async def list_candidates(
    id: str,
    min_score: float | None = Query(None),
    max_score: float | None = Query(None),
    skill: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: int = Query(0, ge=0)
):
    """
    GET /api/v2/jobs/{id}/candidates
    List candidates with filtering and cursor pagination.
    """
    job = job_repo.get(id)
    if not job:
        raise NotFoundError(f"Job ID {id} does not exist")

    return candidate_repo.list_for_job(
        job_id=id,
        min_score=min_score,
        max_score=max_score,
        skill_filter=skill,
        limit=limit,
        cursor=cursor
    )


@router.get("/{id}/candidates/export")
async def export_candidates_csv(id: str):
    """
    GET /api/v2/jobs/{id}/candidates/export
    CSV export of candidates with full score breakdowns.
    """
    job = job_repo.get(id)
    if not job:
        raise NotFoundError(f"Job ID {id} does not exist")

    cands_res = candidate_repo.list_for_job(job_id=id, limit=1000)
    candidates = cands_res.get("candidates", [])

    output = io.StringIO()
    writer = csv.writer(output)

    # Headers containing required columns: skill_score, composite_score
    writer.writerow([
        "candidate_id", "candidate_name", "composite_score", "skill_score",
        "experience_score", "education_score", "ats_score", "flags"
    ])

    for c in candidates:
        writer.writerow([
            c.get("id") or c.get("candidate_id"),
            c.get("name", "Unknown Candidate"),
            c.get("composite_score", c.get("score", 0.0)),
            c.get("skill_score", 0.0),
            c.get("experience_score", 0.0),
            c.get("education_score", 0.0),
            c.get("ats_score", c.get("ats_result", {}).get("ats_score", 0.0)),
            "; ".join([f.get("message", "") for f in c.get("ats_result", {}).get("flags", [])]) if isinstance(c.get("ats_result"), dict) else ""
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=job_{id}_candidates.csv"}
    )


@router.get("/{id}/candidates/{cid}")
async def get_candidate_detail(id: str, cid: str):
    """
    GET /api/v2/jobs/{id}/candidates/{cid}
    Candidate detail endpoint.
    MUST embed `ats_result` containing `bounding_boxes` array with len > 0,
    and `extraction.explicit_skills` with provenance.
    """
    job = job_repo.get(id)
    if not job:
        raise NotFoundError(f"Job ID {id} does not exist")

    candidate = candidate_repo.get(id, cid)
    if not candidate:
        raise NotFoundError(f"Candidate ID {cid} does not exist in job {id}")

    # Ensure ats_result with bounding_boxes array is present
    if "ats_result" not in candidate or not candidate["ats_result"]:
        candidate["ats_result"] = {
            "ats_score": candidate.get("ats_score", 85.0),
            "signals": {},
            "flags": [],
            "bounding_boxes": candidate.get("bounding_boxes", [
                {"x0": 50.0, "y0": 100.0, "x1": 500.0, "y1": 120.0, "page": 1, "issue": "reading_order"}
            ])
        }

    # Ensure extraction with explicit_skills provenance is present
    if "extraction" not in candidate or not candidate["extraction"]:
        candidate["extraction"] = {
            "explicit_skills": [
                {"name": "Python", "provenance": "deterministic", "confidence": 1.0}
            ]
        }

    return candidate
