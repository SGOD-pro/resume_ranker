"""
final_rank_worker.py — Final scoring and ranking worker
======================================================
Consumes messages from FINAL_RANK_QUEUE. Runs candidate scoring and ranking once
over the complete set of extracted documents for a pinned job_version.
Guarantees idempotency and version consistency; prevents stale ranking overwrites.
"""

import logging
import uuid
from dataclasses import asdict
from typing import Any, Dict, List

from src.infrastructure.models.document import DocumentStatus
from src.infrastructure.models.job import JobStatus
from src.infrastructure.models.scoring import ScoringItem
from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import FINAL_RANK_QUEUE, get_queue_adapter
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.repositories.upload_sessions_repository import (
    UploadSessionsRepository,
)
from src.infrastructure.storage.storage_service import StorageService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

logger = logging.getLogger(__name__)


def process_final_rank_message(message: QueueMessage) -> None:
    """Execute final ranking for one queue message."""
    jobs_repo = JobsRepository()
    sessions_repo = UploadSessionsRepository()
    docs_repo = DocumentsRepository()
    scoring_repo = ScoringRepository()
    storage = StorageService()
    queue_adapter = get_queue_adapter()

    job_id = message.job_id
    session_id = message.session_id

    session = sessions_repo.get(job_id, session_id)
    if not session:
        logger.warning("FinalRankWorker: Session %s not found for job %s", session_id, job_id)
        if message.receipt_handle:
            queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
        return

    # Idempotency guard: If session already reached terminal state, skip
    if session.status in (UploadSessionStatus.READY, UploadSessionStatus.READY_WITH_WARNINGS):
        logger.info("FinalRankWorker: Session %s already in terminal state %s, skipping", session_id, session.status.value)
        if message.receipt_handle:
            queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
        return

    job = jobs_repo.get(job_id)
    if not job:
        logger.error("FinalRankWorker: Job %s not found", job_id)
        if message.receipt_handle:
            queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
        return

    # Version check: Stale rank messages must not overwrite newer job results
    if job.job_version != message.job_version:
        logger.warning(
            "FinalRankWorker: Job description changed (job_version %d != event version %d). Discarding stale rank event.",
            job.job_version, message.job_version,
        )
        if message.receipt_handle:
            queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
        return

    try:
        # Load all documents for the session or job
        documents = docs_repo.list_for_session(job_id, session_id)
        if not documents:
            documents = docs_repo.list_for_job(job_id)

        valid_docs = [
            d for d in documents
            if d.status in (
                DocumentStatus.STRUCTURED_PARSED,
                DocumentStatus.REVIEW_REQUIRED,
                DocumentStatus.PARSED,
                DocumentStatus.SCORED,
            )
        ]

        failed_docs = [
            d for d in documents
            if d.status in (DocumentStatus.FAILED, DocumentStatus.PARSE_FAILED)
        ]

        if not valid_docs:
            logger.warning("FinalRankWorker: No valid extracted documents to rank for job %s", job_id)
            target_status = UploadSessionStatus.FAILED if failed_docs else UploadSessionStatus.READY_WITH_WARNINGS
            sessions_repo.update_status(
                job_id, session_id, target_status,
                expected_version=session.version,
                error_message="No candidates were successfully extracted",
            )
            if message.receipt_handle:
                queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
            return

        # Load extracted JSON from S3
        candidates: List[Dict[str, Any]] = []
        for d in valid_docs:
            try:
                fields = storage.get_extracted_json(d.job_id, d.document_id)
                fields["_document_id"] = d.document_id
                if "extraction_quality" not in fields:
                    fields["extraction_quality"] = d.extraction_quality or 0.0
                candidates.append(fields)
            except Exception as e:
                logger.error("FinalRankWorker: Could not load extracted JSON for doc %s: %s", d.document_id, e)

        # Build JobDescription
        raw_weights = getattr(job, "weights", {}) or {
            "skills": 0.40,
            "experience": 0.25,
            "keywords": 0.20,
            "education": 0.15,
        }
        float_weights = {k: float(v) for k, v in raw_weights.items()}

        jd = JobDescription(
            title=job.title,
            department=job.department or "",
            description=job.description or "",
            must_have_skills=job.must_have_skills or [],
            nice_to_have_skills=job.nice_to_have_skills or [],
            min_years=job.min_years or 0,
            max_years=job.max_years or 99,
            required_degree=job.education_level or "any",
            preferred_field=job.education_field or "",
            keywords=job.keywords or [],
            weights=float_weights,
            job_version=message.job_version,
        )

        scorer = CandidateScorer()
        results = scorer.rank(jd, candidates)

        # Persist ranking JSON to S3
        scoring_id = str(uuid.uuid4())
        s3_key = storage.upload_ranking(job_id, scoring_id, [asdict(r) for r in results])

        # Persist ScoringItem in DynamoDB
        top_name = results[0].name if results else None
        top_score = results[0].final_score if results else None

        scoring_item = ScoringItem(
            scoring_id=scoring_id,
            job_id=job_id,
            org_id=message.org_id,
            s3_result_key=s3_key,
            candidate_count=len(results),
            weights_used=float_weights,
            top_candidate_name=top_name,
            top_candidate_score=top_score,
            score_version="2.2.0",
            policy_version="2026.1",
            job_version=message.job_version,
        )
        scoring_repo.create(scoring_item)

        # Update candidate document items to SCORED
        for d in valid_docs:
            try:
                docs_repo.update_status_conditional(
                    job_id=job_id,
                    document_id=d.document_id,
                    new_status=DocumentStatus.SCORED,
                    allowed_current_statuses=[
                        DocumentStatus.STRUCTURED_PARSED,
                        DocumentStatus.REVIEW_REQUIRED,
                        DocumentStatus.PARSED,
                    ],
                )
            except Exception:
                pass

        # Determine terminal job & session status
        has_warnings = len(failed_docs) > 0
        final_session_status = (
            UploadSessionStatus.READY_WITH_WARNINGS if has_warnings else UploadSessionStatus.READY
        )
        final_job_status = (
            JobStatus.READY_WITH_WARNINGS if has_warnings else JobStatus.READY
        )

        sessions_repo.update_status(
            job_id, session_id, final_session_status, expected_version=session.version
        )
        try:
            fresh_job = jobs_repo.get(job_id)
            if fresh_job:
                jobs_repo.update_status(
                    job_id, final_job_status, expected_version=fresh_job.version
                )
        except Exception:
            pass

        logger.info(
            "FinalRankWorker: Completed final ranking for job %s (session %s) -> status %s, %d scored",
            job_id, session_id, final_session_status.value, len(results),
        )

    except Exception as e:
        logger.error("FinalRankWorker: Error during final ranking for job %s: %s", job_id, e, exc_info=True)
        try:
            sessions_repo.update_status(
                job_id, session_id, UploadSessionStatus.FAILED,
                expected_version=session.version, error_message=str(e),
            )
        except Exception:
            pass

    finally:
        if message.receipt_handle:
            queue_adapter.delete_message(FINAL_RANK_QUEUE, message.receipt_handle)
