"""
coordinator.py — Upload session & pipeline workflow coordinator
=================================================================
Manages barriers between pipeline stages:
1. Fast-parse barrier: waits until all expected documents are in terminal fast-parse states.
2. Fallback routing: routes NEEDS_ODL documents to ODL_BATCH_QUEUE in bounded batches.
3. Nova routing: routes NEEDS_NOVA documents to NOVA_QUEUE.
4. Final ranking barrier: waits until all documents reach terminal extraction states,
   then triggers exactly one FINAL_RANK_QUEUE event for the pinned job_version.
"""

import logging
from typing import List

from src.config.aws import get_settings
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.models.job import JobStatus
from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.queue.queue_manager import (
    enqueue_final_rank,
    enqueue_nova,
    enqueue_odl_batch,
)
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.upload_sessions_repository import (
    UploadSessionsRepository,
)

logger = logging.getLogger(__name__)


def check_and_progress_session(job_id: str, session_id: str) -> None:
    """Evaluate session state and advance workflow through the fast-parse barrier."""
    sessions_repo = UploadSessionsRepository()
    docs_repo = DocumentsRepository()
    jobs_repo = JobsRepository()
    settings = get_settings()

    session = sessions_repo.get(job_id, session_id)
    if not session:
        logger.warning("Coordinator: session %s not found for job %s", session_id, job_id)
        return

    # If the user has not finalized the upload session, do not advance
    if session.status == UploadSessionStatus.UPLOADING:
        logger.debug("Coordinator: session %s is still UPLOADING", session_id)
        return

    # If session is already in final ranking or completed, nothing to do
    if session.status in (
        UploadSessionStatus.FINAL_RANKING,
        UploadSessionStatus.READY,
        UploadSessionStatus.READY_WITH_WARNINGS,
        UploadSessionStatus.FAILED,
    ):
        return

    # Get all documents for this session
    documents = docs_repo.list_for_session(job_id, session_id)
    if not documents:
        logger.debug("Coordinator: no documents found for session %s", session_id)
        return

    # If document count < expected, some uploads are still in transit
    if len(documents) < session.expected_document_count:
        logger.debug(
            "Coordinator: session %s has %d/%d documents uploaded",
            session_id, len(documents), session.expected_document_count,
        )
        return

    # Check if all documents have completed fast-parse
    all_fast_complete = all(d.status.is_terminal_fast_parse() for d in documents)
    if not all_fast_complete:
        fast_done = sum(1 for d in documents if d.status.is_terminal_fast_parse())
        logger.debug(
            "Coordinator: fast parsing in progress for session %s: %d/%d complete",
            session_id, fast_done, len(documents),
        )
        return

    # Fast-parse barrier reached!
    # Check if recruiter has explicitly authorized analysis (Analyze click)
    if not getattr(session, "analysis_requested", False):
        if session.status != UploadSessionStatus.READY_TO_ANALYZE:
            try:
                fresh_session = sessions_repo.get(job_id, session_id)
                if fresh_session and fresh_session.status != UploadSessionStatus.READY_TO_ANALYZE:
                    sessions_repo.update_status(
                        job_id,
                        session_id,
                        UploadSessionStatus.READY_TO_ANALYZE,
                        expected_version=fresh_session.version,
                    )
                    logger.info("Coordinator: Session %s reached fast-pass barrier and is READY_TO_ANALYZE", session_id)
            except Exception as e:
                logger.debug("Coordinator: error setting READY_TO_ANALYZE for session %s: %s", session_id, e)
        return

    # User explicitly authorized analysis (analysis_requested = True)
    # Inspect fallback requirements
    needs_odl_docs = [d for d in documents if d.status == DocumentStatus.NEEDS_ODL]

    if needs_odl_docs:
        # Advance session to FALLBACK_PROCESSING
        try:
            fresh_session = sessions_repo.get(job_id, session_id)
            if fresh_session and fresh_session.status != UploadSessionStatus.FALLBACK_PROCESSING:
                sessions_repo.update_status(
                    job_id,
                    session_id,
                    UploadSessionStatus.FALLBACK_PROCESSING,
                    expected_version=fresh_session.version,
                )
        except Exception as e:
            logger.debug("Coordinator: session status update race: %s", e)


        # Batch documents into bounded chunks
        batch_size = max(1, settings.ODL_BATCH_SIZE)
        for i in range(0, len(needs_odl_docs), batch_size):
            chunk = needs_odl_docs[i : i + batch_size]
            chunk_ids = [d.document_id for d in chunk]

            # Transition documents to ODL_QUEUED
            for doc in chunk:
                docs_repo.update_status_conditional(
                    job_id,
                    doc.document_id,
                    DocumentStatus.ODL_QUEUED,
                    allowed_current_statuses=[DocumentStatus.NEEDS_ODL],
                )

            # Enqueue batch message to ODL_BATCH_QUEUE
            enqueue_odl_batch(
                job_id=job_id,
                session_id=session_id,
                document_ids=chunk_ids,
                org_id=session.org_id,
                job_version=session.job_version,
            )
            logger.info("Enqueued ODL batch of %d documents for session %s", len(chunk_ids), session_id)
        return

    # If no ODL fallback needed, check for Nova fallback
    needs_nova_docs = [d for d in documents if d.status == DocumentStatus.NEEDS_NOVA]
    if needs_nova_docs:
        try:
            fresh_session = sessions_repo.get(job_id, session_id)
            if fresh_session and fresh_session.status != UploadSessionStatus.FALLBACK_PROCESSING:
                sessions_repo.update_status(
                    job_id,
                    session_id,
                    UploadSessionStatus.FALLBACK_PROCESSING,
                    expected_version=fresh_session.version,
                )
        except Exception as e:
            logger.debug("Coordinator: session status update race: %s", e)

        for doc in needs_nova_docs:
            docs_repo.update_status_conditional(
                job_id,
                doc.document_id,
                DocumentStatus.NOVA_QUEUED,
                allowed_current_statuses=[DocumentStatus.NEEDS_NOVA],
            )
            enqueue_nova(
                job_id=job_id,
                session_id=session_id,
                document_id=doc.document_id,
                org_id=session.org_id,
                job_version=session.job_version,
                s3_key=doc.s3_pdf_key,
            )
        return

    # No fallbacks required! All documents in terminal extraction states.
    _advance_to_final_ranking(job_id, session, documents)


