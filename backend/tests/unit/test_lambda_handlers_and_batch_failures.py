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


def test_stage2_handler_report_batch_item_failures():
    """Verify Stage 2 handler isolates poisoned/throttled record in batchItemFailures."""
    from src.handlers.stage2 import handler as stage2_handler

    event = {
        "Records": [
            {"messageId": "s2-msg-001", "body": '{"job_id": "j1", "document_ids": ["d1"]}'},
            {"messageId": "s2-msg-002", "body": '{"job_id": "j1", "document_ids": ["d2"]}'},
        ]
    }

    # Simulate batch processing where message s2-msg-002 fails/throttles while s2-msg-001 succeeds
    mock_batch_result = {
        "processed": 1,
        "succeeded": 1,
        "failed_items": ["s2-msg-002"],
    }

    with patch("src.handlers.stage2.process_stage2_batch", return_value=mock_batch_result):
        res = stage2_handler(event)
        assert res["statusCode"] == 200
        assert res["processed"] == 1
        assert len(res["batchItemFailures"]) == 1
        assert res["batchItemFailures"][0]["itemIdentifier"] == "s2-msg-002"



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


def test_stage1_worker_claim_failure_returns_false_and_reported_in_batch_failures():
    """Verify Stage 1 worker returns False when claim fails on non-terminal item, avoiding silent drop."""
    import json
    from src.pipeline.stage1_worker import process_stage1_message
    from src.handlers.stage1 import handler as stage1_handler
    from src.infrastructure.models.file import FileItem, FileStatus

    mock_file = FileItem(
        job_id="j-claim-fail",
        file_id="f-claim-fail",
        filename="resume.pdf",
        status=FileStatus.S1_PROCESSING,  # already leased / non-terminal
    )

    with patch("src.pipeline.stage1_worker.FilesRepository") as MockFilesRepo:
        repo_inst = MagicMock()
        MockFilesRepo.return_value = repo_inst
        repo_inst.get_file.return_value = mock_file
        repo_inst.claim_file.return_value = False  # cannot claim active lease

        # Direct worker invocation must return False (do not ack)
        msg = {
            "messageId": "msg-sqs-claim-fail-001",
            "body": json.dumps({"job_id": "j-claim-fail", "document_id": "f-claim-fail"}),
        }
        ok = process_stage1_message(msg)
        assert ok is False

        # Handler invocation must add to batchItemFailures with originating messageId
        event = {"Records": [msg]}
        res = stage1_handler(event)
        assert res["statusCode"] == 200
        assert len(res["batchItemFailures"]) == 1
        assert res["batchItemFailures"][0]["itemIdentifier"] == "msg-sqs-claim-fail-001"


def test_stage1_worker_materializes_fileitem_from_docitem():
    """Verify Stage 1 worker checks DocumentItem and materializes FileItem when only DocumentItem exists."""
    import json
    from src.pipeline.stage1_worker import process_stage1_message
    from src.infrastructure.models.document import DocumentItem, DocumentStatus

    mock_doc = DocumentItem(
        job_id="j-doc-mat",
        document_id="d-doc-mat",
        filename="candidate.pdf",
        file_size=12345,
        s3_pdf_key="jobs/j-doc-mat/raw/d-doc-mat.pdf",
        status=DocumentStatus.UPLOADED,
    )

    with patch("src.pipeline.stage1_worker.FilesRepository") as MockFilesRepo, \
         patch("src.infrastructure.repositories.documents_repository.DocumentsRepository") as MockDocsRepo, \
         patch("src.pipeline.stage1_worker.StorageService") as MockStorage, \
         patch("src.pipeline.stage1_worker.run_isolated_pdf_parse") as MockParse:

        files_repo_inst = MagicMock()
        docs_repo_inst = MagicMock()
        MockFilesRepo.return_value = files_repo_inst
        MockDocsRepo.return_value = docs_repo_inst

        # Initially FileItem not found in files_repo
        files_repo_inst.get_file.return_value = None
        # DocumentItem found in docs_repo
        docs_repo_inst.get.return_value = mock_doc
        files_repo_inst.claim_file.return_value = True

        MockStorage.return_value.get_resume.return_value = b"%PDF-1.4 mock content"
        MockParse.return_value = {
            "raw_text": "Alice Smith Python Developer",
            "page_signals": [{"char_density": 50.0, "column_count": 1}],
            "hyperlinks": [],
            "pages": 1,
        }

        with patch("src.pipeline.stage1_worker.JobsRepository"):
            msg = {
                "messageId": "msg-mat-001",
                "body": json.dumps({"job_id": "j-doc-mat", "document_id": "d-doc-mat"}),
            }
            ok = process_stage1_message(msg)
            assert ok is True

            # Verify files_repo.create_files was called to materialize FileItem
            files_repo_inst.create_files.assert_called_once()
            created_items = files_repo_inst.create_files.call_args[0][1]
            assert len(created_items) == 1
            assert created_items[0].file_id == "d-doc-mat"
            assert created_items[0].filename == "candidate.pdf"


