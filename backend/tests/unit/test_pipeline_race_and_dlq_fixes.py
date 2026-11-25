"""
test_pipeline_race_and_dlq_fixes.py — Regression tests for live AWS preprod pipeline defects
===========================================================================================
Covers:
1. DynamoDB TransactionConflict retries in FilesRepository.transition_file_terminal.
2. Stage 1 & Stage 2 worker handling of non-terminal transition failures, corrupt PDFs, and deleted jobs.
3. DLQ consumers never poison-looping on deleted files or overwriting completed jobs with FAILED.
4. ScoringWorker optimistic lock retry, stale job_version discard, idempotent DONE skip, and deleted job ack.
5. analyze_job single-path dispatch (no duplicate coordinator + outbox scoring triggers).
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError

from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.repositories.files_repository import FilesRepository
from src.pipeline.dlq_consumers import (
    process_scoring_dlq_message,
    process_stage1_dlq_message,
    process_stage2_dlq_message,
)
from src.pipeline.scoring_worker import process_scoring_message
from src.pipeline.stage1_worker import process_stage1_message
from src.pipeline.stage2_worker import process_stage2_batch


def _tx_conflict_error() -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "TransactionCanceledException",
                "Message": "Transaction cancelled",
            },
            "CancellationReasons": [
                {"Code": "None"},
                {"Code": "TransactionConflict", "Message": "Transaction is ongoing for the item"},
            ],
        },
        "TransactWriteItems",
    )


def _cond_failed_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "UpdateItem",
    )


def test_transition_file_terminal_retries_transaction_conflict_and_succeeds():
    """Concurrent TransactionConflict on JOB#METADATA retries with backoff and succeeds."""
    mock_table = MagicMock()
    mock_table.name = "TestTable"
    attempts = {"count": 0}

    def fake_transact(TransactItems):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _tx_conflict_error()

    mock_table.transact_write_items.side_effect = fake_transact
    mock_table.get_item.return_value = {
        "Item": {
            "PK": "JOB#j1",
            "SK": "METADATA",
            "remaining": 5,
            "usable_files": 95,
            "analyze_requested": False,
        }
    }

    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=mock_table), \
         patch("time.sleep"):
        repo = FilesRepository()
        ok = repo.transition_file_terminal("j1", "f1", FileStatus.S2_DONE.value)

    assert ok is True
    assert attempts["count"] == 3


def test_transition_file_terminal_raises_when_transaction_conflict_exhausted():
    """Exhausted TransactionConflict retries must raise instead of silently returning False."""
    mock_table = MagicMock()
    mock_table.name = "TestTable"
    mock_table.transact_write_items.side_effect = _tx_conflict_error()
    mock_table.get_item.return_value = {
        "Item": {
            "PK": "JOB#j1",
            "SK": "FILE#f1",
            "job_id": "j1",
            "file_id": "f1",
            "filename": "a.pdf",
            "status": "S1_PROCESSING",
        }
    }

    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=mock_table), \
         patch("time.sleep"):
        repo = FilesRepository()
        with pytest.raises(ClientError):
            repo.transition_file_terminal("j1", "f1", FileStatus.S2_DONE.value)


def test_stage1_worker_retries_if_file_remains_non_terminal_and_acks_corrupt_terminal_pdf():
    """Stage1 returns False if transition fails to reach terminal, and True once corrupt PDF is S1_FAILED."""
    file_proc = FileItem(job_id="j1", file_id="f1", filename="a.pdf", status=FileStatus.UPLOADED)
    file_still_proc = FileItem(job_id="j1", file_id="f1", filename="a.pdf", status=FileStatus.S1_PROCESSING)
    file_failed = FileItem(job_id="j1", file_id="f1", filename="a.pdf", status=FileStatus.S1_FAILED)

    # Case 1: clean parse, but transition_file_terminal returns False while file is still non-terminal
    with patch("src.pipeline.stage1_worker.FilesRepository") as MockFilesRepo, \
         patch("src.pipeline.stage1_worker.StorageService") as MockStorage, \
         patch("src.pipeline.stage1_worker.run_isolated_pdf_parse") as MockParse, \
         patch("src.pipeline.stage1_worker.MarkdownExtractionService") as MockExt:
        files_inst = MagicMock()
        MockFilesRepo.return_value = files_inst
        files_inst.get_file.side_effect = [file_proc, file_still_proc]
        files_inst.claim_file.return_value = True
        files_inst.transition_file_terminal.return_value = False
        MockStorage.return_value.get_resume.return_value = b"%PDF-1.4 ok"
        MockParse.return_value = {"raw_text": "Jane Doe\nSoftware Engineer " * 10, "page_signals": [{"score": 0.95}], "hyperlinks": [], "first_page_visual_header": []}
        MockExt.return_value.extract.return_value = {
            "fields": {"name": "Jane Doe", "experience": [{"title": "Eng"}], "skills": ["Python"]},
            "unresolved_chunks": [],
        }
        ok = process_stage1_message({"job_id": "j1", "document_id": "f1"})
        assert ok is False

    # Case 2: permanent PDF corruption -> marked S1_FAILED -> returns True (no pointless 3x SQS retry into DLQ)
    with patch("src.pipeline.stage1_worker.FilesRepository") as MockFilesRepo, \
         patch("src.pipeline.stage1_worker.StorageService") as MockStorage, \
         patch("src.pipeline.stage1_worker.run_isolated_pdf_parse", side_effect=ValueError("corrupt pdf stream")):
        files_inst = MagicMock()
        MockFilesRepo.return_value = files_inst
        files_inst.get_file.side_effect = [file_proc, file_failed]
        files_inst.claim_file.return_value = True
        files_inst.transition_file_terminal.return_value = True
        MockStorage.return_value.get_resume.return_value = b"not-a-pdf"
        ok = process_stage1_message({"job_id": "j1", "document_id": "f1"})
        assert ok is True


