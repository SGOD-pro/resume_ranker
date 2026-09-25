"""
jobs_v2.py — Job lifecycle API routes (API version: v2)
==========================================================
Public API prefix: /api/v2/jobs

Implements Phase 1 Architecture & Amendments:
1. Security: session ownership enforcement on every job route, max 100 files per job,
   max 20 jobs per session per day, no static credentials.
2. Terminal-state accounting: S1_FAILED, S2_DONE, S2_FAILED, REMOVED decrement remaining.
   POST /jobs/{id}/analyze accepts explicit file_ids list, marks others REMOVED.
   GET /jobs/{id}/status uses single DynamoDB query + ETag/304 short-polling + 10-minute stalling detection.
3. Presigned POST direct upload: content-length-range 1..10MB. Paginated when files > 50.
   /complete and /finalize endpoints permanently removed.
4. No WebSockets, no SSE.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, field_validator

from src.api.auth import AuthContext
from src.api.dependencies.auth import enforce_tenant_ownership, get_auth_context
from src.config.aws import get_settings
from src.core.lazy_proxy import LazyProxy
from src.infrastructure.audit import audit_logger
from src.infrastructure.models.file import (
    FileItem,
    FileStatus,
    TERMINAL_FILE_STATUSES,
)
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import (
    FINAL_RANK_QUEUE,
    ODL_BATCH_QUEUE,
    get_queue_adapter,
)
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.repositories.upload_sessions_repository import (
    UploadSessionsRepository,
)
from src.infrastructure.storage.storage_service import StorageService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Lazy-loaded Singletons ───────────────────────────────────────────────────
_jobs_repo = LazyProxy(JobsRepository)
_files_repo = LazyProxy(FilesRepository)
_docs_repo = LazyProxy(DocumentsRepository)
_sessions_repo = LazyProxy(UploadSessionsRepository)
_scoring_repo = LazyProxy(ScoringRepository)
_storage = LazyProxy(StorageService)
_scorer = LazyProxy(CandidateScorer)

# ── Guardrails & Caps ────────────────────────────────────────────────────────
MAX_FILES_PER_JOB = 100
MAX_JOBS_PER_SESSION_PER_DAY = 20

# In-memory sliding window for rate-limiting daily job creations per session
_session_job_timestamps: Dict[str, List[float]] = {}


def _check_and_record_daily_job_limit(session_id: str) -> None:
    now = time.time()
    cutoff = now - 86400.0  # 24 hours
    timestamps = _session_job_timestamps.setdefault(session_id, [])
    # Evict timestamps older than 24h
    timestamps[:] = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= MAX_JOBS_PER_SESSION_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "DAILY_JOB_LIMIT_EXCEEDED",
                "message": f"Daily job limit of {MAX_JOBS_PER_SESSION_PER_DAY} exceeded for this session.",
                "retry_after": 86400,
            },
            headers={"Retry-After": "86400"},
        )
    timestamps.append(now)


def get_session_id(request: Request, response: Optional[Response] = None) -> str:
    """Extract session_id from cookie or header; create new if absent."""
    session_id = request.cookies.get("job_session_id") or request.cookies.get("session_id")
    if not session_id:
        session_id = request.headers.get("X-Session-ID")
    if not session_id:
        session_id = str(uuid.uuid4())
        if response:
            response.set_cookie(
                key="job_session_id",
                value=session_id,
                httponly=True,
                samesite="lax",
                secure=False,
                max_age=86400 * 30,
            )
    return session_id


def enforce_session_ownership(job: JobItem, request: Request, ctx: Optional[AuthContext] = None) -> None:
    """Verify session or tenant ownership of the requested job."""
    # Allow logged-in users belonging to the same tenant org
    if ctx and ctx.org_id and ctx.org_id != "org_default" and ctx.org_id == getattr(job, "org_id", None):
        return

    caller_session = (
        request.cookies.get("job_session_id")
        or request.cookies.get("session_id")
        or request.headers.get("X-Session-ID")
    )
    job_session = getattr(job, "session_id", None)
    if job_session and caller_session and job_session != caller_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Access denied: session ownership mismatch."},
        )


# ── Schemas ──────────────────────────────────────────────────────────────────

class FileUploadSpec(BaseModel):
    filename: str
    file_size: int = 0
    content_type: str = "application/pdf"


class PresignedPostInfo(BaseModel):
    file_id: str
    filename: str
    s3_key: str
    presigned_post: Dict[str, Any]


class CreateJobRequest(BaseModel):
    title: str = "Candidate Screening"
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
        "skills": 0.40,
        "experience": 0.25,
        "keywords": 0.20,
        "education": 0.15,
    })
    files: List[FileUploadSpec] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    id: str
    title: str
    status: str
    total_files: int
    remaining: int
    page: int
    page_size: int
    total_pages: int
    has_more: bool
    next_page: Optional[int] = None
    files: List[PresignedPostInfo]


class PaginatedPresignedPostsResponse(BaseModel):
    job_id: str
    page: int
    page_size: int
    total_files: int
    total_pages: int
    has_more: bool
    next_page: Optional[int] = None
    files: List[PresignedPostInfo]


class UpdateJobRequest(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    must_have_skills: Optional[List[str]] = None
    nice_to_have_skills: Optional[List[str]] = None
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    education_level: Optional[str] = None
    education_field: Optional[str] = None
    keywords: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None


class AnalyzeRequest(BaseModel):
    file_ids: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    title: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    must_have_skills: Optional[List[str]] = None
    nice_to_have_skills: Optional[List[str]] = None
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    education_level: Optional[str] = None
    education_field: Optional[str] = None
    keywords: Optional[List[str]] = None


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str
    remaining: int
    usable_files: int
    analyze_requested: bool
    message: str


class ScoreRequest(BaseModel):
    weights: dict

    @field_validator("weights")
    @classmethod
    def weights_must_sum_to_100(cls, v: dict) -> dict:
        total = sum(v.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f"Weights must sum to 100, got {total}")
        return v


class DecisionUpdateRequest(BaseModel):
    decision: Optional[str] = None
    reason: Optional[str] = None
    note: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: CreateJobRequest,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new screening job and return presigned POST data for direct-to-S3 upload.

    - Content-length-range 1..10MB enforced via S3 policy.
    - Max 100 files per job; max 20 jobs per day.
    - Paginates if file count > 50.
    """
    if len(body.files) > MAX_FILES_PER_JOB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "FILE_LIMIT_EXCEEDED",
                "message": f"Requested {len(body.files)} files exceeds limit of {MAX_FILES_PER_JOB} files per job.",
            },
        )

    session_id = get_session_id(request, response)
    _check_and_record_daily_job_limit(session_id)

    job_id = str(uuid.uuid4())
    total_files = len(body.files)

    job = JobItem(
        job_id=job_id,
        org_id=ctx.org_id,
        session_id=session_id,
        title=body.title or "Candidate Screening",
        department=body.department,
        description=body.description,
        must_have_skills=body.must_have_skills,
        nice_to_have_skills=body.nice_to_have_skills,
        min_years=body.min_years,
        max_years=body.max_years,
        education_level=body.education_level,
        education_field=body.education_field,
        keywords=body.keywords,
        weights=body.weights,
        status=JobStatus.UPLOADING if total_files > 0 else JobStatus.CREATED,
        total_files=total_files,
        remaining=total_files,
        usable_files=0,
    )
    _jobs_repo.create(job)

    file_items: List[FileItem] = []
    presigned_infos: List[PresignedPostInfo] = []

    for f in body.files:
        file_id = str(uuid.uuid4())
        s3_key = f"jobs/{job_id}/raw/{file_id}.pdf"
        post_data = _storage.generate_presigned_post(
            s3_key=s3_key,
            content_type=f.content_type or "application/pdf",
            min_bytes=1,
            max_bytes=10 * 1024 * 1024,
            expires_in=3600,
        )

        item = FileItem(
            job_id=job_id,
            file_id=file_id,
            filename=f.filename,
            file_size=f.file_size,
            status=FileStatus.PENDING_UPLOAD,
            s3_raw_key=s3_key,
        )
        file_items.append(item)
        presigned_infos.append(
            PresignedPostInfo(
                file_id=file_id,
                filename=f.filename,
                s3_key=s3_key,
                presigned_post=post_data,
            )
        )

    if file_items:
        _files_repo.create_files(job_id, file_items)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "JOB_CREATED",
        "job",
        job_id,
        {"title": job.title, "total_files": total_files, "session_id": session_id},
    )

    page_size = 50
    total_pages = max(1, math.ceil(total_files / page_size)) if total_files > 0 else 1
    has_more = total_files > page_size
    returned_files = presigned_infos[:page_size]

    return CreateJobResponse(
        job_id=job_id,
        id=job_id,
        title=job.title,
        status=job.status.value,
        total_files=total_files,
        remaining=job.remaining,
        page=1,
        page_size=page_size,
        total_pages=total_pages,
        has_more=has_more,
        next_page=2 if has_more else None,
        files=returned_files,
    )


