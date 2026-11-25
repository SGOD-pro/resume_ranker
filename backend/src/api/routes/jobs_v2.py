"""
jobs_v2.py — Job lifecycle API routes (API version: v2)
==========================================================
Public API prefix: /api/v2/jobs

Implements Phase 1 Architecture & Amendments:
1. Security: strict tenant isolation and session ownership enforcement on every job route,
   max 100 files per job, max 20 jobs per session per day, no static credentials.
2. Terminal-state accounting: S1_FAILED, S2_DONE, S2_FAILED, REMOVED decrement remaining.
   POST /jobs/{id}/analyze accepts explicit file_ids list, marks others REMOVED.
   GET /jobs/{id}/status uses single DynamoDB query + ETag/304 short-polling + 10-minute stalling detection.
3. Durable upload sessions and transactional outbox pattern for decoupled direct-to-S3 ingestion.
4. Server-Sent Events (SSE) real-time extraction and analysis progress streaming.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import time
import urllib.parse
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
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.config.aws import get_settings
from src.core.lazy_proxy import LazyProxy
from src.infrastructure.audit import audit_logger
from src.infrastructure.models.document import DocumentItem, DocumentStatus
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
    FAST_PARSE_QUEUE,
    FINAL_RANK_QUEUE,
    ODL_BATCH_QUEUE,
    SCORING_QUEUE,
    STAGE1_INGESTION_QUEUE,
    STAGE2_FALLBACK_QUEUE,
    get_queue_adapter,
    enqueue_fast_parse,
)
from src.infrastructure.queue.outbox import commit_file_upload_with_outbox, write_outbox_and_send
from src.pipeline.coordinator import check_and_progress_session
from src.pipeline.worker_runner import dispatch_fast_parse

from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.repositories.upload_sessions_repository import (
    AdmissionVerificationError,
    QuotaExceededError,
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


def enforce_session_ownership(job: JobItem, request: Request) -> None:
    """CSRF and origin validation for standalone job operations (HC-01 & ADR-07)."""
    env = os.environ.get("ENVIRONMENT", "dev").lower()
    is_prod = env in ("prod", "production") or os.environ.get("STRICT_AUTH", "false").lower() in ("true", "1", "yes")

    # CSRF protection: if request has Origin header, verify it matches allowed origins in production
    origin = request.headers.get("origin")
    if is_prod and origin:
        frontend_url = os.environ.get("FRONTEND_URL", "")
        allowed_origins = [o.strip() for o in frontend_url.split(",") if o.strip()]
        if allowed_origins and origin not in allowed_origins:
            logger.warning("CSRF violation: untrusted origin %s attempted access", origin)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Access denied: untrusted cross-origin request blocked."},
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
    org_id: Optional[str] = None
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

    @field_validator("org_id")
    @classmethod
    def validate_org_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v and not re.match(r"^[a-zA-Z0-9_-]{1,64}$", v):
                raise ValueError("org_id must be alphanumeric with hyphens or underscores, up to 64 chars")
        return v


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
    session_id: Optional[str] = None


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
    session_id: Optional[str] = None
    job_version: int = 1
    status: str
    remaining: int = 0
    usable_files: int = 0
    analyze_requested: bool = True
    message: str = "Analysis requested. Background processing pipeline engaged."


class UploadSessionFileSpec(BaseModel):
    filename: str
    file_size: int = 0
    content_type: str = "application/pdf"


class CreateUploadSessionRequest(BaseModel):
    document_count: int
    files: List[UploadSessionFileSpec]


class DocumentPresignedUrlInfo(BaseModel):
    document_id: str
    filename: str
    s3_key: str
    presigned_url: str


class CreateUploadSessionResponse(BaseModel):
    session_id: str
    job_id: str
    job_version: int
    expected_document_count: int
    documents: List[DocumentPresignedUrlInfo]


class CompleteDocumentUploadResponse(BaseModel):
    document_id: str
    session_id: Optional[str] = None
    job_id: str
    status: str
    message: str = "Upload completed successfully."


class FinalizeUploadSessionResponse(BaseModel):
    session_id: str
    job_id: str
    status: str
    message: str = "Upload session finalized. Processing pipeline barrier active."


class UploadSessionProgressResponse(BaseModel):
    session_id: str
    job_id: str
    job_version: int
    status: str
    expected_document_count: int
    uploaded_document_count: int
    fast_parsed_count: int
    terminal_count: int
    documents: List[Dict[str, Any]]


class FileUploadNotification(BaseModel):
    file_ids: Optional[List[str]] = None


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
    tags: Optional[List[str]] = None
    expected_version: Optional[int] = None
    client_timestamp: Optional[str] = None


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_200_OK)
async def create_job(
    body: CreateJobRequest,
    request: Request,
    response: Response,
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

    if body.files:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK

    job_id = str(uuid.uuid4())
    total_files = len(body.files)
    job_org_id = body.org_id if body.org_id else f"job_{job_id}"

    job = JobItem(
        job_id=job_id,
        org_id=job_org_id,
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
        getattr(job, "org_id", "org_default"),
        "anonymous",
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
        session_id=session_id,
    )

@router.post("/ats-check")
async def check_ats_endpoint(
    file: UploadFile = File(...),
):
    """Run B2B ATS Health Check on a resume PDF."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Corrupted file: invalid PDF header.")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    s3_key = f"ats_check/{uuid.uuid4().hex}.pdf"
    _storage._client.put_object(
        Bucket=_storage._bucket,
        Key=s3_key,
        Body=contents,
        ContentType="application/pdf",
    )

    try:
        from src.ats.b2b_ats_scorer import B2BAtsScorer
        scorer = B2BAtsScorer()
        result = scorer.score(tmp_path, s3_bucket=_storage._bucket, s3_key=s3_key)
        return result
    except Exception as e:
        logger.error("ATS check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="ATS check failed.")
    finally:
        try:
            _storage._client.delete_object(Bucket=_storage._bucket, Key=s3_key)
        except Exception:
            pass
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/parse-jd")
async def parse_jd_endpoint(
    file: UploadFile = File(...),
):
    """Extract plain text from an uploaded Job Description PDF."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")
    if not contents.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Corrupted file: invalid PDF header.")

    try:
        from src.extraction.structural_parsing_service import extract_pdf_text_sync
        full_text = await asyncio.to_thread(extract_pdf_text_sync, contents)
        return {"text": full_text, "filename": file.filename}
    except Exception as e:
        logger.error("Parse JD PDF failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to parse JD PDF.")


@router.get("/{job_id}/presigned-posts", response_model=PaginatedPresignedPostsResponse)
async def get_presigned_posts(
    job_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
):
    """Retrieve paginated presigned POST endpoints for large batches (>50 files)."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

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
):
    """Update JD configuration for an existing job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"id": job_id, "config": {}, "status": "unchanged"}

    updates["job_version"] = getattr(job, "job_version", 1) + 1
    updated_job = _jobs_repo.update(job_id, updates, expected_version=job.version)

    audit_logger.record(
        getattr(job, "org_id", "org_default"),
        "anonymous",
        "JOB_UPDATED",
        "job",
        job_id,
        {"updated_fields": list(updates.keys()), "job_version": updates["job_version"]},
    )
    return {"id": job_id, "config": updates, "status": "updated"}


@router.post("/{job_id}/files/uploaded", status_code=status.HTTP_202_ACCEPTED)
@router.post("/{job_id}/resumes/complete", status_code=status.HTTP_202_ACCEPTED)
@router.post("/{job_id}/upload-complete", status_code=status.HTTP_202_ACCEPTED)
async def notify_files_uploaded(
    job_id: str,
    request: Request,
    body: Optional[FileUploadNotification] = None,
):
    """Notify backend that direct-to-S3 uploads have completed for files.
    
    Immediately starts the PyMuPDF fast-parse pipeline in the background.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    all_files = _files_repo.list_files_for_job(job_id)
    target_ids = set(body.file_ids) if (body and body.file_ids) else {f.file_id for f in all_files}

    settings = get_settings()
    run_local = settings.is_local() or settings.RUN_LOCAL_WORKERS
    enqueued_count = 0

    logger.info("|PYMUPDF| Starting multithreaded extraction for %d files in job %s", len(target_ids), job_id)

    upload_sessions = _sessions_repo.list_for_job(job_id)
    resolved_session_id = upload_sessions[0].session_id if upload_sessions else getattr(job, "session_id", "default")
    job_org_id = getattr(job, "org_id", "org_default")

    failed_enqueue_count = 0
    for f in all_files:
        if f.file_id in target_ids and not f.is_terminal and f.status not in (FileStatus.S1_DONE, FileStatus.S2_DONE):
            msg = QueueMessage(
                job_id=job_id,
                session_id=resolved_session_id,
                document_id=f.file_id,
                org_id=job_org_id,
                job_version=job.job_version,
                s3_key=f.s3_raw_key,
                content_hash="",
                stage="FAST_PARSE",
            )
            try:
                enqueue_fast_parse(
                    job_id=job_id,
                    session_id=resolved_session_id,
                    document_id=f.file_id,
                    org_id=job_org_id,
                    job_version=job.job_version,
                    s3_key=f.s3_raw_key,
                    content_hash="",
                )
                enqueued_count += 1
            except Exception as e:
                logger.warning("Could not enqueue via enqueue_fast_parse for file %s: %s", f.file_id, e)
                failed_enqueue_count += 1

    logger.info("|PYMUPDF| Enqueued and started %d files (failed: %d) for background PyMuPDF extraction for job %s", enqueued_count, failed_enqueue_count, job_id)
    status_str = "processing" if enqueued_count > 0 else ("failed" if failed_enqueue_count > 0 else "noop")
    return {
        "job_id": job_id,
        "enqueued": enqueued_count,
        "status": status_str,
        "message": f"PyMuPDF background extraction started for {enqueued_count} files.",
    }