def test_stage1_and_stage2_workers_ack_deleted_job_without_dlq_loop():
    """When job & file/doc were deleted, workers return/skip cleanly instead of retrying into DLQ."""
    with patch("src.pipeline.stage1_worker.FilesRepository") as MockFilesRepo, \
         patch("src.infrastructure.repositories.documents_repository.DocumentsRepository") as MockDocsRepo, \
         patch("src.pipeline.stage1_worker.JobsRepository") as MockJobsRepo:
        MockFilesRepo.return_value.get_file.return_value = None
        MockDocsRepo.return_value.get.return_value = None
        MockJobsRepo.return_value.get.return_value = None
        assert process_stage1_message({"job_id": "deleted-job", "document_id": "deleted-doc"}) is True

    with patch("src.pipeline.stage2_worker.FilesRepository") as MockFilesRepo, \
         patch("src.infrastructure.repositories.documents_repository.DocumentsRepository") as MockDocsRepo, \
         patch("src.pipeline.stage2_worker.JobsRepository") as MockJobsRepo:
        MockFilesRepo.return_value.get_file.return_value = None
        MockDocsRepo.return_value.get.return_value = None
        MockJobsRepo.return_value.get.return_value = None
        res = process_stage2_batch([{"messageId": "m-del", "body": json.dumps({"job_id": "deleted-job", "document_id": "deleted-doc"})}])
        assert res["failed_items"] == []


def test_dlq_consumers_ack_missing_deleted_entities_without_raising():
    """DLQ messages for already-deleted files/jobs must ack (return True) instead of looping forever."""
    with patch(
        "src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal",
        side_effect=ValueError("File job-del/file-del does not exist"),
    ):
        assert process_stage1_dlq_message({"job_id": "job-del", "document_id": "file-del"}) is True
        assert process_stage2_dlq_message({"job_id": "job-del", "document_id": "file-del"}) is True


def test_scoring_dlq_consumer_never_overwrites_completed_job_with_failed():
    """Scoring DLQ must not overwrite an already-DONE/READY job with FAILED."""
    done_job = JobItem(job_id="j-done", status=JobStatus.DONE, version=3)
    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=done_job), \
         patch("src.infrastructure.repositories.jobs_repository.JobsRepository.update") as mock_update:
        ok = process_scoring_dlq_message({"job_id": "j-done"})
        assert ok is True
        mock_update.assert_not_called()

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=None):
        assert process_scoring_dlq_message({"job_id": "j-deleted"}) is True