@router.get("/{job_id}/presigned-posts", response_model=PaginatedPresignedPostsResponse)
async def get_presigned_posts(
    job_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve paginated presigned POST endpoints for large batches (>50 files)."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    all_files = _files_repo.list_files_for_job(job_id)
    total_files = len(all_files)
    total_pages = max(1, math.ceil(total_files / page_size)) if total_files > 0 else 1

    start = (page - 1) * page_size
    end = start + page_size
    page_slice = all_files[start:end]

    infos: List[PresignedPostInfo] = []
    for f in page_slice:
        post_data = _storage.generate_presigned_post(
            s3_key=f.s3_raw_key,
            min_bytes=1,
            max_bytes=10 * 1024 * 1024,
            expires_in=3600,
        )
        infos.append(
            PresignedPostInfo(
                file_id=f.file_id,
                filename=f.filename,
                s3_key=f.s3_raw_key,
                presigned_post=post_data,
            )
        )

    has_more = end < total_files
    return PaginatedPresignedPostsResponse(
        job_id=job_id,
        page=page,
        page_size=page_size,
        total_files=total_files,
        total_pages=total_pages,
        has_more=has_more,
        next_page=page + 1 if has_more else None,
        files=infos,
    )


@router.patch("/{job_id}")
async def update_job(
    job_id: str,
    body: UpdateJobRequest,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update JD configuration for an existing job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"id": job_id, "config": {}, "status": "unchanged"}

    updates["job_version"] = getattr(job, "job_version", 1) + 1
    updated_job = _jobs_repo.update(job_id, updates, expected_version=job.version)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "JOB_UPDATED",
        "job",
        job_id,
        {"updated_fields": list(updates.keys()), "job_version": updates["job_version"]},
    )
    return {"id": job_id, "config": updates, "status": "updated"}


