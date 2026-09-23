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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, BackgroundTasks, status, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, field_validator


from src.api.auth import AuthContext
from src.api.dependencies.auth import get_auth_context, enforce_tenant_ownership
from src.infrastructure.audit import audit_logger
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
    session_id: str
    job_id: str
    status: str


class FinalizeUploadSessionResponse(BaseModel):
    session_id: str
    job_id: str
    status: str
    message: str


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


class AnalysisTriggerRequest(BaseModel):
    session_id: Optional[str] = None
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


class AnalysisTriggerResponse(BaseModel):
    job_id: str
    session_id: str
    job_version: int
    status: str
    message: str


class DecisionUpdateRequest(BaseModel):
    decision: Optional[str] = None  # "new", "reviewing", "shortlisted", "rejected", "interview", "archived"
    reason: Optional[str] = None  # Mandatory if decision == "rejected"
    note: Optional[str] = None
    tags: List[str] = []



from src.core.lazy_proxy import LazyProxy
from src.config.aws import get_settings
from src.infrastructure.models.upload_session import UploadSessionItem, UploadSessionStatus
from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
from src.infrastructure.queue.queue_manager import enqueue_fast_parse, get_queue_adapter
from src.pipeline.coordinator import check_and_progress_session

# ── Shared service instances ─────────────────────────────────────────────────

_extraction_service = LazyProxy(ExtractionService)
_scorer = LazyProxy(CandidateScorer)

# ── Infrastructure singletons ────────────────────────────────────────────────