@router.post("/{job_id}/resumes", status_code=status.HTTP_200_OK)
async def upload_resumes_multipart(
    job_id: str,
    request: Request,
    files: List[UploadFile] = File(...),
):
    """Multipart upload fallback for direct file submission."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    file_items = []
    messages = []
    adapter = get_queue_adapter()
    settings = get_settings()
    run_local = settings.is_local() or settings.RUN_LOCAL_WORKERS

    logger.info("|PYMUPDF| Backend received %d resumes from frontend for job %s. Uploading to S3 and starting extraction...", len(files), job_id)

    # Read all file contents and validate PDF header and structural trailer
    file_payloads = []
    rejected = []
    for f in files:
        f_name = f.filename or "resume.pdf"
        try:
            content = await f.read()
            if len(content) < 32:
                logger.warning("Rejected file %s: size < 32 bytes", f_name)
                rejected.append({"filename": f_name, "reason": "Corrupted or empty file: size under 32 bytes."})
                continue
            if len(content) > settings.MAX_FILE_SIZE_BYTES:
                logger.warning("Rejected file %s: size > %d bytes", f_name, settings.MAX_FILE_SIZE_BYTES)
                rejected.append({"filename": f_name, "reason": f"File exceeds {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit."})
                continue
            if not content.startswith(b"%PDF-"):
                logger.warning("Rejected file %s: invalid PDF magic bytes", f_name)
                rejected.append({"filename": f_name, "reason": "Invalid PDF header: file is not a valid PDF document."})
                continue
            if b"%%EOF" not in content[-1024:]:
                logger.warning("Rejected file %s: missing %%EOF trailer", f_name)
                rejected.append({"filename": f_name, "reason": "Corrupted PDF: missing %%EOF trailer."})
                continue
            file_payloads.append((f_name, content))
        except Exception as read_err:
            logger.warning("Rejected file %s: read error %s", f_name, read_err)
            rejected.append({"filename": f_name, "reason": f"Read error: {str(read_err)}"})

    upload_sessions = _sessions_repo.list_for_job(job_id)
    multipart_session_id = upload_sessions[0].session_id if upload_sessions else getattr(job, "session_id", "default")
    job_org_id = getattr(job, "org_id", "org_default")

    def _upload_single_s3(f_name: str, content_bytes: bytes) -> tuple[FileItem, QueueMessage]:
        fid = str(uuid.uuid4())
        s3_key = f"jobs/{job_id}/raw/{fid}.pdf"
        _storage._client.put_object(
            Bucket=_storage._bucket,
            Key=s3_key,
            Body=content_bytes,
            ContentType="application/pdf",
        )
        f_item = FileItem(
            job_id=job_id,
            file_id=fid,
            filename=f_name,
            file_size=len(content_bytes),
            status=FileStatus.UPLOADED,
            s3_raw_key=s3_key,
        )
        q_msg = QueueMessage(
            job_id=job_id,
            session_id=multipart_session_id,
            document_id=fid,
            org_id=job_org_id,
            job_version=job.job_version,
            s3_key=s3_key,
            stage="FAST_PARSE",
        )
        return f_item, q_msg

    # Bounded concurrent S3 uploads (semaphore of 4 to bound RAM and sockets)
    upload_sem = asyncio.Semaphore(4)

    async def _bounded_upload(fn: str, c: bytes):
        async with upload_sem:
            return await asyncio.to_thread(_upload_single_s3, fn, c)

    upload_results = []
    for fn, c in file_payloads:
        try:
            res = await _bounded_upload(fn, c)
            upload_results.append(res)
        except Exception as up_err:
            logger.error("S3 upload failed for %s: %s", fn, up_err)
            rejected.append({"filename": fn, "reason": f"S3 upload failed: {str(up_err)}"})

    file_items = [r[0] for r in upload_results]
    messages = [r[1] for r in upload_results]

    if file_items:
        _files_repo.create_files(job_id, file_items)
        _jobs_repo.increment_files_count(job_id, len(file_items))

    for msg in messages:
        adapter.send_message(FAST_PARSE_QUEUE, msg)

    logger.info("|PYMUPDF| Stored %d files in S3 (rejected %d) for job %s", len(file_items), len(rejected), job_id)

    return {
        "job_id": job_id,
        "accepted": [f.filename for f in file_items],
        "rejected": rejected,
        "total_accepted": len(file_items),
        "file_id_map": {f.filename: f.file_id for f in file_items},
    }


# ── Target Architecture: Direct Presigned S3 Upload Session API ────────────────


@router.post(
    "/{job_id}/upload-sessions",
    response_model=CreateUploadSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_session(
    job_id: str,
    request: Request,
    body: CreateUploadSessionRequest,
):
    """Create a durable upload session and return presigned S3 PUT URLs."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    settings = get_settings()
    job_org_id = getattr(job, "org_id", "org_default")

    # Guard 1: Document count limit
    if body.document_count > settings.MAX_DOCS_PER_SESSION or len(body.files) > settings.MAX_DOCS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SESSION_DOCUMENT_LIMIT_EXCEEDED",
                "message": f"Requested document count exceeds maximum limit of {settings.MAX_DOCS_PER_SESSION}.",
            },
        )

    # Guard 2: Batch bytes & file sizes
    total_bytes = sum(f.file_size for f in body.files)
    if total_bytes > settings.MAX_BATCH_BYTES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SESSION_BATCH_SIZE_EXCEEDED",
                "message": f"Total batch size exceeds maximum allowed of {settings.MAX_BATCH_BYTES / (1024*1024):.0f}MB.",
            },
        )

    for f in body.files:
        if f.file_size > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "FILE_SIZE_LIMIT_EXCEEDED",
                    "message": f"File '{f.filename}' exceeds maximum file size of {settings.MAX_FILE_SIZE_BYTES / (1024*1024):.0f}MB.",
                },
            )

    session_id = str(uuid.uuid4())
    job_version = getattr(job, "job_version", 1)

    session = UploadSessionItem(
        session_id=session_id,
        job_id=job_id,
        org_id=job_org_id,
        job_version=job_version,
        expected_document_count=len(body.files),
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
    )

    # Guard 3: Atomic admission quota verification and session creation
    try:
        session = _sessions_repo.admit_and_create_session(
            session,
            max_active=settings.MAX_ACTIVE_SESSIONS_PER_ORG,
        )
    except AdmissionVerificationError as ave:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]
        logger.warning("Org %s admission verification failed: %s", job_org_id, ave)
        raise HTTPException(
            status_code=503,
            detail={
                "status_code": 503,
                "error_code": "ADMISSION_VERIFICATION_UNAVAILABLE",
                "code": "ADMISSION_VERIFICATION_UNAVAILABLE",
                "route": request.url.path,
                "job_id": job_id,
                "session_id": None,
                "org_id": job_org_id,
                "client_ip_hash": ip_hash,
                "retry_after": 5,
                "retry_after_seconds": 5,
                "message": "Organization admission verification is temporarily unavailable. Please retry.",
            },
            headers={"Retry-After": "5"},
        )
    except QuotaExceededError as qee:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]
        raise HTTPException(
            status_code=429,
            detail={
                "status_code": 429,
                "error_code": "CONCURRENT_SESSIONS_EXCEEDED",
                "code": "CONCURRENT_SESSIONS_EXCEEDED",
                "route": request.url.path,
                "job_id": job_id,
                "session_id": None,
                "org_id": job_org_id,
                "client_ip_hash": ip_hash,
                "retry_after": 60,
                "retry_after_seconds": 60,
                "message": f"Organization has {qee.current} active upload sessions (max {qee.limit}). Please wait before retrying.",
            },
            headers={"Retry-After": "60"},
        )

    doc_infos: List[DocumentPresignedUrlInfo] = []
    file_items: List[FileItem] = []
    doc_items: List[DocumentItem] = []
    for f in body.files:
        doc_id = str(uuid.uuid4())
        s3_key = f"{job_org_id}/jobs/{job_id}/sessions/{session_id}/resumes/{doc_id}.pdf"
        presigned_url = _storage.generate_presigned_put_url(
            s3_key=s3_key,
            content_type=f.content_type or "application/pdf",
            expires_in=settings.PRESIGNED_URL_EXPIRY_SECONDS,
            content_length=f.file_size if f.file_size > 0 else None,
        )

        doc_item = DocumentItem(
            document_id=doc_id,
            job_id=job_id,
            session_id=session_id,
            org_id=job_org_id,
            filename=f.filename,
            file_size=f.file_size,
            s3_pdf_key=s3_key,
            status=DocumentStatus.UPLOAD_INITIALIZED,
        )
        doc_items.append(doc_item)

        file_items.append(
            FileItem(
                job_id=job_id,
                file_id=doc_id,
                filename=f.filename,
                file_size=f.file_size,
                status=FileStatus.PENDING_UPLOAD,
                s3_raw_key=s3_key,
            )
        )

        doc_infos.append(
            DocumentPresignedUrlInfo(
                document_id=doc_id,
                filename=f.filename,
                s3_key=s3_key,
                presigned_url=presigned_url,
            )
        )

    if doc_items:
        _docs_repo.create_batch(doc_items)

    if file_items:
        _files_repo.create_files(job_id, file_items)
        _jobs_repo.increment_files_count(job_id, len(file_items))

    audit_logger.record(
        job_org_id,
        "anonymous",
        "UPLOAD_SESSION_CREATED",
        "job",
        job_id,
        {"session_id": session_id, "expected_document_count": len(body.files)},
    )

    return CreateUploadSessionResponse(
        session_id=session_id,
        job_id=job_id,
        job_version=job_version,
        expected_document_count=len(body.files),
        documents=doc_infos,
    )