def check_and_progress_fallback(job_id: str, session_id: str) -> None:
    """Evaluate fallback completion and advance workflow to final ranking when ready."""
    sessions_repo = UploadSessionsRepository()
    docs_repo = DocumentsRepository()

    session = sessions_repo.get(job_id, session_id)
    if not session:
        return

    if session.status in (
        UploadSessionStatus.FINAL_RANKING,
        UploadSessionStatus.READY,
        UploadSessionStatus.READY_WITH_WARNINGS,
        UploadSessionStatus.FAILED,
    ):
        return

    documents = docs_repo.list_for_session(job_id, session_id)
    if not documents:
        return

    # Check if any documents newly need Nova
    for doc in documents:
        if doc.status == DocumentStatus.NEEDS_NOVA:
            updated = docs_repo.update_status_conditional(
                job_id,
                doc.document_id,
                DocumentStatus.NOVA_QUEUED,
                allowed_current_statuses=[DocumentStatus.NEEDS_NOVA],
            )
            if updated:
                enqueue_nova(
                    job_id=job_id,
                    session_id=session_id,
                    document_id=doc.document_id,
                    org_id=session.org_id,
                    job_version=session.job_version,
                    s3_key=doc.s3_pdf_key,
                )

    # Check if all documents reached terminal extraction states
    all_terminal = all(d.status.is_terminal_extraction() for d in documents)
    if all_terminal:
        _advance_to_final_ranking(job_id, session, documents)


def _advance_to_final_ranking(
    job_id: str,
    session: UploadSessionItem,
    documents: List[DocumentItem],
) -> None:
    """Atomically advance session and job to FINAL_RANKING and enqueue final scoring."""
    sessions_repo = UploadSessionsRepository()
    jobs_repo = JobsRepository()

    try:
        fresh_session = sessions_repo.get(job_id, session.session_id)
        if not fresh_session or fresh_session.status in (
            UploadSessionStatus.FINAL_RANKING,
            UploadSessionStatus.READY,
            UploadSessionStatus.READY_WITH_WARNINGS,
        ):
            return

        sessions_repo.update_status(
            job_id,
            session.session_id,
            UploadSessionStatus.FINAL_RANKING,
            expected_version=fresh_session.version,
        )

        fresh_job = jobs_repo.get(job_id)
        if fresh_job:
            try:
                jobs_repo.update_status(
                    job_id,
                    JobStatus.FINAL_RANKING,
                    expected_version=fresh_job.version,
                )
            except Exception:
                pass

        enqueue_final_rank(
            job_id=job_id,
            session_id=session.session_id,
            org_id=session.org_id,
            job_version=session.job_version,
        )
        logger.info(
            "Session %s and Job %s advanced to FINAL_RANKING; enqueued final ranking event",
            session.session_id, job_id,
        )
    except Exception as e:
        logger.error("Failed to advance session %s to final ranking: %s", session.session_id, e)