_jobs_repo = LazyProxy(JobsRepository)
_docs_repo = LazyProxy(DocumentsRepository)
_sessions_repo = LazyProxy(UploadSessionsRepository)
_scoring_repo = LazyProxy(ScoringRepository)
_storage = LazyProxy(StorageService)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateJobResponse)
async def create_job(body: CreateJobRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Create a new screening job.

    Persists to DynamoDB: PK=JOB#{id}, SK=METADATA, scoped to tenant org_id.
    """
    job = JobItem(
        org_id=ctx.org_id,
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
    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "JOB_CREATED",
        "job",
        job.job_id,
        {"title": body.title, "department": body.department},
    )
    logger.info("Created job: %s (%s) for org: %s", job.job_id, body.title, ctx.org_id)

    return CreateJobResponse(id=job.job_id, title=body.title, status="created")


@router.patch("/{job_id}")
async def update_job(job_id: str, body: UpdateJobRequest, ctx: AuthContext = Depends(get_auth_context)):
    """Update the JD config for an existing job.

    Merges only the supplied (non-None) fields.
    Increments job_version for scoring lineage tracking.
    Uses optimistic locking via version counter.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

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
    logger.info("Job %s config updated with fields: %s", job_id, list(updates.keys()))

    return {
        "id": job_id,
        "config": updates,
        "status": "updated",
    }


@router.post("/{job_id}/resumes", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_resumes(
    job_id: str,
    request: Request,
    files: List[UploadFile] = File(...),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Upload resume PDFs for a job (Compatibility wrapper using durable pipeline).

    Directly ingests PDFs, creates an upload session, uploads to S3, creates
    DocumentItem records, enqueues to FAST_PARSE_QUEUE, and finalizes the session.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    settings = get_settings()
    MAX_SIZE = settings.MAX_FILE_SIZE_BYTES
    MAX_PAGES = settings.MAX_PAGE_COUNT

    # Check org active upload sessions quota
    active_sessions = _sessions_repo.count_active_for_org(ctx.org_id)
    if active_sessions >= settings.MAX_ACTIVE_SESSIONS_PER_ORG:
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
                "message": f"Organization has {active_sessions} active upload sessions (max {settings.MAX_ACTIVE_SESSIONS_PER_ORG}). Please wait before retrying.",
            },
            headers={"Retry-After": "60"},
        )

    session_id = str(uuid.uuid4())
    job_version = getattr(job, "job_version", 1)
    session = UploadSessionItem(
        session_id=session_id,
        job_id=job_id,
        org_id=ctx.org_id,
        job_version=job_version,
        expected_document_count=len(files),
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
        analysis_requested=True,
    )
    _sessions_repo.create(session)

    accepted: List[str] = []
    rejected: List[dict] = []

    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            rejected.append({"filename": f.filename or "unknown", "reason": "Not a PDF file"})
            continue

        if f.content_type and f.content_type != "application/pdf":
            rejected.append({"filename": f.filename, "reason": f"Invalid content type: {f.content_type}"})
            continue

        content = await f.read()
        if len(content) > MAX_SIZE:
            size_mb = round(len(content) / (1024 * 1024), 1)
            rejected.append({"filename": f.filename, "reason": f"File too large: {size_mb}MB (max 10MB)"})
            continue

        if not content.startswith(b"%PDF-"):
            rejected.append({"filename": f.filename, "reason": "Corrupt or invalid PDF file (magic bytes mismatch)"})
            continue

        try:
            import fitz
            pdf_doc = fitz.open(stream=content, filetype="pdf")
            page_count = pdf_doc.page_count
            pdf_doc.close()
            if page_count > MAX_PAGES:
                rejected.append({"filename": f.filename, "reason": f"Document exceeds {MAX_PAGES} page limit ({page_count} pages)"})
                continue
        except Exception:
            rejected.append({"filename": f.filename, "reason": "Unreadable or corrupt PDF structure"})
            continue

        file_hash = hashlib.sha256(content).hexdigest()
        existing = _docs_repo.find_by_hash(job_id, file_hash)
        if existing:
            rejected.append({
                "filename": f.filename,
                "reason": f"Duplicate of '{existing.filename}' (SHA256 match)",
            })
            continue

        doc_id = str(uuid.uuid4())
        s3_key = _storage.upload_resume(job_id, doc_id, content, f.filename)

        doc = DocumentItem(
            document_id=doc_id,
            job_id=job_id,
            session_id=session_id,
            org_id=ctx.org_id,
            filename=f.filename,
            file_size=len(content),
            content_hash=file_hash,
            s3_pdf_key=s3_key,
            page_count=page_count,
            status=DocumentStatus.UPLOADED,
        )
        _docs_repo.create(doc)

        fresh_job = _jobs_repo.get(job_id)
        if fresh_job:
            _jobs_repo.increment_document_count(job_id, expected_version=fresh_job.version)

        fresh_sess = _sessions_repo.get(job_id, session_id)
        if fresh_sess:
            _sessions_repo.increment_uploaded_count(job_id, session_id, expected_version=fresh_sess.version)

        enqueue_fast_parse(
            job_id=job_id,
            session_id=session_id,
            document_id=doc_id,
            org_id=ctx.org_id,
            job_version=job_version,
            s3_key=s3_key,
            content_hash=file_hash,
        )
        accepted.append(f.filename)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "RESUMES_UPLOADED",
        "job",
        job_id,
        {"accepted_count": len(accepted), "rejected_count": len(rejected), "session_id": session_id},
    )

    # Finalize the compatibility session
    fresh_sess = _sessions_repo.get(job_id, session_id)
    if fresh_sess:
        _sessions_repo.update_status(
            job_id,
            session_id,
            UploadSessionStatus.FAST_PREPROCESSING,
            expected_version=fresh_sess.version,
        )
    check_and_progress_session(job_id, session_id)

    all_docs = _docs_repo.list_for_job(job_id)
    return UploadResponse(
        job_id=job_id,
        accepted=accepted,
        rejected=rejected,
        total_accepted=len(all_docs),
    )


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
    """Create a durable upload session and return presigned S3 PUT URLs.

    Enforces upload-safe guardrails:
    - Organization ownership and authenticated access
    - Max active upload sessions per organization quota (HTTP 429 on breach)
    - Max documents per upload session limit
    - Max batch bytes and individual file size limits
    - Pinned immutable job_version for reproducible scoring lineage
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    settings = get_settings()

    # Guard 1: Concurrency / Quota
    active_sessions = _sessions_repo.count_active_for_org(ctx.org_id)
    if active_sessions >= settings.MAX_ACTIVE_SESSIONS_PER_ORG:
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
                "message": f"Organization has {active_sessions} active upload sessions (max {settings.MAX_ACTIVE_SESSIONS_PER_ORG}). Please wait before retrying.",
            },
            headers={"Retry-After": "60"},
        )


    # Guard 2: Document count limit
    if body.document_count > settings.MAX_DOCS_PER_SESSION or len(body.files) > settings.MAX_DOCS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SESSION_DOCUMENT_LIMIT_EXCEEDED",
                "message": f"Requested document count exceeds maximum limit of {settings.MAX_DOCS_PER_SESSION}.",
            },
        )

    # Guard 3: Batch bytes & file sizes
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
    _sessions_repo.create(session)

    doc_infos: List[DocumentPresignedUrlInfo] = []
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

        doc_infos.append(
            DocumentPresignedUrlInfo(
                document_id=doc_id,
                filename=f.filename,
                s3_key=s3_key,
                presigned_url=presigned_url,
            )
        )

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
async def complete_document_upload(
    job_id: str,
    session_id: str,
    document_id: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Verify S3 upload completion, validate PDF integrity header, and enqueue for fast-parse."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    session = _sessions_repo.get(job_id, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")

    doc = _docs_repo.get(job_id, document_id)
    if not doc or doc.session_id != session_id:
        raise HTTPException(status_code=404, detail="Document not found for session")

    # Idempotency: If already UPLOADED or past that state, return success immediately
    if doc.status not in (DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING):
        return CompleteDocumentUploadResponse(
            document_id=document_id,
            session_id=session_id,
            job_id=job_id,
            status=doc.status.value,
        )

    settings = get_settings()

    # 1. HEAD request to verify object exists and check size
    try:
        head = _storage.head_object(doc.s3_pdf_key)
    except Exception as e:
        logger.error("HEAD verification failed for s3://%s: %s", doc.s3_pdf_key, e)
        raise HTTPException(status_code=400, detail="S3 object not found or incomplete upload")

    actual_size = head.get("ContentLength", 0)
    if actual_size > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds 10MB limit")

    # 2. Verify PDF magic bytes (%PDF-) via Range read
    try:
        magic_bytes = _storage.get_object_byte_range(doc.s3_pdf_key, 0, 10)
        if not magic_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Corrupted file: invalid PDF header (magic bytes mismatch)")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail="Failed to verify PDF header bytes")

    # 3. Update DocumentItem in DynamoDB to UPLOADED
    updated = _docs_repo.update_status_conditional(
        job_id=job_id,
        document_id=document_id,
        new_status=DocumentStatus.UPLOADED,
        allowed_current_statuses=[DocumentStatus.UPLOAD_INITIALIZED, DocumentStatus.PENDING],
        extra_updates={
            "file_size": actual_size,
        },
    )
    if updated:
        fresh_sess = _sessions_repo.get(job_id, session_id)
        if fresh_sess:
            _sessions_repo.increment_uploaded_count(job_id, session_id, expected_version=fresh_sess.version)

        fresh_job = _jobs_repo.get(job_id)
        if fresh_job:
            _jobs_repo.increment_document_count(job_id, expected_version=fresh_job.version)

        # Enqueue via transactional outbox — eliminates crash window between
        # DynamoDB write and SQS publish. If SQS fails, the outbox relay retries.
        try:
            from src.infrastructure.queue.outbox import write_outbox_and_send
            write_outbox_and_send(
                job_id=job_id,
                session_id=session_id,
                document_id=document_id,
                org_id=ctx.org_id,
                job_version=session.job_version,
                s3_key=doc.s3_pdf_key,
                stage="FAST_PARSE",
            )
        except Exception as outbox_err:
            # Outbox import/call failed — fall back to direct enqueue
            logger.warning("Outbox dispatch failed for doc %s, falling back to direct enqueue: %s", document_id, outbox_err)
            enqueue_fast_parse(
                job_id=job_id,
                session_id=session_id,
                document_id=document_id,
                org_id=ctx.org_id,
                job_version=session.job_version,
                s3_key=doc.s3_pdf_key,
                content_hash="",
            )

    return CompleteDocumentUploadResponse(
        document_id=document_id,
        session_id=session_id,
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
    "/{job_id}/analysis",
    response_model=AnalysisTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_analysis(
    job_id: str,
    body: Optional[AnalysisTriggerRequest] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Explicit recruiter Analyze trigger.

    Validates weights, updates JD config if modified, increments job_version,
    pins the session to new job_version, sets analysis_requested = True,
    and advances workflow through ODL/fallback to final ranking.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    req = body or AnalysisTriggerRequest()

    # 1. Validate weights if supplied
    if req.weights:
        w_sum = sum(req.weights.values())
        if abs(w_sum - 100) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=f"Score weights must sum to 100%, got {w_sum}%",
            )

    # 2. Check if JD criteria or weights changed; update and bump job_version
    updates: Dict[str, Any] = {}
    if req.title and req.title != job.title:
        updates["title"] = req.title
    if req.department and req.department != job.department:
        updates["department"] = req.department
    if req.description and req.description != job.description:
        updates["description"] = req.description
    if req.must_have_skills is not None and req.must_have_skills != job.must_have_skills:
        updates["must_have_skills"] = req.must_have_skills
    if req.nice_to_have_skills is not None and req.nice_to_have_skills != job.nice_to_have_skills:
        updates["nice_to_have_skills"] = req.nice_to_have_skills
    if req.min_years is not None and req.min_years != job.min_years:
        updates["min_years"] = req.min_years
    if req.max_years is not None and req.max_years != job.max_years:
        updates["max_years"] = req.max_years
    if req.education_level is not None and req.education_level != job.education_level:
        updates["education_level"] = req.education_level
    if req.education_field is not None and req.education_field != job.education_field:
        updates["education_field"] = req.education_field
    if req.keywords is not None and req.keywords != job.keywords:
        updates["keywords"] = req.keywords
    if req.weights:
        updates["weights"] = req.weights

    current_job_version = getattr(job, "job_version", 1)
    if updates:
        current_job_version += 1
        updates["job_version"] = current_job_version
        _jobs_repo.update(job_id, updates, expected_version=job.version)
        logger.info("Job %s criteria updated, new job_version=%d", job_id, current_job_version)

    # 3. Locate session
    session = None
    if req.session_id:
        session = _sessions_repo.get(job_id, req.session_id)
    if not session:
        sessions = _sessions_repo.list_for_job(job_id)
        if sessions:
            sessions.sort(key=lambda s: s.created_at, reverse=True)
            session = sessions[0]

    if not session:
        raise HTTPException(status_code=400, detail="No upload session found for job")

    # 4. Idempotency: If already analysis requested and running or complete, return 202
    if getattr(session, "analysis_requested", False) and session.status in (
        UploadSessionStatus.ANALYSIS_REQUESTED,
        UploadSessionStatus.FALLBACK_PROCESSING,
        UploadSessionStatus.FINAL_RANKING,
        UploadSessionStatus.READY,
        UploadSessionStatus.READY_WITH_WARNINGS,
    ):
        return AnalysisTriggerResponse(
            job_id=job_id,
            session_id=session.session_id,
            job_version=session.job_version,
            status=session.status.value,
            message="Analysis already requested and in progress.",
        )

    # 5. Authorize analysis and pin job_version
    fresh_session = _sessions_repo.get(job_id, session.session_id)
    if fresh_session:
        _sessions_repo.set_analysis_requested(
            job_id=job_id,
            session_id=session.session_id,
            expected_version=fresh_session.version,
            analysis_requested=True,
            new_status=UploadSessionStatus.ANALYSIS_REQUESTED,
            job_version=current_job_version,
        )

    # 6. Trigger coordinator to advance through ODL or final ranking
    check_and_progress_session(job_id, session.session_id)

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "ANALYSIS_REQUESTED",
        "job",
        job_id,
        {"session_id": session.session_id, "job_version": current_job_version},
    )

    return AnalysisTriggerResponse(
        job_id=job_id,
        session_id=session.session_id,
        job_version=current_job_version,
        status="ANALYSIS_REQUESTED",
        message="Analysis requested. Background processing pipeline engaged.",
    )


@router.get(
    "/{job_id}/analysis/status",
    response_model=UploadSessionProgressResponse,
)
async def get_analysis_status(
    job_id: str,
    session_id: Optional[str] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve analysis / session status for a job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    target_session = None
    if session_id:
        target_session = _sessions_repo.get(job_id, session_id)
    else:
        sessions = _sessions_repo.list_for_job(job_id)
        if sessions:
            sessions.sort(key=lambda s: s.created_at, reverse=True)
            target_session = sessions[0]

    if not target_session:
        raise HTTPException(status_code=404, detail="No session found for job")

    docs = _docs_repo.list_for_session(job_id, target_session.session_id)
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
        session_id=target_session.session_id,
        job_id=job_id,
        job_version=target_session.job_version,
        status=target_session.status.value,
        expected_document_count=target_session.expected_document_count,
        uploaded_document_count=target_session.uploaded_document_count,
        fast_parsed_count=fast_parsed,
        terminal_count=terminal,
        documents=doc_list,
    )


async def _extraction_event_stream(job_id: str):
    """Generator that yields SSE events by polling DynamoDB state (resumable)."""
    job = _jobs_repo.get(job_id)
    if not job:
        yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
        return

    seen_completed = set()
    poll_iterations = 0
    max_poll_iterations = 180  # 6 minutes max

    while poll_iterations < max_poll_iterations:
        poll_iterations += 1
        documents = _docs_repo.list_for_job(job_id)
        if not documents:
            yield f"event: error\ndata: {json.dumps({'error': 'No resumes uploaded'})}\n\n"
            return

        total = len(documents)
        completed_docs = 0
        succeeded = 0
        failed = 0

        for doc in documents:
            is_completed = (
                doc.status.is_terminal_extraction()
                or doc.status in (DocumentStatus.PARSED, DocumentStatus.PARSE_FAILED, DocumentStatus.SCORED)
            )
            if is_completed:
                completed_docs += 1
                if doc.status in (DocumentStatus.FAILED, DocumentStatus.PARSE_FAILED):
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
                        "candidate_name": doc.candidate_name,
                        "identity_status": doc.identity_status,
                        "status": "failed" if doc.status in (DocumentStatus.FAILED, DocumentStatus.PARSE_FAILED) else "extracted",
                    })
                    yield f"event: progress\ndata: {event_data}\n\n"

        if completed_docs == total and total > 0:
            yield f"event: complete\ndata: {json.dumps({'type': 'extraction_complete', 'total': total, 'succeeded': succeeded, 'failed': failed})}\n\n"
            break

        yield ": ping\n\n"
        await asyncio.sleep(1.0)
    else:
        yield f"event: error\ndata: {json.dumps({'error': 'Extraction timed out'})}\n\n"


@router.get("/{job_id}/extract")
async def extract_resumes(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Start extraction as a Server-Sent Events stream. Resumable from durable state."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

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
async def score_job(job_id: str, body: ScoreRequest, ctx: AuthContext = Depends(get_auth_context)):
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
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    # Load all extracted documents from DynamoDB
    documents = _docs_repo.list_for_job(job_id)
    extracted_docs = [
        d for d in documents
        if d.status in (
            DocumentStatus.STRUCTURED_PARSED,
            DocumentStatus.REVIEW_REQUIRED,
            DocumentStatus.PARSED,
            DocumentStatus.SCORED,
        )
    ]

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

    # Construct JobDescription with criteria
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

    audit_logger.record(
        ctx.org_id,
        ctx.user_id,
        "SCORING_COMPLETED",
        "job",
        job_id,
        {"candidate_count": len(scored_dicts), "top_candidate": top_name},
    )

    return {
        "job_id": job_id,
        "status": "scored",
        "total_candidates": len(scored_dicts),
        "weights_applied": raw_weights,
        "candidates": scored_dicts,
    }


@router.get("/{job_id}/results")
async def get_results(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Retrieve stored scoring results for a job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    latest_scoring = _scoring_repo.get_latest(job_id)
    if not latest_scoring or latest_scoring.status != ScoringStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="No scoring results available. Run analysis first."
        )

    try:
        candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
        # Ensure every candidate dictionary has document_id, job_id, and pdf_url for the UI
        for c in candidates:
            doc_id = c.get("document_id") or c.get("_document_id")
            if doc_id:
                c["document_id"] = doc_id
                c["job_id"] = job_id
                if not c.get("pdf_url"):
                    c["pdf_url"] = f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download"
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
async def download_resume(job_id: str, document_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Download a resume PDF from S3 storage."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    doc = _docs_repo.get(job_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        pdf_bytes = _storage.get_resume(job_id, document_id, s3_key=doc.s3_pdf_key)
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


# ── Retention & Deletion Endpoints ───────────────────────────────────────────

@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
async def delete_job(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Cascading deletion of job and all associated documents, extractions, and scores."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    # Delete DynamoDB records
    _jobs_repo.delete(job_id)

    # Clean up S3 prefix
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
async def delete_resume(job_id: str, document_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Delete a single candidate document and its extracted data."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    doc = _docs_repo.get(job_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    _docs_repo.delete(job_id, document_id)

    # Delete S3 objects
    try:
        _storage._client.delete_object(Bucket=_storage._bucket, Key=doc.s3_pdf_key)
        if doc.s3_extracted_key:
            _storage._client.delete_object(Bucket=_storage._bucket, Key=doc.s3_extracted_key)
    except Exception as e:
        logger.warning("Error deleting S3 keys for document %s: %s", document_id, e)

    audit_logger.record(ctx.org_id, ctx.user_id, "DOCUMENT_DELETED", "document", document_id, {"job_id": job_id})
    return {"status": "deleted", "message": f"Document {document_id} deleted."}


# ── Decision, CSV Export, Comparison, and Audit Endpoints ────────────────────

@router.patch("/{job_id}/candidates/{document_id}/decision")
async def update_candidate_decision(
    job_id: str,
    document_id: str,
    body: DecisionUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update human recruiter decision state.

    Decision states: new | reviewing | shortlisted | rejected | interview | archived
    Rejections REQUIRE an evidence-backed reason.
    """
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    valid_decisions = ("new", "reviewing", "shortlisted", "rejected", "interview", "archived")
    aliases = {
        "under-review": "reviewing",
        "under_review": "reviewing",
        "shortlist": "shortlisted",
        "reject": "rejected",
        "assessment-sent": "interview",
        "assessment_sent": "interview",
    }
    decision_norm = None
    if body.decision and body.decision.strip():
        raw_d = body.decision.strip().lower()
        decision_norm = aliases.get(raw_d, raw_d)
        if decision_norm not in valid_decisions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid decision state. Must be one of: {', '.join(valid_decisions)}",
            )

    # Mandatory reason rule for rejected decisions
    effective_reason = (body.reason or "").strip()
    if decision_norm == "rejected":
        if not effective_reason and body.note and "rejection reason:" in body.note.lower():
            parts = body.note.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                effective_reason = parts[1].strip()
        if not effective_reason:
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
        {
            "job_id": job_id,
            "decision": decision_norm,
            "reason": effective_reason if decision_norm == "rejected" else body.reason,
            "note": body.note,
        },
    )

    return {
        "job_id": job_id,
        "document_id": document_id,
        "decision": decision_norm,
        "reason": effective_reason if decision_norm == "rejected" else body.reason,
        "note": body.note,
        "status": "updated",
    }