@router.post(
    "/{job_id}/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/{job_id}/analysis",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_job(
    job_id: str,
    request: Request,
    body: Optional[AnalyzeRequest] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Recruiter Analyze trigger (Amendment 2).

    - Payload carries explicit file_ids; unselected files are marked REMOVED.
    - Ready fallback files enter Stage 2.
    - Sets analyze_requested = True.
    - Triggers scoring when remaining == 0.
    - Returns HTTP 202 Accepted in < 1 second.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    req = body or AnalyzeRequest()

    # Update weights or criteria if supplied
    updates: Dict[str, Any] = {}
    if req.weights:
        w_sum = sum(req.weights.values())
        if abs(w_sum - 100) > 0.01:
            raise HTTPException(status_code=400, detail=f"Weights must sum to 100%, got {w_sum}%")
        updates["weights"] = req.weights

    if req.title and req.title != job.title:
        updates["title"] = req.title
    if req.department and req.department != job.department:
        updates["department"] = req.department
    if req.description and req.description != job.description:
        updates["description"] = req.description
    if req.must_have_skills is not None:
        updates["must_have_skills"] = req.must_have_skills
    if req.nice_to_have_skills is not None:
        updates["nice_to_have_skills"] = req.nice_to_have_skills
    if req.min_years is not None:
        updates["min_years"] = req.min_years
    if req.max_years is not None:
        updates["max_years"] = req.max_years
    if req.education_level is not None:
        updates["education_level"] = req.education_level
    if req.education_field is not None:
        updates["education_field"] = req.education_field
    if req.keywords is not None:
        updates["keywords"] = req.keywords

    if updates:
        job = _jobs_repo.update(job_id, updates, expected_version=job.version)

    # Determine explicit file IDs
    all_files = _files_repo.list_files_for_job(job_id)
    if req.file_ids is not None:
        selected_file_ids = req.file_ids
    else:
        selected_file_ids = [f.file_id for f in all_files if f.status != FileStatus.REMOVED]

    # Execute request_analysis (conditionally marks REMOVED, advances fallback, triggers scoring if remaining == 0)
    updated_job = _jobs_repo.request_analysis(job_id, selected_file_ids)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "ANALYSIS_REQUESTED",
        "job",
        job_id,
        {"selected_files_count": len(selected_file_ids), "remaining": updated_job.remaining},
    )

    return AnalyzeResponse(
        job_id=job_id,
        status=updated_job.status.value,
        remaining=updated_job.remaining,
        usable_files=updated_job.usable_files,
        analyze_requested=True,
        message="Analysis requested. Pipeline executing.",
    )


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: str,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Short-polling endpoint with ETag/304 and 10-minute stalling detection.

    Uses a single DynamoDB query (PK=JOB#{job_id}) to fetch METADATA and all FILE# items.
    """
    job, files = _jobs_repo.get_job_with_files(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    # Compute deterministic ETag over status, remaining counter, and last update
    etag_input = f"{job.status.value}:{job.remaining}:{job.usable_files}:{job.updated_at}:{len(files)}"
    etag = f'"{hashlib.sha256(etag_input.encode("utf-8")).hexdigest()[:16]}"'

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Cache-Control": "private, no-cache"},
        )

    is_stalled = job.is_stalled(threshold_seconds=600)

    file_summaries = [
        {
            "file_id": f.file_id,
            "filename": f.filename,
            "status": f.status.value,
            "candidate_name": f.candidate_name,
            "needs_fallback": f.needs_fallback,
            "low_confidence_extraction": getattr(f, "low_confidence_extraction", False),
            "fallback_reason": getattr(f, "fallback_reason", None),
            "error_message": f.error_message,
        }
        for f in files
    ]

    payload = {
        "job_id": job.job_id,
        "status": job.status.value,
        "total_files": job.total_files,
        "remaining": job.remaining,
        "usable_files": job.usable_files,
        "analyze_requested": job.analyze_requested,
        "is_stalled": is_stalled,
        "updated_at": job.updated_at,
        "files": file_summaries,
    }

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    return payload


@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve scored candidates from jobs/{job_id}/results.json."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    try:
        resp = _storage._client.get_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/results.json")
        body = resp["Body"].read().decode("utf-8")
        results_data = json.loads(body)
        candidates = results_data.get("candidates", [])
        for c in candidates:
            doc_id = c.get("document_id") or c.get("_document_id") or c.get("candidate_id")
            if doc_id:
                c["document_id"] = doc_id
                c["job_id"] = job_id
                if not c.get("pdf_url"):
                    c["pdf_url"] = f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download"
        results_data["candidates"] = candidates
        return results_data
    except Exception as e:
        logger.info("Results JSON not yet available for job %s: %s", job_id, e)
        # Return fallback empty shape if still in progress
        return {
            "job_id": job_id,
            "status": job.status.value,
            "total_candidates": 0,
            "candidates": [],
        }


@router.get("/{job_id}/resumes/{document_id}/download")
async def download_resume(
    job_id: str,
    document_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Download candidate resume PDF directly from S3."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    file_item = _files_repo.get_file(job_id, document_id)
    s3_key = file_item.s3_raw_key if file_item else f"jobs/{job_id}/raw/{document_id}.pdf"

    try:
        pdf_bytes = _storage.get_resume(job_id, document_id, s3_key=s3_key)
    except Exception as e:
        logger.error("Failed to download resume %s: %s", document_id, e)
        raise HTTPException(status_code=404, detail="Resume PDF not found in storage.")

    filename = (file_item.filename if file_item else None) or f"{document_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
async def delete_job(
    job_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Cascading deletion of job and all associated files, extractions, and scores."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    _jobs_repo.delete(job_id)

    try:
        prefix = f"jobs/{job_id}/"
        resp = _storage._client.list_objects_v2(Bucket=_storage._bucket, Prefix=prefix)
        if "Contents" in resp:
            delete_objects = [{"Key": obj["Key"]} for obj in resp["Contents"]]
            _storage._client.delete_objects(Bucket=_storage._bucket, Delete={"Objects": delete_objects})
    except Exception as e:
        logger.warning("Error purging S3 prefix for job %s: %s", job_id, e)

    audit_logger.record(ctx.org_id, ctx.user_id, "JOB_DELETED", "job", job_id)
    return {"status": "deleted", "message": f"Job {job_id} and all related data deleted."}


@router.delete("/{job_id}/resumes/{document_id}", status_code=status.HTTP_200_OK)
async def delete_resume(
    job_id: str,
    document_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Mark a resume as REMOVED and purge its raw S3 object."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    _files_repo.transition_file_terminal(
        job_id=job_id,
        file_id=document_id,
        terminal_status=FileStatus.REMOVED.value,
        error_message="User deleted resume",
    )

    try:
        _storage._client.delete_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/raw/{document_id}.pdf")
    except Exception as e:
        logger.warning("Error deleting S3 raw key for doc %s: %s", document_id, e)

    audit_logger.record(ctx.org_id, ctx.user_id, "DOCUMENT_DELETED", "document", document_id, {"job_id": job_id})
    return {"status": "deleted", "message": f"Document {document_id} removed."}


@router.patch("/{job_id}/candidates/{document_id}/decision")
async def update_candidate_decision(
    job_id: str,
    document_id: str,
    body: DecisionUpdateRequest,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update human recruiter decision state."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    valid_decisions = ("new", "reviewing", "shortlisted", "rejected", "interview", "archived")
    raw_decision = (body.decision or "").strip().lower()
    if raw_decision and raw_decision not in valid_decisions:
        raise HTTPException(status_code=400, detail=f"Invalid decision state. Must be one of: {valid_decisions}")

    if raw_decision == "rejected" and not (body.reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Non-negotiable policy: Rejections require a documented, evidence-backed reason.",
        )

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "DECISION_UPDATED",
        "candidate",
        document_id,
        {"job_id": job_id, "decision": raw_decision, "reason": body.reason, "note": body.note},
    )
    return {
        "job_id": job_id,
        "document_id": document_id,
        "decision": raw_decision,
        "reason": body.reason,
        "note": body.note,
        "status": "updated",
    }


@router.get("/{job_id}/export/csv")
async def export_job_csv(
    job_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Export candidate rankings for a job in standard CSV format."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    candidates = []
    try:
        resp = _storage._client.get_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/results.json")
        body = resp["Body"].read().decode("utf-8")
        candidates = json.loads(body).get("candidates", [])
    except Exception:
        candidates = []

    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Name", "Email", "Phone", "Match Score", "Signal",
        "Skills Score", "Experience Score", "Keywords Score", "Education Score",
        "Knocked Out", "Knockout Reasons",
    ])

    for i, c in enumerate(candidates):
        score = c.get("final_score", 0.0)
        signal = "Knockout" if c.get("knocked_out") else ("Strong" if score >= 75 else ("Good" if score >= 50 else "Fair"))
        writer.writerow([
            c.get("rank", i + 1),
            c.get("name", "Unknown"),
            c.get("email", ""),
            c.get("phone", ""),
            f"{score:.1f}",
            signal,
            f"{c.get('skill_score', 0.0):.1f}",
            f"{c.get('experience_score', 0.0):.1f}",
            f"{c.get('keyword_score', 0.0):.1f}",
            f"{c.get('education_score', 0.0):.1f}",
            "YES" if c.get("knocked_out") else "NO",
            "; ".join(c.get("knockout_reasons", [])),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sortlist_job_{job_id[:8]}_export.csv"'},
    )
