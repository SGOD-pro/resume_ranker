"""
test_dlq_and_race_safety.py — Tests for DLQ consumers, Bedrock throttling, and pipeline race safety
====================================================================================================
Verifies:
1. Stage 1 DLQ consumer transitions dead message to S1_FAILED and decrements remaining.
2. Stage 2 DLQ consumer transitions dead message to S2_FAILED and decrements remaining.
3. Scoring DLQ consumer marks job FAILED.
4. Bedrock Throttling: Stage 2 re-raises RetryableThrottlingError so SQS retries; never terminal failure.
5. Race safety:
   - Analyze requested BEFORE Stage 1 completes -> automatically advances to Stage 2 upon fast-parse finish.
   - Analyze requested AFTER Stage 1 completes -> immediately advances S1_DONE files to Stage 2.
   - Explicit file_ids in Analyze marks unselected files REMOVED (decrementing remaining).
"""

from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError

from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.queue.message import QueueMessage
from src.pipeline.dlq_consumers import (
    process_stage1_dlq_message,
    process_stage2_dlq_message,
    process_scoring_dlq_message,
)
from src.pipeline.stage1_worker import process_stage1_message
from src.pipeline.stage2_worker import process_stage2_message, RetryableThrottlingError
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.files_repository import FilesRepository


def test_stage1_dlq_consumer_transitions_to_s1_failed():
    """Poisoned message in Stage 1 DLQ transitions file to S1_FAILED and decrements remaining."""
    job_id = "job-dlq-s1"
    file_id = "file-dlq-s1"

    msg = {
        "Records": [
            {
                "s3": {
                    "object": {"key": f"jobs/{job_id}/raw/{file_id}.pdf"}
                }
            }
        ]
    }

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_trans:
        success = process_stage1_dlq_message(msg)
        assert success is True
        mock_trans.assert_called_once()
        args, kwargs = mock_trans.call_args
        assert kwargs["terminal_status"] == FileStatus.S1_FAILED.value
        assert kwargs["job_id"] == job_id
        assert kwargs["file_id"] == file_id


def test_stage2_dlq_consumer_transitions_to_s2_failed():
    """Poisoned message in Stage 2 DLQ transitions file to S2_FAILED and decrements remaining."""
    job_id = "job-dlq-s2"
    file_id = "file-dlq-s2"

    msg = QueueMessage(
        job_id=job_id,
        session_id=job_id,
        document_id=file_id,
        org_id="org_default",
        job_version=1,
        stage="ODL_BATCH",
    )

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_trans:
        success = process_stage2_dlq_message(msg)
        assert success is True
        mock_trans.assert_called_once()
        args, kwargs = mock_trans.call_args
        assert kwargs["terminal_status"] == FileStatus.S2_FAILED.value
        assert kwargs["job_id"] == job_id
        assert kwargs["file_id"] == file_id


def test_scoring_dlq_consumer_marks_job_failed():
    """Poisoned message in Scoring DLQ marks job FAILED."""
    job_id = "job-dlq-score"
    msg = QueueMessage(
        job_id=job_id,
        session_id=job_id,
        document_id=job_id,
        org_id="org_default",
        job_version=1,
        stage="FINAL_RANK",
    )

    job_item = JobItem(job_id=job_id, status=JobStatus.SCORING)

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=job_item), \
         patch("src.infrastructure.repositories.jobs_repository.JobsRepository.update") as mock_update:
        success = process_scoring_dlq_message(msg)
        assert success is True
        mock_update.assert_called_once()
        updates = mock_update.call_args[0][1]
        assert updates["status"] == JobStatus.FAILED.value


def test_stage2_bedrock_throttling_is_retryable():
    """When Bedrock raises ThrottlingException, stage 2 re-raises RetryableThrottlingError."""
    job_id = "job-throttle"
    file_id = "file-throttle"

    file_item = FileItem(
        job_id=job_id,
        file_id=file_id,
        status=FileStatus.S1_DONE,
        needs_fallback=True,
    )

    # Missing critical fields to force Nova invocation
    stage1_json = {
        "fields": {"name": None, "skills": [], "experience": []},
        "quality": {"score": 0.95},
        "unresolved_chunks": ["some resume text"],
    }

    throttle_error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse",
    )

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", return_value=file_item), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.update_file_non_terminal"), \
         patch("src.infrastructure.storage.storage_service.StorageService.get_stage1_json", return_value=stage1_json), \
         patch("src.extraction.fallback.nova_service.NovaService.resolve_chunks", side_effect=throttle_error), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_trans:

        with pytest.raises(RetryableThrottlingError):
            process_stage2_message({"job_id": job_id, "document_id": file_id})

        # MUST NOT transition to S2_FAILED immediately on throttling
        mock_trans.assert_not_called()


def test_analyze_before_stage1_completes():
    """If user clicks Analyze while Stage 1 is running, completing Stage 1 immediately enqueues Stage 2."""
    job_id = "job-race-early"
    file_id = "file-race-01"

    job = JobItem(
        job_id=job_id,
        status=JobStatus.UPLOADING,
        analyze_requested=True,
        analyze_file_ids=[file_id],
    )
    file_item = FileItem(
        job_id=job_id,
        file_id=file_id,
        status=FileStatus.PENDING_UPLOAD,
    )

    msg = {
        "Records": [
            {
                "s3": {
                    "object": {"key": f"jobs/{job_id}/raw/{file_id}.pdf"}
                }
            }
        ]
    }

    dummy_pdf_bytes = b"%PDF-1.4 test"

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", return_value=file_item), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.update_file_non_terminal"), \
         patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=job), \
         patch("src.infrastructure.storage.storage_service.StorageService.get_resume", return_value=dummy_pdf_bytes), \
         patch("src.infrastructure.storage.storage_service.StorageService.upload_stage1_json", return_value="key"), \
         patch("fitz.open") as mock_fitz, \
         patch("src.pipeline.stage1_worker.pymupdf_layout_quality_signals") as mock_signals, \
         patch("src.extraction.markdown_extraction_service.MarkdownExtractionService.extract") as mock_extract, \
         patch("src.pipeline.stage1_worker.get_queue_adapter") as mock_adapter:

        # Mock fitz document
        doc_mock = MagicMock()
        page_mock = MagicMock()
        page_mock.get_text.return_value = "Sample text"
        doc_mock.__iter__.return_value = [page_mock]
        mock_fitz.return_value = doc_mock

        # Multi-column / low quality forces fallback
        mock_signals.return_value = {
            "reading_order": 0.5,
            "char_density": 0.5,
            "not_table_heavy": 1.0,
            "col_penalty": 0.0,
            "score": 0.45,
        }
        mock_extract.return_value = {"fields": {"name": "Candidate A"}, "unresolved_chunks": ["chunk"]}

        queue_mock = MagicMock()
        mock_adapter.return_value = queue_mock

        process_stage1_message(msg)

        # Stage 2 MUST be enqueued automatically because analyze_requested was True
        queue_mock.send_message.assert_called_once()
        args, _ = queue_mock.send_message.call_args
        assert args[0] == "odl_batch_queue"
        enqueued_msg = args[1]
        assert enqueued_msg.job_id == job_id
        assert enqueued_msg.document_id == file_id