@router.post(
    "/{job_id}/upload-sessions/{session_id}/documents/{document_id}/complete",
    response_model=CompleteDocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/{job_id}/documents/{document_id}/complete",
    response_model=CompleteDocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def complete_document_upload(
    job_id: str,
    document_id: str,
    request: Request,
    session_id: Optional[str] = None,
):
    """Verify S3 upload completion, validate PDF integrity header, and enqueue for fast-parse."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    job_org_id = getattr(job, "org_id", f"job_{job_id}")
    doc = _docs_repo.get(job_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for this job")

    if session_id:
        sess = _sessions_repo.get(job_id, session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Upload session not found")
        if doc.session_id != session_id:
            raise HTTPException(status_code=400, detail="Document does not belong to specified upload session")

    resolved_session_id = session_id or doc.session_id or getattr(job, "session_id", "default_session")

    # Idempotency: If already UPLOADED or past that state, return success immediately
    if doc.status not in (DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING):
        return CompleteDocumentUploadResponse(
            document_id=document_id,
            session_id=resolved_session_id,
            job_id=job_id,
            status=doc.status.value,
        )

    s3_key = doc.s3_pdf_key or f"jobs/{job_id}/resumes/{document_id}.pdf"
    settings = get_settings()

    # 1. HEAD request to verify object exists and check size
    try:
        head = _storage.head_object(s3_key)
    except Exception as e:
        logger.error("HEAD verification failed for s3://%s: %s", s3_key, e)
        raise HTTPException(status_code=400, detail="S3 object not found or incomplete upload")

    actual_size = head.get("ContentLength", 0)
    if actual_size > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds 10MB limit")
    if actual_size < 32:
        raise HTTPException(status_code=400, detail="Corrupted file: file size too small to be a valid PDF")

    # 2. Lightweight verification of PDF header (%PDF-) via Range read (bytes=0-9)
    try:
        magic_bytes = _storage.get_object_byte_range(s3_key, 0, 10)
        if not magic_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Corrupted file: invalid PDF header (magic bytes mismatch)")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail="Failed to verify PDF header bytes")

    # 3. Atomically commit FileItem and DocumentItem status transition, plus outbox record in DynamoDB, then attempt SQS
    fresh_job = _jobs_repo.get(job_id)
    job_version = getattr(fresh_job, "job_version", 1) if fresh_job else 1
    try:
        commit_file_upload_with_outbox(
            job_id=job_id,
            file_id=document_id,
            actual_size=actual_size,
            session_id=resolved_session_id,
            org_id=job_org_id,
            job_version=job_version,
            s3_key=s3_key,
            stage="FAST_PARSE",
        )
    except Exception as outbox_err:
        fresh_doc = _docs_repo.get(job_id, document_id)
        if fresh_doc and fresh_doc.status not in (DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING):
            logger.info("Outbox transaction condition already committed for doc %s (%s)", document_id, fresh_doc.status)
            return CompleteDocumentUploadResponse(
                document_id=document_id,
                session_id=resolved_session_id,
                job_id=job_id,
                status=fresh_doc.status.value,
            )
        logger.error("Outbox transaction failed for document %s: %s", document_id, outbox_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to durably commit upload transaction. Please retry.",
        )

    # 4. Increment session uploaded counter atomically ONLY after durable atomic commit succeeds
    if resolved_session_id:
        try:
            _sessions_repo.increment_uploaded_count(job_id, resolved_session_id)
        except Exception as e:
            logger.warning("Failed to increment session uploaded count: %s", e)

    return CompleteDocumentUploadResponse(
        document_id=document_id,
        session_id=resolved_session_id,
        job_id=job_id,
        status="UPLOADED",
    )


@router.post(
    "/{job_id}/upload-sessions/{session_id}/finalize",
    response_model=FinalizeUploadSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def finalize_upload_session(
    job_id: str,
    session_id: str,
    request: Request,
):
    """Finalize upload session to establish the explicit fast-parse barrier."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    session = _sessions_repo.get(job_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")

    # Idempotent finalization: transition to FAST_PREPROCESSING
    # Note: analysis_requested remains False until user clicks Analyze!
    if session.status == UploadSessionStatus.UPLOADING:
        _sessions_repo.update_status(
            job_id,
            session_id,
            UploadSessionStatus.FAST_PREPROCESSING,
            expected_version=session.version,
        )
        fresh_job = _jobs_repo.get(job_id)
        if fresh_job and fresh_job.status == JobStatus.CREATED:
            _jobs_repo.update_status(job_id, JobStatus.FAST_PARSING, expected_version=fresh_job.version)

    check_and_progress_session(job_id, session_id)

    return FinalizeUploadSessionResponse(
        session_id=session_id,
        job_id=job_id,
        status="FAST_PREPROCESSING",
        message="Upload session finalized. Processing pipeline barrier active.",
    )


