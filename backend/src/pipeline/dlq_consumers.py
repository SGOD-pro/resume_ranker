"""
dlq_consumers.py — Dead-Letter Queue (DLQ) handlers for Stage 1, Stage 2, and Scoring
=====================================================================================
Implements Amendment 2:
- stage1 DLQ consumer: marks file S1_FAILED, conditionally decrementing job.remaining
- stage2 DLQ consumer: marks file S2_FAILED, conditionally decrementing job.remaining
- scoring DLQ consumer: marks job FAILED
Guarantees the system never gets stuck with non-zero remaining when messages die in DLQs.
"""

import json
import logging
from typing import Any

from src.infrastructure.models.file import FileStatus
from src.infrastructure.models.job import JobStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.pipeline.stage1_worker import extract_job_file_from_message

logger = logging.getLogger(__name__)


def process_stage1_dlq_message(message: Any) -> bool:
    """Consume a dead message from Stage 1 DLQ and transition file to S1_FAILED."""
    files_repo = FilesRepository()
    job_id, file_id, _ = extract_job_file_from_message(message)

    if not job_id or not file_id:
        logger.error("Stage1DLQ: Could not parse job_id/file_id from DLQ message")
        return False

    logger.warning("Stage1DLQ: Processing poisoned message for %s/%s -> S1_FAILED", job_id, file_id)
    files_repo.transition_file_terminal(
        job_id=job_id,
        file_id=file_id,
        terminal_status=FileStatus.S1_FAILED.value,
        error_message="Stage 1 processing permanently failed (routed to DLQ)",
    )
    return True


def process_stage2_dlq_message(message: Any) -> bool:
    """Consume a dead message from Stage 2 DLQ and transition file to S2_FAILED."""
    files_repo = FilesRepository()

    job_id = getattr(message, "job_id", None)
    file_id = getattr(message, "document_id", None) or getattr(message, "file_id", None)

    if not job_id or not file_id:
        body = message.body if hasattr(message, "body") else message
        if isinstance(body, dict) and "body" in body:
            body = body["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                pass
        if isinstance(body, dict):
            job_id = body.get("job_id")
            file_id = body.get("document_id") or body.get("file_id")

    if not job_id or not file_id:
        logger.error("Stage2DLQ: Could not parse job_id/file_id from DLQ message")
        return False

    logger.warning("Stage2DLQ: Processing poisoned message for %s/%s -> S2_FAILED", job_id, file_id)
    files_repo.transition_file_terminal(
        job_id=job_id,
        file_id=file_id,
        terminal_status=FileStatus.S2_FAILED.value,
        error_message="Stage 2 fallback permanently failed (routed to DLQ)",
    )
    return True


def process_scoring_dlq_message(message: Any) -> bool:
    """Consume a dead message from Scoring DLQ and mark job FAILED."""
    jobs_repo = JobsRepository()

    job_id = getattr(message, "job_id", None)
    if not job_id:
        body = message.body if hasattr(message, "body") else message
        if isinstance(body, dict) and "body" in body:
            body = body["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                pass
        if isinstance(body, dict):
            job_id = body.get("job_id")

    if not job_id:
        logger.error("ScoringDLQ: Could not parse job_id from DLQ message")
        return False

    logger.error("ScoringDLQ: Scoring permanently failed for job %s -> FAILED", job_id)
    job = jobs_repo.get(job_id)
    if job:
        jobs_repo.update(
            job_id,
            {"status": JobStatus.FAILED.value, "error_message": "Scoring failed after max retries (DLQ)"},
            expected_version=job.version,
        )
    return True
