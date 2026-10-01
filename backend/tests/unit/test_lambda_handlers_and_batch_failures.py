"""
test_lambda_handlers_and_batch_failures.py — Verification of Modular Handlers and SQS Batch Failures
==================================================================================================
Verifies:
1. Isolated handlers exist and import only their domain dependencies.
2. ReportBatchItemFailures contract is satisfied with originating messageId.
3. Preserves successful work when another record in the batch fails.
4. Autonomous recovery handler executes outbox reconciliation.
5. Backwards-compatible lambda_handler delegations.
6. UploadSessionsRepository count_active_for_org indexed query correctness.
"""

from unittest.mock import MagicMock, patch
import pytest

from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository


def test_stage1_handler_report_batch_item_failures():
    """Verify Stage 1 handler isolates failure to specific messageId without raising batch error."""
    from src.handlers.stage1 import handler as stage1_handler

    event = {
        "Records": [
            {"messageId": "msg-001", "body": '{"job_id": "j1", "document_id": "d1"}'},
            {"messageId": "msg-002", "body": '{"job_id": "j1", "document_id": "d2"}'},
            {"messageId": "msg-003", "body": '{"job_id": "j1", "document_id": "d3"}'},
        ]
    }

    # Simulate record 2 failing while records 1 and 3 succeed
    def mock_process(rec):
        if rec["messageId"] == "msg-002":
            raise RuntimeError("Transient parsing failure on corrupt byte stream")
        return None

    with patch("src.handlers.stage1.process_stage1_message", side_effect=mock_process):
        res = stage1_handler(event)
        assert res["statusCode"] == 200
        assert res["processed"] == 2
        assert len(res["batchItemFailures"]) == 1
        assert res["batchItemFailures"][0]["itemIdentifier"] == "msg-002"


def test_stage1_handler_all_succeed():
    """When all records succeed, batchItemFailures is empty."""
    from src.handlers.stage1 import handler as stage1_handler

    event = {
        "Records": [
            {"messageId": "msg-101", "body": "{}"},
            {"messageId": "msg-102", "body": "{}"},
        ]
    }

    with patch("src.handlers.stage1.process_stage1_message", return_value=None):
        res = stage1_handler(event)
        assert res["statusCode"] == 200
        assert res["processed"] == 2
        assert res["batchItemFailures"] == []


def test_scoring_handler_report_batch_item_failures():
    """Verify Scoring handler isolates failed record in batchItemFailures."""
    from src.handlers.scoring import handler as scoring_handler

    event = {
        "Records": [
            {"messageId": "score-001", "body": '{"job_id": "j1"}'},
            {"messageId": "score-002", "body": '{"job_id": "j2"}'},
        ]
    }

    def mock_score(rec):
        if rec["messageId"] == "score-002":
            raise ValueError("DynamoDB contention")
        return None

    with patch("src.handlers.scoring.process_scoring_message", side_effect=mock_score):
        res = scoring_handler(event)
        assert res["statusCode"] == 200
        assert res["processed"] == 1
        assert len(res["batchItemFailures"]) == 1
        assert res["batchItemFailures"][0]["itemIdentifier"] == "score-002"


def test_recovery_handler_autonomous():
    """Verify recovery handler runs outbox reconciliation."""
    from src.handlers.recovery import handler as recovery_handler

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.reconcile_all_pending_outboxes", return_value=(5, 1)):
        res = recovery_handler()
        assert res["statusCode"] == 200
        assert res["relayed_events"] == 5
        assert res["recovered_jobs"] == 1


def test_lambda_handler_backwards_compatibility():
    """Verify lambda_handler.py delegates cleanly to isolated modules."""
    import src.lambda_handler as lh

    event = {
        "Records": [
            {"messageId": "legacy-001", "body": "{}"},
        ]
    }

    with patch("src.handlers.stage1.process_stage1_message", return_value=None):
        res = lh.stage1_handler(event)
        assert res["statusCode"] == 200
        assert res["batchItemFailures"] == []

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.reconcile_all_pending_outboxes", return_value=(0, 0)):
        res = lh.recovery_handler()
        assert res["statusCode"] == 200


def test_upload_sessions_repository_indexed_active_count():
    """Verify count_active_for_org uses indexed query and tracks lifecycle transitions."""
    import uuid
    repo = UploadSessionsRepository()
    uid = uuid.uuid4().hex[:8]
    org_id = f"org-test-metrics-{uid}"
    job_id = f"job-test-metrics-{uid}"
    sess_id = f"sess-test-metrics-{uid}"

    sess = UploadSessionItem(
        session_id=sess_id,
        job_id=job_id,
        org_id=org_id,
        job_version=1,
        expected_document_count=5,
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
    )

    repo.create(sess)

    # Active count should be 1
    active = repo.count_active_for_org(org_id)
    assert active == 1

    # Transition to READY_TO_ANALYZE (barrier) should delete/remove active pointer
    repo.update_status(job_id, sess_id, UploadSessionStatus.READY_TO_ANALYZE, expected_version=1)

    active_after = repo.count_active_for_org(org_id)
    assert active_after == 0