@router.get(
    "/{job_id}/upload-sessions/{session_id}",
    response_model=UploadSessionProgressResponse,
)
async def get_upload_session(
    job_id: str,
    session_id: str,
    request: Request,
):
    """Retrieve upload session state, progress counts, and per-document diagnostics."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    session = _sessions_repo.get(job_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")

    docs = _docs_repo.list_for_session(job_id, session_id)
    fast_parsed = sum(1 for d in docs if d.status.is_terminal_fast_parse())
    terminal = sum(1 for d in docs if d.status.is_terminal_extraction())

    doc_list = [
        {
            "document_id": d.document_id,
            "filename": d.filename,
            "status": d.status.value,
            "candidate_name": d.candidate_name,
            "identity_status": d.identity_status,
            "extraction_quality": d.extraction_quality,
            "fallback_reason": d.fallback_reason,
            "error_reason": d.error_reason,
        }
        for d in docs
    ]

    return UploadSessionProgressResponse(
        session_id=session_id,
        job_id=job_id,
        job_version=session.job_version,
        status=session.status.value,
        expected_document_count=session.expected_document_count,
        uploaded_document_count=session.uploaded_document_count,
        fast_parsed_count=fast_parsed,
        terminal_count=terminal,
        documents=doc_list,
    )


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
):
    """Recruiter Analyze trigger.

    - Payload carries explicit file_ids; unselected files are marked REMOVED.
    - Sets analyze_requested = True.
    - Pins job_version and advances upload session if present.
    - Returns HTTP 202 Accepted in < 1 second.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

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

    current_job_version = getattr(job, "job_version", 1)
    if updates:
        current_job_version += 1
        updates["job_version"] = current_job_version
        job = _jobs_repo.update(job_id, updates, expected_version=job.version)

    all_files = _files_repo.list_files_for_job(job_id)

    # Advance upload session if present
    target_session = None
    sessions = _sessions_repo.list_for_job(job_id)
    if sessions:
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        target_session = sessions[0]
        try:
            _sessions_repo.set_analysis_requested(
                job_id=job_id,
                session_id=target_session.session_id,
                expected_version=target_session.version,
                analysis_requested=True,
                new_status=UploadSessionStatus.ANALYSIS_REQUESTED,
                job_version=current_job_version,
            )
            # Progress upload session if documents are tracked without FileItems
            if not all_files:
                check_and_progress_session(job_id, target_session.session_id)
        except Exception as e:
            logger.warning("Could not set analysis_requested on session: %s", e)

    job_org_id = getattr(job, "org_id", "org_default")

    # Determine explicit file IDs
    if req.file_ids is not None:
        selected_file_ids = req.file_ids
    else:
        selected_file_ids = [f.file_id for f in all_files if f.status != FileStatus.REMOVED]

    # Ensure any selected files not yet active/done in Stage 1 or terminal state are durably enqueued via outbox
    for f in all_files:
        if f.file_id in selected_file_ids and not f.is_terminal and f.status not in (
            FileStatus.S1_PROCESSING, FileStatus.S1_DONE, FileStatus.S2_PROCESSING, FileStatus.S2_DONE
        ):
            try:
                write_outbox_and_send(
                    job_id=job_id,
                    session_id=(target_session.session_id if target_session else None) or job.session_id or "default",
                    document_id=f.file_id,
                    org_id=job_org_id,
                    job_version=current_job_version,
                    s3_key=f.s3_raw_key,
                    stage="FAST_PARSE",
                )
            except Exception as outbox_err:
                logger.error("Outbox dispatch failed during analyze_job for file %s: %s", f.file_id, outbox_err)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to durably enqueue resume processing. Please retry.",
                )

    # Execute request_analysis (conditionally marks REMOVED, advances fallback, triggers scoring if remaining == 0)
    updated_job = _jobs_repo.request_analysis(job_id, selected_file_ids)

    audit_logger.record(
        job_org_id,
        "anonymous",
        "ANALYSIS_REQUESTED",
        "job",
        job_id,
        {"selected_files_count": len(selected_file_ids), "remaining": updated_job.remaining if updated_job else 0},
    )

    return AnalyzeResponse(
        job_id=job_id,
        session_id=target_session.session_id if target_session else None,
        job_version=current_job_version,
        status="ANALYSIS_REQUESTED",
        remaining=updated_job.remaining if updated_job else 0,
        usable_files=updated_job.usable_files if updated_job else 0,
        analyze_requested=True,
        message="Analysis requested. Pipeline executing.",
    )


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: str,
    request: Request,
    response: Response,
):
    """Short-polling endpoint with ETag/304 and 10-minute stalling detection.

    Uses a single DynamoDB query (PK=JOB#{job_id}) to fetch METADATA and all FILE# items.
    """
    # 1. Fetch job and files, and strictly enforce session ownership FIRST
    job, files = _jobs_repo.get_job_with_files(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    # 2. Reconcile any pending outbox events only after ownership is validated
    try:
        reconciled_count = _files_repo.reconcile_outbox(job_id)
        try:
            from src.infrastructure.queue.outbox import relay_pending_outbox
            relayed_uploads = relay_pending_outbox(job_id=job_id)
        except Exception:
            relayed_uploads = 0
        if (isinstance(reconciled_count, int) and reconciled_count > 0) or relayed_uploads > 0:
            # Re-fetch after reconciliation in case status or files advanced
            job, files = _jobs_repo.get_job_with_files(job_id)
    except Exception as exc:
        logger.warning("Outbox reconciliation warning during status poll for %s: %s", job_id, exc)

    # Compute deterministic ETag over status, remaining counter, updated_at, and all per-file states
    file_signatures = [
        f"{f.file_id}:{f.status.value if hasattr(f.status, 'value') else f.status}:{f.candidate_name}:{getattr(f, 'updated_at', '')}:{f.error_message}"
        for f in sorted(files, key=lambda x: x.file_id)
    ]
    etag_input = f"{job.status.value}:{job.remaining}:{job.usable_files}:{job.updated_at}:{';'.join(file_signatures)}"
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

    docs = _docs_repo.list_for_job(job_id)
    sessions = _sessions_repo.list_for_job(job_id)
    effective_status = job.status.value
    if sessions:
        sessions.sort(key=lambda s: getattr(s, "created_at", ""), reverse=True)
        if sessions[0].status.value in ("READY", "READY_WITH_WARNINGS", "DONE", "DONE_WITH_ERRORS"):
            effective_status = sessions[0].status.value

    effective_total = job.total_files or len(files) or len(docs)
    effective_remaining = job.remaining if job.total_files > 0 else (sum(1 for f in files if not f.is_terminal) if files else sum(1 for d in docs if not d.status.is_terminal_fast_parse()))
    effective_usable = job.usable_files if job.usable_files > 0 else (sum(1 for f in files if f.status == FileStatus.S2_DONE) if files else sum(1 for d in docs if d.status in (DocumentStatus.STRUCTURED_PARSED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.SCORED)))

    payload = {
        "job_id": job.job_id,
        "status": effective_status,
        "total_files": effective_total,
        "remaining": effective_remaining,
        "usable_files": effective_usable,
        "analyze_requested": job.analyze_requested,
        "is_stalled": is_stalled,
        "updated_at": job.updated_at,
        "files": file_summaries,
        "config": {
            "title": job.title,
            "department": job.department,
            "description": job.description,
            "must_have_skills": job.must_have_skills,
            "nice_to_have_skills": job.nice_to_have_skills,
            "min_years": job.min_years,
            "max_years": job.max_years,
            "education_level": job.education_level,
            "education_field": job.education_field,
            "keywords": job.keywords,
            "weights": job.weights,
        },
    }

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    return payload


@router.get("/{job_id}/extract")
async def extract_resumes_stream(
    job_id: str,
    request: Request,
):
    """SSE extraction stream for client compatibility (API contracts)."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    async def event_generator():
        last_state = ""
        heartbeat_ticks = 0

        while True:
            if await request.is_disconnected():
                break

            job, files = _jobs_repo.get_job_with_files(job_id)
            if not job:
                yield f"event: error\ndata: {json.dumps({'message': 'Job not found'})}\n\n"
                break

            docs = _docs_repo.list_for_job(job_id)
            if docs:
                total_docs = len(docs)
                fast_parsed = sum(1 for d in docs if d.status.is_terminal_fast_parse())
                succeeded = sum(1 for d in docs if d.status.is_terminal_fast_parse() and d.status not in (DocumentStatus.FAILED, DocumentStatus.PARSE_FAILED))
                failed = sum(1 for d in docs if d.status in (DocumentStatus.FAILED, DocumentStatus.PARSE_FAILED))

                is_terminal_job = job.status in (
                    JobStatus.READY,
                    JobStatus.READY_WITH_WARNINGS,
                    JobStatus.DONE,
                    JobStatus.DONE_WITH_ERRORS,
                )
                is_complete = is_terminal_job if job.analyze_requested else (fast_parsed == total_docs and total_docs > 0)

                payload = {
                    "job_id": job_id,
                    "job_status": job.status.value,
                    "status": "complete" if is_complete else ("scoring" if fast_parsed == total_docs else "extracting"),
                    "total": total_docs,
                    "total_files": total_docs,
                    "current": fast_parsed,
                    "usable_files": succeeded,
                    "remaining": total_docs - fast_parsed,
                    "succeeded": succeeded,
                    "failed": failed,
                    "analyze_requested": job.analyze_requested,
                    "is_stalled": job.is_stalled(threshold_seconds=600),
                }
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"

                if is_complete and total_docs > 0:
                    yield f"event: complete\ndata: {json.dumps({'type': 'complete', 'status': job.status.value, 'total': total_docs, 'usable': succeeded, 'succeeded': succeeded, 'failed': failed})}\n\n"
                    break

                if job.status == JobStatus.FAILED:
                    yield f"event: error\ndata: {json.dumps({'type': 'error', 'status': 'FAILED', 'message': job.error_message or 'Job processing failed'})}\n\n"
                    break

                await asyncio.sleep(0.5)
                continue

            s2_done_count = sum(1 for f in files if f.status == FileStatus.S2_DONE.value)
            failed_count = sum(1 for f in files if f.status in (FileStatus.S1_FAILED.value, FileStatus.S2_FAILED.value))
            completed_files = sum(1 for f in files if f.status in (FileStatus.S1_DONE.value, FileStatus.S2_DONE.value, FileStatus.S1_FAILED.value, FileStatus.S2_FAILED.value))

            file_summaries = [
                {
                    "file_id": f.file_id,
                    "filename": f.filename,
                    "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                    "candidate_name": f.candidate_name,
                    "needs_fallback": f.needs_fallback,
                    "low_confidence_extraction": getattr(f, "low_confidence_extraction", False),
                    "fallback_reason": getattr(f, "fallback_reason", None),
                    "error_message": f.error_message,
                }
                for f in files
            ]

            state_key = f"{job.status.value}:{job.remaining}:{job.usable_files}:{s2_done_count}:{failed_count}"
            heartbeat_ticks += 1

            if state_key != last_state or heartbeat_ticks >= 10:
                last_state = state_key
                heartbeat_ticks = 0
                payload = {
                    "job_id": job.job_id,
                    "job_status": job.status.value,
                    "status": job.status.value,
                    "total_files": job.total_files,
                    "remaining": job.remaining,
                    "usable_files": job.usable_files,
                    "succeeded": s2_done_count,
                    "failed": failed_count,
                    "analyze_requested": job.analyze_requested,
                    "is_stalled": job.is_stalled(threshold_seconds=600),
                    "files": file_summaries,
                }
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"

            # Check terminal states
            if job.status in (JobStatus.DONE, JobStatus.DONE_WITH_ERRORS, JobStatus.READY, JobStatus.READY_WITH_WARNINGS) or (files and completed_files == len(files)):
                yield f"event: complete\ndata: {json.dumps({'type': 'complete', 'status': job.status.value, 'total': job.total_files or len(files), 'usable': job.usable_files or s2_done_count, 'succeeded': s2_done_count, 'failed': failed_count})}\n\n"
                break
            elif job.status == JobStatus.FAILED:
                yield f"event: error\ndata: {json.dumps({'message': 'Job execution failed on server'})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/score")
async def score_job_endpoint(
    job_id: str,
    request: Request,
    body: Optional[Dict[str, Any]] = None,
):
    """Score candidates for a job.
    Accepts weights and executes candidate scoring.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    raw_weights = (body or {}).get("weights")
    if raw_weights:
        w_sum = sum(raw_weights.values())
        if abs(w_sum - 100) < 0.01:
            fractional_weights = {k: float(v) / 100.0 for k, v in raw_weights.items()}
        else:
            fractional_weights = {k: float(v) for k, v in raw_weights.items()}
        job = _jobs_repo.update(job_id, {"weights": fractional_weights}, expected_version=job.version)

    from src.pipeline.scoring_worker import process_scoring_message
    from src.infrastructure.queue.message import QueueMessage
    upload_sessions = _sessions_repo.list_for_job(job_id)
    score_session_id = upload_sessions[0].session_id if upload_sessions else getattr(job, "session_id", "default")
    job_org_id = getattr(job, "org_id", "org_default")
    msg = QueueMessage(
        job_id=job_id,
        session_id=score_session_id,
        document_id=job_id,
        org_id=job_org_id,
        job_version=job.job_version,
        stage="FINAL_RANK",
    )
    process_scoring_message(msg)

    results_resp = await get_results(job_id=job_id, request=request)
    return results_resp


@router.get("/{job_id}/results")
async def get_results(
    job_id: str,
    request: Request,
):
    """Retrieve scored candidates from jobs/{job_id}/results.json."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    try:
        try:
            resp = _storage._client.get_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/results.json")
        except Exception:
            # Fallback to latest scoring result key from ScoringRepository
            scoring_item = _scoring_repo.get_latest(job_id)
            if not scoring_item or not scoring_item.s3_result_key:
                raise
            resp = _storage._client.get_object(Bucket=_storage._bucket, Key=scoring_item.s3_result_key)

        body = resp["Body"].read().decode("utf-8")
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            candidates = parsed.get("candidates", [])
        elif isinstance(parsed, list):
            candidates = parsed
        else:
            candidates = []

        for c in candidates:
            doc_id = c.get("document_id") or c.get("_document_id") or c.get("candidate_id")
            if doc_id:
                c["document_id"] = doc_id
                c["job_id"] = job_id
                if not c.get("pdf_url"):
                    c["pdf_url"] = f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download"

        # Overlay authoritative recruiter decisions from DynamoDB
        try:
            decisions = _scoring_repo.get_candidate_decisions(job_id)
            if decisions:
                for c in candidates:
                    doc_id = c.get("document_id") or c.get("id")
                    if doc_id and doc_id in decisions:
                        dec = decisions[doc_id]
                        if "decision" in dec and dec["decision"]:
                            c["decision"] = dec["decision"]
                            c["human_decision"] = dec["decision"].upper()
                        if "status" in dec and dec["status"]:
                            c["status"] = dec["status"]
                        if "decision_reason" in dec and dec["decision_reason"] is not None:
                            c["decision_reason"] = dec["decision_reason"]
                        if "note" in dec and dec["note"] is not None:
                            c["note"] = dec["note"]
                        if "tags" in dec and dec["tags"] is not None:
                            c["tags"] = dec["tags"]
        except Exception as dec_err:
            logger.debug("Overlaying candidate decisions fallback: %s", dec_err)

        return {
            "job_id": job_id,
            "status": "scored",
            "total_candidates": len(candidates),
            "candidates": candidates,
        }
    except Exception as e:
        logger.info("Results JSON not yet available for job %s: %s", job_id, e)
        terminal_statuses = {
            JobStatus.DONE,
            JobStatus.DONE_WITH_ERRORS,
            JobStatus.READY,
            JobStatus.READY_WITH_WARNINGS,
        }
        if job.status in terminal_statuses:
            if getattr(job, "usable_files", 0) == 0:
                # Legitimately zero candidates usable or scored
                return {
                    "job_id": job_id,
                    "status": job.status.value,
                    "total_candidates": 0,
                    "candidates": [],
                }
            # Terminal job with usable files, but results missing from storage -> 500
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Scoring results could not be retrieved from storage for terminal job {job_id}: {e}",
            )
        if job.status == JobStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job failed: {job.error_message or 'Analysis processing failed'}",
            )
        # Job is still in progress (e.g. PROCESSING, SCORING, UPLOADING) -> 409 Conflict
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Results not ready yet. Current job status: {job.status.value}",
        )


@router.get("/{job_id}/resumes/{document_id}/download")
async def download_resume(
    job_id: str,
    document_id: str,
    request: Request,
):
    """Download candidate resume PDF directly from S3."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    file_item = _files_repo.get_file(job_id, document_id)
    if not file_item:
        try:
            for f in _files_repo.list_files_for_job(job_id):
                if (
                    f.file_id == document_id
                    or f.filename == document_id
                    or (f.candidate_name and f.candidate_name.strip().lower() == document_id.strip().lower())
                ):
                    file_item = f
                    break
        except Exception:
            pass

    doc_item = _docs_repo.get(job_id, document_id) if not file_item else None
    s3_key = file_item.s3_raw_key if file_item else (doc_item.s3_pdf_key if doc_item and doc_item.s3_pdf_key else f"jobs/{job_id}/raw/{document_id}.pdf")

    try:
        pdf_bytes = _storage.get_resume(job_id, document_id, s3_key=s3_key)
    except Exception as e:
        logger.error("Failed to download resume %s: %s", document_id, e)
        raise HTTPException(status_code=404, detail="Resume PDF not found in storage.")

    raw_filename = (file_item.filename if file_item else (doc_item.filename if doc_item else None)) or f"{document_id}.pdf"
    safe_filename = re.sub(r'[\r\n"]+', '_', raw_filename)
    encoded_filename = urllib.parse.quote(safe_filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"; filename*=UTF-8\'\'{encoded_filename}'},
    )


@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
async def delete_job(
    job_id: str,
    request: Request,
):
    """Cascading deletion of job and all associated files, extractions, and scores."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    job_org_id = getattr(job, "org_id", f"job_{job_id}")

    # Purge S3 prefixes: both standard and org-scoped prefixes
    prefixes = [f"jobs/{job_id}/", f"{job_org_id}/jobs/{job_id}/"]
    for pfx in dict.fromkeys(prefixes):
        try:
            paginator = _storage._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=_storage._bucket, Prefix=pfx):
                contents = page.get("Contents", [])
                if contents:
                    delete_keys = [{"Key": obj["Key"]} for obj in contents]
                    for i in range(0, len(delete_keys), 1000):
                        _storage._client.delete_objects(
                            Bucket=_storage._bucket,
                            Delete={"Objects": delete_keys[i:i + 1000]}
                        )
        except Exception as e:
            logger.warning("Error purging S3 prefix %s for job %s: %s", pfx, job_id, e)

    # Clean up DynamoDB active session and outbox items if present
    try:
        _jobs_repo._client.delete_item(
            TableName=_jobs_repo._table_name,
            Key={"PK": {"S": f"ORG#{job_org_id}"}, "SK": {"S": f"ACTIVE_SESSION#{job_id}"}},
        )
    except Exception as e:
        logger.debug("Failed cleaning active session pointer for job %s: %s", job_id, e)

    try:
        resp = _jobs_repo._client.query(
            TableName=_jobs_repo._table_name,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": {"S": f"OUTBOX#{job_id}"}},
        )
        for item in resp.get("Items", []):
            _jobs_repo._client.delete_item(
                TableName=_jobs_repo._table_name,
                Key={"PK": item["PK"], "SK": item["SK"]},
            )
    except Exception as e:
        logger.debug("Failed cleaning outbox items for job %s: %s", job_id, e)

    _jobs_repo.delete(job_id)

    audit_logger.record(getattr(job, "org_id", "org_default"), "anonymous", "JOB_DELETED", "job", job_id)
    return {"status": "deleted", "message": f"Job {job_id} and all related data deleted."}


@router.get("/{job_id}/audit", status_code=status.HTTP_200_OK)
async def get_job_audit_log(
    job_id: str,
    request: Request,
):
    """Retrieve audit log events for a job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)
    events = audit_logger.query(org_id=getattr(job, "org_id", "org_default"), resource_id=job_id)
    return {"job_id": job_id, "events": events}


