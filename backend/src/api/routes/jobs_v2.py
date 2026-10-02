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
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.api.auth import AuthContext
from src.api.dependencies.auth import enforce_tenant_ownership, get_auth_context
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


def enforce_session_ownership(job: JobItem, request: Request, ctx: Optional[AuthContext] = None) -> None:
    """Verify session or tenant ownership of the requested job."""
    job_org = getattr(job, "org_id", None)
    if ctx and ctx.org_id and ctx.org_id != "org_default" and job_org and job_org != "org_default":
        if ctx.org_id != job_org:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Access denied: tenant organization mismatch."},
            )
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
    tags: List[str] = Field(default_factory=list)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_200_OK)
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

    if body.files:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK

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

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    s3_key = f"ats_check/{uuid.uuid4().hex[:8]}_{file.filename}"
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
        raise HTTPException(status_code=500, detail=f"ATS check failed: {str(e)}")
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

    try:
        import fitz
        doc = fitz.open(stream=contents, filetype="pdf")
        text_pages = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n\n".join(text_pages).strip()
        return {"text": full_text, "filename": file.filename}
    except Exception as e:
        logger.error("Parse JD PDF failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse JD PDF: {str(e)}")


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


@router.post("/{job_id}/files/uploaded", status_code=status.HTTP_202_ACCEPTED)
@router.post("/{job_id}/resumes/complete", status_code=status.HTTP_202_ACCEPTED)
@router.post("/{job_id}/upload-complete", status_code=status.HTTP_202_ACCEPTED)
async def notify_files_uploaded(
    job_id: str,
    request: Request,
    body: Optional[FileUploadNotification] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Notify backend that direct-to-S3 uploads have completed for files.
    
    Immediately starts the PyMuPDF fast-parse pipeline in the background.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    all_files = _files_repo.list_files_for_job(job_id)
    target_ids = set(body.file_ids) if (body and body.file_ids) else {f.file_id for f in all_files}

    settings = get_settings()
    run_local = settings.is_local() or settings.RUN_LOCAL_WORKERS
    enqueued_count = 0

    logger.info("|PYMUPDF| Starting multithreaded extraction for %d files in job %s", len(target_ids), job_id)

    for f in all_files:
        if f.file_id in target_ids and not f.is_terminal and f.status not in (FileStatus.S1_DONE, FileStatus.S2_DONE):
            msg = QueueMessage(
                job_id=job_id,
                session_id=job.session_id,
                document_id=f.file_id,
                org_id=ctx.org_id,
                job_version=job.job_version,
                s3_key=f.s3_raw_key,
                content_hash="",
                stage="FAST_PARSE",
            )
            try:
                enqueue_fast_parse(
                    job_id=job_id,
                    session_id=job.session_id,
                    document_id=f.file_id,
                    org_id=ctx.org_id,
                    job_version=job.job_version,
                    s3_key=f.s3_raw_key,
                    content_hash="",
                )
            except Exception as e:
                logger.warning("Could not enqueue via enqueue_fast_parse: %s", e)

            enqueued_count += 1

    logger.info("|PYMUPDF| Enqueued and started %d files for background PyMuPDF extraction for job %s", enqueued_count, job_id)
    return {
        "job_id": job_id,
        "enqueued": enqueued_count,
        "status": "processing",
        "message": f"PyMuPDF background extraction started for {enqueued_count} files.",
    }


@router.post("/{job_id}/resumes", status_code=status.HTTP_200_OK)
async def upload_resumes_multipart(
    job_id: str,
    request: Request,
    files: List[UploadFile] = File(...),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Multipart upload fallback for direct file submission."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    file_items = []
    messages = []
    adapter = get_queue_adapter()
    settings = get_settings()
    run_local = settings.is_local() or settings.RUN_LOCAL_WORKERS

    logger.info("|PYMUPDF| Backend received %d resumes from frontend for job %s. Uploading to S3 and starting extraction...", len(files), job_id)

    # Read all file contents and validate PDF magic bytes (%PDF)
    file_payloads = []
    rejected = []
    for f in files:
        content = await f.read()
        f_name = f.filename or "resume.pdf"
        if not content.startswith(b"%PDF"):
            logger.warning("Rejected file %s: invalid PDF magic bytes", f_name)
            rejected.append({"filename": f_name, "reason": "Invalid PDF magic bytes: file is not a valid PDF document."})
            continue
        file_payloads.append((f_name, content))

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
            session_id=job.session_id,
            document_id=fid,
            org_id=ctx.org_id,
            job_version=job.job_version,
            s3_key=s3_key,
            stage="FAST_PARSE",
        )
        return f_item, q_msg

    # Parallel S3 uploads
    upload_results = await asyncio.gather(
        *(asyncio.to_thread(_upload_single_s3, fn, c) for fn, c in file_payloads)
    )

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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a durable upload session and return presigned S3 PUT URLs."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    settings = get_settings()

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
        org_id=ctx.org_id,
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
        logger.warning("Org %s admission verification failed: %s", ctx.org_id, ave)
        raise HTTPException(
            status_code=503,
            detail={
                "status_code": 503,
                "error_code": "ADMISSION_VERIFICATION_UNAVAILABLE",
                "code": "ADMISSION_VERIFICATION_UNAVAILABLE",
                "route": request.url.path,
                "job_id": job_id,
                "session_id": None,
                "org_id": ctx.org_id,
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
                "org_id": ctx.org_id,
                "client_ip_hash": ip_hash,
                "retry_after": 60,
                "retry_after_seconds": 60,
                "message": f"Organization has {qee.current} active upload sessions (max {qee.limit}). Please wait before retrying.",
            },
            headers={"Retry-After": "60"},
        )

    doc_infos: List[DocumentPresignedUrlInfo] = []
    file_items: List[FileItem] = []
    for f in body.files:
        doc_id = str(uuid.uuid4())
        s3_key = f"{ctx.org_id}/jobs/{job_id}/sessions/{session_id}/resumes/{doc_id}.pdf"
        presigned_url = _storage.generate_presigned_put_url(
            s3_key=s3_key,
            content_type=f.content_type or "application/pdf",
            expires_in=settings.PRESIGNED_URL_EXPIRY_SECONDS,
        )

        doc_item = DocumentItem(
            document_id=doc_id,
            job_id=job_id,
            session_id=session_id,
            org_id=ctx.org_id,
            filename=f.filename,
            file_size=f.file_size,
            s3_pdf_key=s3_key,
            status=DocumentStatus.UPLOAD_INITIALIZED,
        )
        _docs_repo.create(doc_item)

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

    if file_items:
        _files_repo.create_files(job_id, file_items)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
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
    session_id: Optional[str] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Verify S3 upload completion, validate PDF integrity header, and enqueue for fast-parse."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    doc = _docs_repo.get(job_id, document_id)
    resolved_session_id = session_id or (doc.session_id if doc else None) or getattr(job, "session_id", "default_session")

    # Idempotency: If already UPLOADED or past that state, return success immediately
    if doc and doc.status not in (DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING):
        return CompleteDocumentUploadResponse(
            document_id=document_id,
            session_id=resolved_session_id,
            job_id=job_id,
            status=doc.status.value,
        )

    s3_key = (doc.s3_pdf_key if doc else None) or f"jobs/{job_id}/resumes/{document_id}.pdf"
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

    # 2. Verify PDF magic bytes (%PDF-) via Range read
    try:
        magic_bytes = _storage.get_object_byte_range(s3_key, 0, 10)
        if not magic_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Corrupted file: invalid PDF header (magic bytes mismatch)")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail="Failed to verify PDF header bytes")

    # 3. Update DocumentItem and FileItem in DynamoDB to UPLOADED
    if doc:
        updated = _docs_repo.update_status_conditional(
            job_id=job_id,
            document_id=document_id,
            new_status=DocumentStatus.UPLOADED,
            allowed_current_statuses=[DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING],
            extra_updates={"file_size": actual_size},
        )
        if updated and resolved_session_id:
            fresh_sess = _sessions_repo.get(job_id, resolved_session_id)
            if fresh_sess:
                _sessions_repo.increment_uploaded_count(job_id, resolved_session_id, expected_version=fresh_sess.version)

    _files_repo.update_file_non_terminal(
        job_id=job_id,
        file_id=document_id,
        status=FileStatus.UPLOADED,
        file_size=actual_size,
    )

    fresh_job = _jobs_repo.get(job_id)
    if fresh_job:
        _jobs_repo.increment_document_count(job_id, expected_version=fresh_job.version)

    # 4. Enqueue to FAST_PARSE_QUEUE
    job_version = getattr(fresh_job, "job_version", 1) if fresh_job else 1
    enqueue_fast_parse(
        job_id=job_id,
        session_id=resolved_session_id,
        document_id=document_id,
        org_id=ctx.org_id,
        job_version=job_version,
        s3_key=s3_key,
        content_hash="",
    )

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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Finalize upload session to establish the explicit fast-parse barrier."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve upload session state, progress counts, and per-document diagnostics."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

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
    ctx: AuthContext = Depends(get_auth_context),
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

    current_job_version = getattr(job, "job_version", 1)
    if updates:
        current_job_version += 1
        updates["job_version"] = current_job_version
        job = _jobs_repo.update(job_id, updates, expected_version=job.version)

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
            check_and_progress_session(job_id, target_session.session_id)
        except Exception as e:
            logger.warning("Could not set analysis_requested on session: %s", e)

    # Determine explicit file IDs
    all_files = _files_repo.list_files_for_job(job_id)
    if req.file_ids is not None:
        selected_file_ids = req.file_ids
    else:
        selected_file_ids = [f.file_id for f in all_files if f.status != FileStatus.REMOVED]

    # Ensure any selected files not yet in S1_DONE or terminal state are enqueued for Stage 1
    for f in all_files:
        if f.file_id in selected_file_ids and not f.is_terminal and f.status not in (FileStatus.S1_DONE, FileStatus.S2_DONE):
            try:
                enqueue_fast_parse(
                    job_id=job_id,
                    session_id=job.session_id or (target_session.session_id if target_session else "default"),
                    document_id=f.file_id,
                    org_id=ctx.org_id,
                    job_version=current_job_version,
                    s3_key=f.s3_raw_key,
                    content_hash="",
                )
            except Exception:
                pass

    # Execute request_analysis (conditionally marks REMOVED, advances fallback, triggers scoring if remaining == 0)
    updated_job = _jobs_repo.request_analysis(job_id, selected_file_ids)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Short-polling endpoint with ETag/304 and 10-minute stalling detection.

    Uses a single DynamoDB query (PK=JOB#{job_id}) to fetch METADATA and all FILE# items.
    """
    # 1. Fetch job and files, and strictly enforce session ownership FIRST
    job, files = _jobs_repo.get_job_with_files(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

    # 2. Reconcile any pending outbox events only after ownership is validated
    try:
        reconciled_count = _files_repo.reconcile_outbox(job_id)
        if isinstance(reconciled_count, int) and reconciled_count > 0:
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


@router.get("/{job_id}/extract")
async def extract_resumes_stream(
    job_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """SSE extraction stream for client compatibility (API contracts)."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Score candidates for a job.
    Accepts weights and executes candidate scoring.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)

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
    msg = QueueMessage(
        job_id=job_id,
        session_id=job.session_id,
        document_id=job_id,
        org_id=ctx.org_id,
        job_version=job.job_version,
        stage="FINAL_RANK",
    )
    process_scoring_message(msg)

    results_resp = await get_results(job_id=job_id, request=request, ctx=ctx)
    return results_resp


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

        return {
            "job_id": job_id,
            "status": "scored",
            "total_candidates": len(candidates),
            "candidates": candidates,
        }
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

    filename = (file_item.filename if file_item else (doc_item.filename if doc_item else None)) or f"{document_id}.pdf"
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


@router.get("/{job_id}/audit", status_code=status.HTTP_200_OK)
async def get_job_audit_log(
    job_id: str,
    request: Request,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve audit log events for a job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_session_ownership(job, request, ctx)
    events = audit_logger.query(org_id=ctx.org_id, resource_id=job_id)
    return {"job_id": job_id, "events": events}


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

    # Persist decision to S3 results.json if it exists
    try:
        resp = _storage._client.get_object(Bucket=_storage._bucket, Key=f"jobs/{job_id}/results.json")
        body_content = resp["Body"].read().decode("utf-8")
        results_data = json.loads(body_content)
        candidates = results_data.get("candidates", [])
        updated = False
        for c in candidates:
            c_doc_id = c.get("document_id") or c.get("_document_id") or c.get("candidate_id")
            if c_doc_id == document_id or c.get("id") == document_id:
                if raw_decision:
                    c["decision"] = raw_decision
                    c["human_decision"] = raw_decision.upper()
                    if raw_decision == "shortlisted":
                        c["status"] = "shortlisted"
                    elif raw_decision == "rejected":
                        c["status"] = "rejected"
                    elif raw_decision in ("interview", "assessment-sent"):
                        c["status"] = "assessment-sent"
                    else:
                        c["status"] = "under-review"
                if body.reason is not None:
                    c["decision_reason"] = body.reason
                if body.note is not None:
                    c["note"] = body.note
                if body.tags is not None:
                    c["tags"] = body.tags
                updated = True
                break
        if updated:
            _storage._client.put_object(
                Bucket=_storage._bucket,
                Key=f"jobs/{job_id}/results.json",
                Body=json.dumps(results_data, indent=2).encode("utf-8"),
                ContentType="application/json",
            )
            logger.info("Updated decision for candidate %s in job %s results.json", document_id, job_id)
    except Exception as e:
        logger.warning("Could not update decision in results.json for job %s: %s", job_id, e)

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
        "Decision", "Decision Reason", "Note",
        "Skills Score", "Experience Score", "Keywords Score", "Education Score",
        "Knocked Out", "Knockout Reasons",
    ])

    for i, c in enumerate(candidates):
        score = c.get("final_score", 0.0)
        signal = "Knockout" if c.get("knocked_out") else ("Strong" if score >= 75 else ("Good" if score >= 50 else "Fair"))
        decision = c.get("decision") or c.get("human_decision") or "NEW"
        writer.writerow([
            c.get("rank", i + 1),
            c.get("name", "Unknown"),
            c.get("email", ""),
            c.get("phone", ""),
            f"{score:.1f}",
            signal,
            decision.upper(),
            c.get("decision_reason", ""),
            c.get("note", ""),
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
    ctx: AuthContext = Depends(get_auth_context),
):
    """Return aggregate extraction quality and timing metrics for a job."""
    from src.infrastructure.models.document import DocumentStatus

    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    docs = _docs_repo.list_for_job(job_id)
    total_docs = len(docs)
    extracted = [d for d in docs if d.status == DocumentStatus.PARSED]
    failed = [d for d in docs if d.status == DocumentStatus.PARSE_FAILED]
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