@router.get("/{job_id}/export/csv")
async def export_job_csv(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Export candidate rankings for a job in standard CSV format."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    latest_scoring = _scoring_repo.get_latest(job_id)
    candidates = []
    if latest_scoring and latest_scoring.status == ScoringStatus.COMPLETED:
        try:
            candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
        except Exception:
            candidates = []

    # Format CSV rows
    import io
    import csv
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Rank", "Name", "Email", "Phone", "Match Score", "Signal",
        "Skills Score", "Experience Score", "Keywords Score", "Education Score",
        "Knocked Out", "Knockout Reasons", "Candidate Domain"
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
            c.get("candidate_domain", ""),
        ])

    csv_data = output.getvalue()
    audit_logger.record(ctx.org_id, ctx.user_id, "CSV_EXPORTED", "job", job_id)

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="sortlist_job_{job_id[:8]}_export.csv"',
        },
    )


@router.get("/{job_id}/compare")
async def compare_candidates(
    job_id: str,
    ids: str = Query(..., description="Comma-separated list of 2 to 4 document IDs"),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Compare 2 to 4 selected candidates side-by-side."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    doc_ids = [d.strip() for d in ids.split(",") if d.strip()]
    if len(doc_ids) < 2 or len(doc_ids) > 4:
        raise HTTPException(status_code=400, detail="Candidate comparison requires 2 to 4 candidate IDs.")

    latest_scoring = _scoring_repo.get_latest(job_id)
    if not latest_scoring:
        raise HTTPException(status_code=400, detail="Job has not been scored yet.")

    candidates = _storage.get_ranking(job_id, latest_scoring.scoring_id)
    cand_map = {c.get("document_id"): c for c in candidates}

    selected = [cand_map[did] for did in doc_ids if did in cand_map]
    return {
        "job_id": job_id,
        "count": len(selected),
        "candidates": selected,
    }


@router.get("/{job_id}/audit")
async def get_job_audit_log(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Retrieve audit log events for this job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    events = audit_logger.query(org_id=ctx.org_id, resource_id=job_id)
    return {"job_id": job_id, "events": events}


@router.get("/{job_id}/extraction-metrics")
async def get_extraction_metrics(job_id: str, ctx: AuthContext = Depends(get_auth_context)):
    """Retrieve aggregate and per-document extraction metrics and timings for a job."""
    job = _jobs_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enforce_tenant_ownership(getattr(job, "org_id", "org_default"), ctx)

    docs = _docs_repo.list_for_job(job_id)
    total_docs = len(docs)
    extracted_docs = [d for d in docs if d.status == DocumentStatus.PARSED]
    failed_docs = [d for d in docs if d.status == DocumentStatus.PARSE_FAILED]
    pending_docs = [d for d in docs if d.status in (DocumentStatus.PENDING, DocumentStatus.PARSING)]

    doc_metrics = []
    qualities = []
    id_counts = {"VERIFIED": 0, "PLAUSIBLE": 0, "UNRESOLVED": 0}
    timing_totals = {
        "download_ms": 0.0,
        "structure_ms": 0.0,
        "deterministic_ms": 0.0,
        "nova_ms": 0.0,
        "total_ms": 0.0,
    }
    timing_counts = {k: 0 for k in timing_totals}

    for d in docs:
        item = {
            "document_id": d.document_id,
            "filename": d.filename,
            "status": d.status.value if hasattr(d.status, "value") else str(d.status),
            "extraction_quality": d.extraction_quality or 0.0,
            "candidate_name": d.candidate_name or None,
            "page_count": d.page_count or 0,
            "identity_status": "UNRESOLVED",
            "timings": {},
        }

        if d.extraction_quality is not None and d.status == DocumentStatus.PARSED:
            qualities.append(float(d.extraction_quality))

        if d.status == DocumentStatus.PARSED and d.s3_extracted_key:
            try:
                fields = _storage.get_extracted_json(job_id, d.document_id)
                ident = fields.get("identity") or {}
                id_status = ident.get("status")
                if not id_status:
                    id_status = "VERIFIED" if fields.get("name") else "UNRESOLVED"
                item["identity_status"] = id_status
                if id_status in id_counts:
                    id_counts[id_status] += 1
                else:
                    id_counts["UNRESOLVED"] += 1

                t_data = fields.get("_timings") or {}
                item["timings"] = t_data
                for k, v in t_data.items():
                    if k in timing_totals and isinstance(v, (int, float)):
                        timing_totals[k] += float(v)
                        timing_counts[k] += 1
            except Exception as exc:
                logger.warning("Failed to fetch extraction JSON for doc %s metrics: %s", d.document_id, exc)
                item["identity_status"] = "VERIFIED" if d.candidate_name else "UNRESOLVED"
                id_counts[item["identity_status"]] += 1
        elif d.status == DocumentStatus.PARSED:
            item["identity_status"] = "VERIFIED" if d.candidate_name else "UNRESOLVED"
            id_counts[item["identity_status"]] += 1

        doc_metrics.append(item)

    avg_quality = round(sum(qualities) / len(qualities), 3) if qualities else 0.0
    extracted_n = len(extracted_docs)
    unresolved_rate = round(id_counts["UNRESOLVED"] / max(1, extracted_n), 3) if extracted_n > 0 else 0.0

    avg_timings = {
        k: round(timing_totals[k] / max(1, timing_counts[k]), 2)
        for k in timing_totals
    }

    return {
        "job_id": job_id,
        "total_documents": total_docs,
        "extracted_count": len(extracted_docs),
        "failed_count": len(failed_docs),
        "pending_count": len(pending_docs),
        "avg_quality_score": avg_quality,
        "identity_metrics": {
            "verified_count": id_counts["VERIFIED"],
            "plausible_count": id_counts["PLAUSIBLE"],
            "unresolved_count": id_counts["UNRESOLVED"],
            "unresolved_rate": unresolved_rate,
        },
        "timings_summary": avg_timings,
        "documents": doc_metrics,
    }


@router.post("/ats-check")
async def ats_check(file: UploadFile = File(...)):
    """Standalone ATS checker.

    Uploads a PDF, runs through the V2 Extraction Pipeline, and returns a B2B ATS Report.
    Ephemeral: deletes uploaded document data after processing.
    """
    import tempfile
    import os
    import uuid
    from src.ats.b2b_ats_scorer import B2BAtsScorer

    try:
        content = await file.read()

        # Check magic bytes (%PDF-)
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file: magic bytes mismatch")

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
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            # Ephemeral retention: cleanup S3 immediately
            try:
                _storage._client.delete_object(Bucket=_storage._bucket, Key=s3_key)
            except Exception:
                pass
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ATS check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