def test_scoring_worker_handles_concurrent_done_version_conflict_and_stale_job_version():
    """ScoringWorker retries optimistic lock conflicts, skips already-DONE/stale jobs, and acks deleted jobs."""
    # 1. Deleted job -> ack True
    with patch("src.pipeline.scoring_worker.JobsRepository") as MockJobsRepo:
        MockJobsRepo.return_value.get.return_value = None
        assert process_scoring_message({"job_id": "deleted-job"}) is True

    # 2. Stale job_version -> ack True without scoring
    newer_job = JobItem(job_id="j-stale", status=JobStatus.SCORING, job_version=2, version=2)
    with patch("src.pipeline.scoring_worker.JobsRepository") as MockJobsRepo, \
         patch("src.pipeline.scoring_worker.CandidateScorer") as MockScorer:
        MockJobsRepo.return_value.get.return_value = newer_job
        ok = process_scoring_message(QueueMessage(
            job_id="j-stale", session_id="j-stale", document_id="j-stale", org_id="o1", job_version=1, stage="FINAL_RANK"
        ))
        assert ok is True
        MockScorer.assert_not_called()

    # 3. Concurrent DONE update causes ConditionalCheckFailedException -> re-reads DONE and returns True without FAILED write
    initial_job = JobItem(job_id="j-race", status=JobStatus.SCORING, job_version=1, version=1)
    done_job = JobItem(job_id="j-race", status=JobStatus.DONE, job_version=1, version=2)
    f1 = FileItem(job_id="j-race", file_id="f1", filename="1.pdf", status=FileStatus.S2_DONE, candidate_name="Alice")

    with patch("src.pipeline.scoring_worker.JobsRepository") as MockJobsRepo, \
         patch("src.pipeline.scoring_worker.FilesRepository") as MockFilesRepo, \
         patch("src.pipeline.scoring_worker.ScoringRepository"), \
         patch("src.pipeline.scoring_worker.StorageService") as MockStorage, \
         patch("src.pipeline.scoring_worker.CandidateScorer") as MockScorer:
        jobs_inst = MagicMock()
        MockJobsRepo.return_value = jobs_inst
        jobs_inst.get.side_effect = [initial_job, done_job]
        jobs_inst.update.side_effect = _cond_failed_error()

        MockFilesRepo.return_value.list_files_for_job.return_value = [f1]
        MockStorage.return_value.get_stage2_json.return_value = {"name": "Alice", "skills": ["Python"]}

        from dataclasses import dataclass

        @dataclass
        class _Ranked:
            document_id: str = "f1"
            name: str = "Alice"
            final_score: float = 90.0

        MockScorer.return_value.rank.return_value = [_Ranked()]

        ok = process_scoring_message({"job_id": "j-race", "job_version": 1})
        assert ok is True
        # Must NOT have attempted to mark JobStatus.FAILED
        for call in jobs_inst.update.call_args_list:
            assert call[0][1].get("status") != JobStatus.FAILED.value


def test_analyze_job_does_not_double_dispatch_scoring_when_files_exist(monkeypatch):
    """analyze_job must not invoke coordinator final-rank dispatch on top of request_analysis outbox when FileItems exist."""
    from fastapi.testclient import TestClient
    from src.main import create_app

    job = JobItem(job_id="j-no-dup", org_id="job_j-no-dup", status=JobStatus.READY_TO_ANALYZE, job_version=1, version=1)
    f1 = FileItem(job_id="j-no-dup", file_id="f1", filename="1.pdf", status=FileStatus.S2_DONE)
    sess = MagicMock()
    sess.session_id = "s-1"
    sess.version = 1
    sess.created_at = "2026-11-25T00:00:00Z"

    with patch("src.api.routes.jobs_v2._jobs_repo") as mock_jobs, \
         patch("src.api.routes.jobs_v2._files_repo") as mock_files, \
         patch("src.api.routes.jobs_v2._sessions_repo") as mock_sessions, \
         patch("src.api.routes.jobs_v2.check_and_progress_session") as mock_coord, \
         patch("src.api.routes.jobs_v2.audit_logger"):
        mock_jobs.get.return_value = job
        mock_jobs.request_analysis.return_value = JobItem(job_id="j-no-dup", status=JobStatus.SCORING, remaining=0, usable_files=1)
        mock_files.list_files_for_job.return_value = [f1]
        mock_sessions.list_for_job.return_value = [sess]

        client = TestClient(create_app())
        resp = client.post("/api/v2/jobs/j-no-dup/analyze", json={})
        assert resp.status_code == 202
        mock_coord.assert_not_called()


def test_delete_resume_uses_get_file_and_deletes_recorded_s3_keys():
    """DELETE /resumes/{doc_id} must call FilesRepository.get_file (not nonexistent .get) and delete S3 keys."""
    from fastapi.testclient import TestClient
    from src.main import create_app

    job = JobItem(job_id="j-del-res", org_id="job_j-del-res", status=JobStatus.READY_TO_ANALYZE)
    real_files_repo = FilesRepository.__new__(FilesRepository)
    real_files_repo._table = MagicMock()
    real_files_repo.transition_file_terminal = MagicMock(return_value=True)
    real_files_repo.get_file = MagicMock(
        return_value=FileItem(
            job_id="j-del-res",
            file_id="doc-1",
            filename="1.pdf",
            status=FileStatus.REMOVED,
            s3_raw_key="job_j-del-res/jobs/j-del-res/sessions/s1/resumes/doc-1.pdf",
        )
    )

    with patch("src.api.routes.jobs_v2._jobs_repo") as mock_jobs, \
         patch("src.api.routes.jobs_v2._files_repo", real_files_repo), \
         patch("src.api.routes.jobs_v2._docs_repo") as mock_docs, \
         patch("src.api.routes.jobs_v2._storage") as mock_storage, \
         patch("src.api.routes.jobs_v2.audit_logger"):
        mock_jobs.get.return_value = job
        mock_docs.get.return_value = None

        client = TestClient(create_app())
        resp = client.delete("/api/v2/jobs/j-del-res/resumes/doc-1")
        assert resp.status_code == 200
        deleted_keys = {c[1]["Key"] for c in mock_storage._client.delete_object.call_args_list}
        assert "job_j-del-res/jobs/j-del-res/sessions/s1/resumes/doc-1.pdf" in deleted_keys