def test_stage2_worker_raw_sqs_dict_message_id_preservation_on_throttling():
    """Verify Stage 2 preserves raw SQS dict messageId, isolates throttling, and releases lease."""
    import json
    from src.pipeline.stage2_worker import process_stage2_batch
    from src.extraction.fallback.nova_service import NovaThrottlingError
    from src.infrastructure.models.file import FileItem, FileStatus

    f1 = FileItem(job_id="j-raw", file_id="f1", filename="f1.pdf", status=FileStatus.S1_DONE)
    f2 = FileItem(job_id="j-raw", file_id="f2", filename="f2.pdf", status=FileStatus.S1_DONE)

    messages = [
        {"messageId": "sqs-msg-success-1", "body": json.dumps({"job_id": "j-raw", "document_id": "f1"})},
        {"messageId": "sqs-msg-throttled-2", "body": json.dumps({"job_id": "j-raw", "document_id": "f2"})},
    ]

    with patch("src.pipeline.stage2_worker.FilesRepository") as MockFilesRepo, \
         patch("src.pipeline.stage2_worker.StorageService") as MockStorage, \
         patch("src.pipeline.stage2_worker.NovaService") as MockNova:

        files_inst = MagicMock()
        MockFilesRepo.return_value = files_inst
        files_inst.get_file.side_effect = lambda j, f: f1 if f == "f1" else f2
        files_inst.claim_file.return_value = True
        files_inst.reserve_llm_slot.return_value = (True, None)

        storage_inst = MagicMock()
        MockStorage.return_value = storage_inst
        storage_inst.get_stage1_json.return_value = {
            "fields": {},
            "quality": {"score": 0.95},
            "unresolved_chunks": ["some missing text"],
            "raw_text": "Jane Doe",
        }
        storage_inst.upload_stage2_json.return_value = "jobs/j-raw/stage2/f1.json"

        nova_inst = MagicMock()
        MockNova.return_value = nova_inst
        call_count = [0]
        def mock_resolve(chunks, existing_fields=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise NovaThrottlingError("Rate exceeded for Bedrock Nova")
            return {"name": "Candidate One", "skills": ["Python"]}
        nova_inst.resolve_chunks.side_effect = mock_resolve

        res = process_stage2_batch(messages)

        # MessageId "sqs-msg-throttled-2" must be in failed_items
        assert "sqs-msg-throttled-2" in res["failed_items"]
        # Success count must be 1 (f1 succeeded)
        assert res["succeeded"] == 1
        # f2 lease must be reset to S1_DONE for SQS redrive
        files_inst.update_file_non_terminal.assert_called_with("j-raw", "f2", FileStatus.S1_DONE)


def test_stage2_worker_head_object_retry_and_oversized_bypass():
    """Verify HeadObject retries 3 times on failure and oversized docs bypass ODL to Nova."""
    import json
    from src.pipeline.stage2_worker import process_stage2_batch, MAX_ODL_BYTE_BUDGET
    from src.infrastructure.models.file import FileItem, FileStatus

    f_oversized = FileItem(
        job_id="j-size",
        file_id="f-large",
        filename="huge.pdf",
        status=FileStatus.S1_DONE,
        file_size=MAX_ODL_BYTE_BUDGET + 1024,  # > 20 MB
    )
    f_missing_head = FileItem(
        job_id="j-size",
        file_id="f-no-head",
        filename="broken.pdf",
        status=FileStatus.S1_DONE,
        file_size=0,  # size unknown, must call HeadObject
    )

    messages = [
        {"messageId": "msg-oversized", "body": json.dumps({"job_id": "j-size", "document_id": "f-large"})},
        {"messageId": "msg-no-head", "body": json.dumps({"job_id": "j-size", "document_id": "f-no-head"})},
    ]

    with patch("src.pipeline.stage2_worker.FilesRepository") as MockFilesRepo, \
         patch("src.pipeline.stage2_worker.StorageService") as MockStorage, \
         patch("src.pipeline.stage2_worker.parse_batch") as MockParseBatch, \
         patch("src.pipeline.stage2_worker.NovaService") as MockNova:

        files_inst = MagicMock()
        MockFilesRepo.return_value = files_inst
        files_inst.get_file.side_effect = lambda j, f: f_oversized if f == "f-large" else f_missing_head
        files_inst.claim_file.return_value = True
        files_inst.reserve_llm_slot.return_value = (True, None)

        storage_inst = MagicMock()
        MockStorage.return_value = storage_inst
        storage_inst._bucket = "test-bucket"
        storage_inst.get_stage1_json.return_value = {
            "fields": {"name": "Bob"},
            "quality": {"score": 0.50},  # triggers ODL candidate
            "raw_text": "Bob text",
        }
        storage_inst._client.head_object.side_effect = Exception("S3 503 SlowDown")

        nova_inst = MagicMock()
        MockNova.return_value = nova_inst
        nova_inst.resolve_chunks.return_value = {"name": "Bob", "skills": ["AWS"]}

        res = process_stage2_batch(messages)

        # 1. f-no-head failed size verification after 3 retries and was failed closed into failed_items
        assert "msg-no-head" in res["failed_items"]
        assert storage_inst._client.head_object.call_count == 3

        # 2. f-large was bypassed from parse_batch because it exceeds MAX_ODL_BYTE_BUDGET
        MockParseBatch.assert_not_called()

        # 3. f-large proceeded to Nova fallback successfully
        assert res["succeeded"] == 1


def test_upload_sessions_atomic_admission_counter_and_pagination():
    """Verify admit_and_create_session enforces quota atomically and count_active_for_org paginates."""
    import uuid
    from src.infrastructure.repositories.upload_sessions_repository import (
        UploadSessionsRepository,
        QuotaExceededError,
        AdmissionVerificationError,
    )
    from src.infrastructure.models.upload_session import UploadSessionItem, UploadSessionStatus

    repo = UploadSessionsRepository()
    uid = uuid.uuid4().hex[:8]
    org_id = f"org-admit-{uid}"
    job_id = f"job-admit-{uid}"

    # Admit session 1 with limit 2 -> succeeds
    sess1 = UploadSessionItem(
        session_id=f"sess-1-{uid}",
        job_id=job_id,
        org_id=org_id,
        job_version=1,
        expected_document_count=5,
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
    )
    repo.admit_and_create_session(sess1, max_active=2)

    # Admit session 2 with limit 2 -> succeeds
    sess2 = UploadSessionItem(
        session_id=f"sess-2-{uid}",
        job_id=job_id,
        org_id=org_id,
        job_version=1,
        expected_document_count=3,
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
    )
    repo.admit_and_create_session(sess2, max_active=2)

    # Admit session 3 with limit 2 -> QuotaExceededError
    sess3 = UploadSessionItem(
        session_id=f"sess-3-{uid}",
        job_id=job_id,
        org_id=org_id,
        job_version=1,
        expected_document_count=2,
        uploaded_document_count=0,
        status=UploadSessionStatus.UPLOADING,
    )
    with pytest.raises(QuotaExceededError):
        repo.admit_and_create_session(sess3, max_active=2)

    # Transition sess1 to READY_TO_ANALYZE -> decrements counter
    repo.update_status(job_id, sess1.session_id, UploadSessionStatus.READY_TO_ANALYZE, expected_version=1)

    # Now sess3 can be admitted!
    repo.admit_and_create_session(sess3, max_active=2)

    # Test count_active_for_org pagination across LastEvaluatedKey
    with patch.object(repo._table, "query") as mock_query:
        mock_query.side_effect = [
            {"Items": [{"session_id": "s1", "status": UploadSessionStatus.UPLOADING.value}], "LastEvaluatedKey": {"PK": "k1"}},
            {"Items": [{"session_id": "s2", "status": UploadSessionStatus.UPLOADING.value}], "LastEvaluatedKey": {"PK": "k2"}},
            {"Items": [{"session_id": "s3", "status": UploadSessionStatus.UPLOADING.value}]},
        ]
        cnt = repo.count_active_for_org("org-paginated")
        assert cnt == 3
        assert mock_query.call_count == 3

    # Test AdmissionVerificationError on query failure
    with patch.object(repo._table, "query", side_effect=Exception("DynamoDB 500")):
        with pytest.raises(AdmissionVerificationError):
            repo.count_active_for_org("org-err")