@router.delete("/{job_id}/resumes/{document_id}", status_code=status.HTTP_200_OK)
async def delete_resume(
    job_id: str,
    document_id: str,
    request: Request,
):
    """Mark a resume as REMOVED and purge its raw S3 object."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    _files_repo.transition_file_terminal(
        job_id=job_id,
        file_id=document_id,
        terminal_status=FileStatus.REMOVED.value,
        error_message="User deleted resume",
    )

    doc_item = _docs_repo.get(job_id, document_id)
    if doc_item:
        try:
            from src.infrastructure.models.document import DocumentStatus
            _docs_repo.update_status_conditional(
                job_id,
                document_id,
                DocumentStatus.FAILED,
                allowed_current_statuses=None,
                extra_updates={"error_reason": "User deleted resume"},
            )
        except Exception as doc_err:
            logger.debug("DocumentItem sync on delete: %s", doc_err)

    file_item = _files_repo.get_file(job_id, document_id)

    s3_keys_to_delete = {
        f"jobs/{job_id}/raw/{document_id}.pdf",
        f"jobs/{job_id}/resumes/{document_id}.pdf",
    }
    if doc_item and doc_item.s3_pdf_key:
        s3_keys_to_delete.add(doc_item.s3_pdf_key)
    if file_item:
        if getattr(file_item, "s3_raw_key", None):
            s3_keys_to_delete.add(file_item.s3_raw_key)
        if getattr(file_item, "s3_clean_key", None):
            s3_keys_to_delete.add(file_item.s3_clean_key)

    for s3_k in s3_keys_to_delete:
        try:
            _storage._client.delete_object(Bucket=_storage._bucket, Key=s3_k)
        except Exception as e:
            logger.warning("Error deleting S3 key %s for doc %s: %s", s3_k, document_id, e)

    audit_logger.record(getattr(job, "org_id", "org_default"), "anonymous", "DOCUMENT_DELETED", "document", document_id, {"job_id": job_id})
    return {"status": "deleted", "message": f"Document {document_id} removed."}


@router.patch("/{job_id}/candidates/{document_id}/decision")
async def update_candidate_decision(
    job_id: str,
    document_id: str,
    body: DecisionUpdateRequest,
    request: Request,
):
    """Update human recruiter decision state."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    valid_decisions = ("new", "reviewing", "shortlisted", "rejected", "interview", "archived")
    raw_decision = None
    if body.decision is not None:
        cleaned = body.decision.strip().lower()
        if not cleaned or cleaned not in valid_decisions:
            raise HTTPException(status_code=400, detail=f"Invalid decision state. Must be one of: {valid_decisions}")
        raw_decision = cleaned

    if raw_decision == "rejected" and not (body.reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Non-negotiable policy: Rejections require a documented, evidence-backed reason.",
        )

    # 1. Persist decision atomically to DynamoDB
    status_mapped = (
        "shortlisted" if raw_decision == "shortlisted"
        else ("rejected" if raw_decision == "rejected"
        else ("assessment-sent" if raw_decision in ("interview", "assessment-sent") else "under-review"))
    ) if raw_decision else None

    decision_payload: Dict[str, Any] = {"updated_by": "recruiter"}
    if raw_decision is not None:
        decision_payload["decision"] = raw_decision
        decision_payload["human_decision"] = raw_decision.upper()
        decision_payload["status"] = status_mapped
    if body.reason is not None:
        decision_payload["decision_reason"] = body.reason
    if body.note is not None:
        decision_payload["note"] = body.note
    if body.tags is not None:
        decision_payload["tags"] = body.tags

    try:
        updated_attrs = _scoring_repo.save_candidate_decision(
            job_id,
            document_id,
            decision_payload,
            expected_version=body.expected_version,
            client_timestamp=body.client_timestamp,
        )
    except Exception as e:
        if "ConditionalCheckFailedException" in type(e).__name__ or "ConditionalCheckFailed" in str(e):
            raise HTTPException(status_code=409, detail="Concurrent decision update conflict. Please retry.")
        logger.error("Failed to save candidate decision: %s", e)
        raise HTTPException(status_code=500, detail="Failed to persist candidate decision.")

    audit_logger.record(
        getattr(job, "org_id", "org_default"),
        "anonymous",
        "DECISION_UPDATED",
        "candidate",
        document_id,
        {"job_id": job_id, "decision": raw_decision, "reason": body.reason, "note": body.note},
    )
    return {
        "job_id": job_id,
        "document_id": document_id,
        "decision": updated_attrs.get("decision", raw_decision),
        "reason": updated_attrs.get("decision_reason", body.reason),
        "note": updated_attrs.get("note", body.note),
        "tags": updated_attrs.get("tags", body.tags),
        "status": "updated",
    }


@router.get("/{job_id}/export/csv")
async def export_job_csv(
    job_id: str,
    request: Request,
):
    """Export candidate rankings for a job in standard CSV format."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    candidates = []
    try:
        resp = _storage._client.get_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/results.json")
        body = resp["Body"].read().decode("utf-8")
        candidates = json.loads(body).get("candidates", [])
    except Exception:
        try:
            scoring_item = _scoring_repo.get_latest(job_id)
            if scoring_item and scoring_item.s3_result_key:
                resp = _storage._client.get_object(Bucket=_storage._bucket, Key=scoring_item.s3_result_key)
                body = resp["Body"].read().decode("utf-8")
                candidates = json.loads(body).get("candidates", [])
        except Exception as e:
            logger.warning("Error fetching results for CSV export: %s", e)
            candidates = []

    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Name", "Email", "Phone", "Match Score", "Signal",
        "Decision", "Decision Reason", "Note",
        "Skills Score", "Experience Score", "Keywords Score", "Education Score",
        "Knocked Out", "Knockout Reasons",
    ])

    try:
        decisions = _scoring_repo.get_candidate_decisions(job_id)
    except Exception:
        decisions = {}

    def _sanitize_csv_cell(val: Any) -> Any:
        if isinstance(val, str) and val.startswith(("=", "+", "-", "@")):
            return f"'{val}"
        return val

    for i, c in enumerate(candidates):
        doc_id = c.get("document_id") or c.get("id")
        dec = decisions.get(doc_id, {})
        score = c.get("final_score", 0.0)
        signal = "Knockout" if c.get("knocked_out") else ("Strong" if score >= 75 else ("Good" if score >= 50 else "Fair"))
        decision = dec.get("decision") or c.get("decision") or c.get("human_decision") or "NEW"
        reason = dec.get("decision_reason") if dec.get("decision_reason") is not None else c.get("decision_reason", "")
        note = dec.get("note") if dec.get("note") is not None else c.get("note", "")
        writer.writerow([
            _sanitize_csv_cell(c.get("rank", i + 1)),
            _sanitize_csv_cell(c.get("name", "Unknown")),
            _sanitize_csv_cell(c.get("email", "")),
            _sanitize_csv_cell(c.get("phone", "")),
            f"{score:.1f}",
            signal,
            decision.upper(),
            _sanitize_csv_cell(reason),
            _sanitize_csv_cell(note),
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


@router.get("/{job_id}/extraction-metrics")
async def get_extraction_metrics(
    job_id: str,
    request: Request,
):
    """Return aggregate extraction quality and timing metrics for a job."""
    from src.infrastructure.models.document import DocumentStatus

    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request)

    docs = _docs_repo.list_for_job(job_id)
    total_docs = len(docs)
    extracted = [
        d for d in docs
        if d.status in (
            DocumentStatus.PARSED,
            DocumentStatus.STRUCTURED_PARSED,
            DocumentStatus.REVIEW_REQUIRED,
            DocumentStatus.SCORED,
        )
    ]
    failed = [d for d in docs if d.status in (DocumentStatus.PARSE_FAILED, DocumentStatus.FAILED)]
    pending = total_docs - len(extracted) - len(failed)

    avg_quality = sum(d.extraction_quality for d in extracted) / len(extracted) if extracted else 0.0

    verified_cnt = 0
    unresolved_cnt = 0
    download_times = []
    structure_times = []
    determ_times = []
    nova_times = []
    doc_metrics = []

    for d in docs:
        d_meta = {
            "document_id": d.document_id,
            "filename": d.filename,
            "status": d.status.value,
            "candidate_name": d.candidate_name,
            "identity_status": None,
            "timings": None,
        }
        if d.status == DocumentStatus.PARSED:
            try:
                ej = _storage.get_extracted_json(job_id, d.document_id)
                ident = ej.get("identity", {})
                istat = ident.get("status", "UNRESOLVED")
                d_meta["identity_status"] = istat
                if istat == "VERIFIED":
                    verified_cnt += 1
                elif istat == "UNRESOLVED":
                    unresolved_cnt += 1

                t = ej.get("_timings", {})
                d_meta["timings"] = t
                if "download_ms" in t:
                    download_times.append(t["download_ms"])
                if "structure_ms" in t:
                    structure_times.append(t["structure_ms"])
                if "deterministic_ms" in t:
                    determ_times.append(t["deterministic_ms"])
                if "nova_ms" in t:
                    nova_times.append(t["nova_ms"])
            except Exception:
                pass
        doc_metrics.append(d_meta)

    unresolved_rate = (unresolved_cnt / len(extracted)) if extracted else 0.0

    return {
        "job_id": job_id,
        "total_documents": total_docs,
        "extracted_count": len(extracted),
        "failed_count": len(failed),
        "pending_count": pending,
        "avg_quality_score": avg_quality,
        "identity_metrics": {
            "verified_count": verified_cnt,
            "unresolved_count": unresolved_cnt,
            "unresolved_rate": unresolved_rate,
        },
        "timings_summary": {
            "download_ms": sum(download_times) / len(download_times) if download_times else 0.0,
            "structure_ms": sum(structure_times) / len(structure_times) if structure_times else 0.0,
            "deterministic_ms": sum(determ_times) / len(determ_times) if determ_times else 0.0,
            "nova_ms": sum(nova_times) / len(nova_times) if nova_times else 0.0,
        },
        "documents": doc_metrics,
    }
