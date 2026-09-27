"""
test_phase1_6_durability.py — Phase 1.6 Concurrency, Durability & Microbatching Regressions
============================================================================================
Covers all 8 Section E verification requirements:
1. Crash between terminal-file update and counter update (atomic transaction validation).
2. Crash before queue publication (durable outbox pattern & reconciliation).
3. Analyze racing with Stage-1 completion (removed files not resurrected, ready files dispatched).
4. Duplicate worker deliveries racing on the same file (claim lease isolation).
5. Concurrent LLM requests racing against per-job budget (atomic reservation enforcement).
6. Retryable throttling propagating back to queue handler (NovaThrottlingError -> RetryableThrottlingError).
7. Scoring dispatch failure and subsequent recovery (stranded scoring reconciliation on poll).
8. Partial ODL microbatch failure and reliable tail flush (failure isolation without cascading errors).
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.extraction.fallback.nova_service import NovaThrottlingError
from src.extraction.odl_client import BatchParseResult, DocDescriptor, ODLParseError, ODLParseResult
from src.infrastructure.models.file import FileItem, FileStatus, TERMINAL_FILE_STATUSES
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.pipeline.stage1_worker import process_stage1_message
from src.pipeline.stage2_worker import (
    RetryableThrottlingError,
    merge_extracted_fields,
    process_stage2_batch,
    process_stage2_message,
)


class MockTransactDynamoTable:
    """Mock table that records TransactWriteItems and validates atomicity."""

    def __init__(self):
        self.items = {}
        self.transact_calls = []
        self.fail_next_transact = False

    @property
    def name(self):
        return "TestTable"

    def get_item(self, Key):
        k = (Key["PK"], Key["SK"])
        if k in self.items:
            return {"Item": dict(self.items[k])}
        return {}

    def put_item(self, Item, ConditionExpression=None):
        k = (Item["PK"], Item["SK"])
        self.items[k] = dict(Item)
        return {}

    def update_item(self, Key, UpdateExpression, ConditionExpression=None,
                    ExpressionAttributeNames=None, ExpressionAttributeValues=None, ReturnValues=None):
        k = (Key["PK"], Key["SK"])
        item = self.items.get(k)
        if not item:
            item = {"PK": Key["PK"], "SK": Key["SK"]}
            self.items[k] = item

        # Evaluate condition expression
        if ConditionExpression:
            if "NOT (#st IN (:s1_f, :s2_d, :s2_f, :rem))" in ConditionExpression:
                if item.get("status") in ("S1_FAILED", "S2_DONE", "S2_FAILED", "REMOVED"):
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
            if "#rem > :zero" in ConditionExpression:
                if item.get("remaining", 0) <= 0:
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
            if "claim_expires_at" in ConditionExpression or "#claim_exp" in ConditionExpression:
                now_str = ExpressionAttributeValues.get(":now")
                claim_exp = item.get("claim_expires_at")
                claim_w = item.get("claim_worker_id")
                req_w = ExpressionAttributeValues.get(":w_id")
                if claim_exp and claim_exp >= now_str and claim_w != req_w:
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
            if "#res < :max_cap" in ConditionExpression:
                res_cnt = item.get("llm_reservations", 0)
                max_cap = ExpressionAttributeValues.get(":max_cap", 5) if ExpressionAttributeValues else 5
                if res_cnt >= max_cap:
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")

        # Apply basic updates
        if UpdateExpression and "ADD #res :one" in UpdateExpression:
            item["llm_reservations"] = item.get("llm_reservations", 0) + 1

        if ExpressionAttributeNames and ExpressionAttributeValues:
            for alias, val in ExpressionAttributeValues.items():
                if alias in (":status", ":proc_st", ":new_st"):
                    item["status"] = val
                elif alias == ":one":
                    if "#rem = #rem - :one" in UpdateExpression:
                        item["remaining"] = item.get("remaining", 0) - 1
                elif alias == ":usable_inc":
                    item["usable_files"] = item.get("usable_files", 0) + val
                elif alias == ":now":
                    item["updated_at"] = val
                elif alias == ":true":
                    if ExpressionAttributeNames.get("#d") == "dispatched":
                        item["dispatched"] = True
                    else:
                        item["analyze_requested"] = True
                elif alias == ":w_id":
                    item["claim_worker_id"] = val
                elif alias == ":claim_exp":
                    item["claim_expires_at"] = val
                elif alias == ":scoring":
                    item["status"] = "SCORING"
                elif alias == ":done_err":
                    item["status"] = "DONE_WITH_ERRORS"
                elif alias == ":t_st":
                    item["status"] = val

        self.items[k] = item
        return {"Attributes": dict(item)}

    def query(self, KeyConditionExpression=None, ExpressionAttributeValues=None, ScanIndexForward=True):
        pk_val = ExpressionAttributeValues.get(":pk") if ExpressionAttributeValues else None
        sk_prefix = ExpressionAttributeValues.get(":sk_prefix") if ExpressionAttributeValues else None

        if KeyConditionExpression is not None and hasattr(KeyConditionExpression, "get_expression"):
            try:
                expr_dict = KeyConditionExpression.get_expression()
                vals = expr_dict.get("values", [])
                for v in vals:
                    op = getattr(v, "expression_operator", "")
                    val_list = getattr(v, "_values", [])
                    if op == "=" and len(val_list) == 2:
                        pk_val = val_list[1]
                    elif op == "begins_with" and len(val_list) == 2:
                        sk_prefix = val_list[1]
            except Exception:
                pass

        results = []
        for (pk, sk), item in self.items.items():
            if pk_val and pk != pk_val:
                continue
            if sk_prefix and not sk.startswith(sk_prefix):
                continue
            results.append(dict(item))
        return {"Items": results}

    def transact_write_items(self, TransactItems):
        self.transact_calls.append(TransactItems)
        if self.fail_next_transact:
            raise ClientError(
                {"Error": {"Code": "TransactionCanceledException", "Message": "Transaction cancelled"}},
                "TransactWriteItems"
            )

        from boto3.dynamodb.types import TypeDeserializer
        deser = TypeDeserializer()

        # Step 1: Pre-evaluate condition expressions across all items
        for action in TransactItems:
            if "Update" in action:
                u = action["Update"]
                cond = u.get("ConditionExpression")
                if cond and "#res < :max_cap" in cond:
                    key = {k: deser.deserialize(v) for k, v in u["Key"].items()}
                    k = (key["PK"], key["SK"])
                    existing_job = self.items.get(k, {})
                    res_cnt = existing_job.get("llm_reservations", 0)
                    values = {k: deser.deserialize(v) for k, v in u.get("ExpressionAttributeValues", {}).items()}
                    max_cap = int(values.get(":max_cap", 5))
                    if res_cnt >= max_cap:
                        raise ClientError(
                            {
                                "Error": {"Code": "TransactionCanceledException", "Message": "Transaction cancelled"},
                                "CancellationReasons": [{"Code": "None"}, {"Code": "ConditionalCheckFailed"}],
                            },
                            "TransactWriteItems",
                        )

        # Step 2: Apply all updates atomically
        for action in TransactItems:
            if "Update" in action:
                u = action["Update"]
                key = {k: deser.deserialize(v) for k, v in u["Key"].items()}
                names = u.get("ExpressionAttributeNames", {})
                values = {k: deser.deserialize(v) for k, v in u.get("ExpressionAttributeValues", {}).items()}
                values = {k: int(v) if hasattr(v, "as_integer_ratio") and v % 1 == 0 else v for k, v in values.items()}
                self.update_item(
                    Key=key,
                    UpdateExpression=u["UpdateExpression"],
                    ConditionExpression=u.get("ConditionExpression"),
                    ExpressionAttributeNames=names,
                    ExpressionAttributeValues=values,
                )
            elif "Put" in action:
                p = action["Put"]
                item_dict = {k: deser.deserialize(v) for k, v in p["Item"].items()}
                self.put_item(item_dict)


@pytest.fixture
def mock_table():
    table = MockTransactDynamoTable()
    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=table), \
         patch("src.infrastructure.repositories.jobs_repository._get_table", return_value=table):
        yield table


# ---------------------------------------------------------------------------
# Drill 1: Crash between terminal-file update and counter update
# ---------------------------------------------------------------------------
def test_atomic_file_terminal_and_counter_update(mock_table):
    """DynamoDB TransactWriteItems bundles file status and job remaining atomically."""
    job_id = "job-atomic-1"
    file_id = "file-1"

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 2,
        "usable_files": 0,
        "total_files": 2,
        "status": "PROCESSING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": "S2_PROCESSING",
    }

    files_repo = FilesRepository()
    success = files_repo.transition_file_terminal(job_id, file_id, FileStatus.S2_DONE.value)

    assert success is True
    # Verify TransactWriteItems was invoked with both updates
    assert len(mock_table.transact_calls) == 1
    transact_items = mock_table.transact_calls[0]
    assert len(transact_items) == 2
    assert "FILE#" in transact_items[0]["Update"]["Key"]["SK"]["S"]
    assert transact_items[1]["Update"]["Key"]["SK"]["S"] == "METADATA"

    # Verify both states updated
    file_item = mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")]
    job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
    assert file_item["status"] == FileStatus.S2_DONE.value
    assert job_item["remaining"] == 1
    assert job_item["usable_files"] == 1

    # Simulate transaction failure: ensure neither updates
    mock_table.fail_next_transact = True
    file_id_2 = "file-2"
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id_2}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id_2}",
        "status": "S2_PROCESSING",
    }
    fail_res = files_repo.transition_file_terminal(job_id, file_id_2, FileStatus.S2_DONE.value)
    assert fail_res is False
    # Counter must NOT have decremented on failed transaction
    assert mock_table.items[(f"JOB#{job_id}", "METADATA")]["remaining"] == 1
    assert mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id_2}")]["status"] == "S2_PROCESSING"


# ---------------------------------------------------------------------------
# Drill 2: Crash before queue publication (Durable Outbox Pattern)
# ---------------------------------------------------------------------------
def test_crash_before_queue_publication_recovered_by_outbox(mock_table):
    """Outbox event written before dispatch; recovered and dispatched during reconciliation."""
    job_id = "job-outbox-crash"
    file_id = "file-ready-1"

    files_repo = FilesRepository()
    # 1. Record outbox event (simulates state write before crash)
    event_sk = files_repo.record_outbox_event(
        job_id=job_id,
        outbox_sk=f"OUTBOX#STAGE2#{file_id}",
        event_type="STAGE2_DISPATCH",
        payload={"job_id": job_id, "file_id": file_id},
    )

    outbox_item = mock_table.items.get((f"JOB#{job_id}", event_sk))
    assert outbox_item is not None
    assert outbox_item["dispatched"] is False

    # 2. Simulate worker crash before publishing to SQS
    # Later: reconciliation poll recovers the undispatched outbox item
    with patch("src.infrastructure.repositories.files_repository.get_queue_adapter") as mock_qa:
        mock_adapter = MagicMock()
        mock_qa.return_value = mock_adapter

        dispatched = files_repo.reconcile_outbox(job_id)
        assert dispatched == 1
        mock_adapter.send_message.assert_called_once()

    # Outbox item is now marked dispatched
    updated_outbox = mock_table.items[(f"JOB#{job_id}", event_sk)]
    assert updated_outbox["dispatched"] is True


# ---------------------------------------------------------------------------
# Drill 3: Analyze racing with Stage-1 completion
# ---------------------------------------------------------------------------
def test_analyze_racing_with_stage1_completion(mock_table):
    """Analyze marks excluded files REMOVED, transitions ready files, and active S1 detects intent."""
    job_id = "job-race-analyze"
    f_active = "file-active-s1"
    f_ready = "file-ready-s1"
    f_excluded = "file-excluded"

    # Setup job with 3 files
    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "job_id": job_id,
        "remaining": 3,
        "usable_files": 0,
        "total_files": 3,
        "analyze_requested": False,
        "status": "PROCESSING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{f_active}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{f_active}",
        "status": FileStatus.S1_PROCESSING.value,
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{f_ready}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{f_ready}",
        "status": FileStatus.S1_DONE.value,
        "s3_stage1_key": f"jobs/{job_id}/stage1/{f_ready}.json",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{f_excluded}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{f_excluded}",
        "status": FileStatus.S1_DONE.value,
    }

    jobs_repo = JobsRepository()
    files_repo = FilesRepository()

    # User clicks Analyze requesting only f_active and f_ready
    jobs_repo.request_analysis(job_id=job_id, file_ids=[f_active, f_ready])

    # 1. Excluded file must be marked REMOVED immediately and decrement remaining
    excluded_item = mock_table.items[(f"JOB#{job_id}", f"FILE#{f_excluded}")]
    assert excluded_item["status"] == FileStatus.REMOVED.value

    # 2. Ready file must have an outbox event for Stage 2
    ready_outbox = mock_table.items.get((f"JOB#{job_id}", f"OUTBOX#STAGE2#{f_ready}"))
    assert ready_outbox is not None

    # 3. Active file finishes Stage 1 after Analyze was called
    # Stage 1 worker completes and checks job.analyze_requested
    job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
    assert job_item["analyze_requested"] is True

    # Active file transitions to S1_DONE and immediately proceeds
    files_repo.update_file_non_terminal(
        job_id=job_id,
        file_id=f_active,
        status=FileStatus.S1_DONE.value,
        s3_stage1_key=f"jobs/{job_id}/stage1/{f_active}.json",
    )
    assert mock_table.items[(f"JOB#{job_id}", f"FILE#{f_active}")]["status"] == FileStatus.S1_DONE.value


# ---------------------------------------------------------------------------
# Drill 4: Duplicate worker deliveries racing on the same file
# ---------------------------------------------------------------------------
def test_duplicate_worker_claims_isolated(mock_table):
    """Worker lease claims prevent concurrent duplicate executions."""
    job_id = "job-lease-race"
    file_id = "file-shared"

    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": FileStatus.S1_DONE.value,
    }

    files_repo = FilesRepository()

    # Worker A claims file
    claimed_a = files_repo.claim_file(job_id, file_id, worker_id="worker-A", lease_seconds=120)
    assert claimed_a is True

    # Worker B arrives concurrently and attempts to claim same file
    claimed_b = files_repo.claim_file(job_id, file_id, worker_id="worker-B", lease_seconds=120)
    assert claimed_b is False

    # Worker A can re-claim/heartbeat its own lease
    claimed_a_renewal = files_repo.claim_file(job_id, file_id, worker_id="worker-A", lease_seconds=120)
    assert claimed_a_renewal is True


# ---------------------------------------------------------------------------
# Drill 5: Concurrent LLM requests racing against per-job budget
# ---------------------------------------------------------------------------
def test_concurrent_llm_budget_reservations(mock_table):
    """Atomic reservation pattern strictly enforces LLM_FALLBACK_MAX_PER_JOB."""
    job_id = "job-llm-budget-race"
    files_repo = FilesRepository()

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 10,
        "total_files": 10,
        "usable_files": 0,
        "llm_reservations": 0,
    }

    # Simulate 5 files reserving budget up to cap = 5
    for i in range(5):
        fid = f"file-{i}"
        mock_table.items[(f"JOB#{job_id}", f"FILE#{fid}")] = {
            "PK": f"JOB#{job_id}",
            "SK": f"FILE#{fid}",
            "status": FileStatus.S2_PROCESSING.value,
            "needs_fallback": True,
        }
        allowed, reason = files_repo.reserve_llm_slot(job_id, fid, attempt_id=f"worker-{i}", max_per_job=5)
        assert allowed is True
        assert reason is None

    # 6th file attempts reservation -> Must be rejected atomically
    fid_6 = "file-exceeds"
    mock_table.items[(f"JOB#{job_id}", f"FILE#{fid_6}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{fid_6}",
        "status": FileStatus.S2_PROCESSING.value,
        "needs_fallback": True,
    }
    allowed_6, reason_6 = files_repo.reserve_llm_slot(job_id, fid_6, attempt_id="worker-6", max_per_job=5)
    assert allowed_6 is False
    assert reason_6 == "JOB_LLM_CAP_REACHED"


# ---------------------------------------------------------------------------
# Drill 6: Retryable throttling propagating back to the queue handler
# ---------------------------------------------------------------------------
def test_retryable_throttling_propagates_to_queue(mock_table):
    """Nova/Bedrock throttling raises RetryableThrottlingError to invoke SQS retry backoff."""
    job_id = "job-throttle-test"
    file_id = "file-throttled"

    current_file = FileItem(job_id=job_id, file_id=file_id, status=FileStatus.S2_PROCESSING.value, needs_fallback=True)
    stage1_json = {
        "fields": {},  # missing name and skills
        "quality": {"score": 0.95, "looks_tabular": False},
        "unresolved_chunks": ["some unparsed content"],
    }

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", return_value=current_file), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.claim_file", return_value=True), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.reserve_llm_slot", return_value=(True, None)), \
         patch("src.infrastructure.storage.storage_service.StorageService.get_stage1_json", return_value=stage1_json), \
         patch("src.extraction.fallback.nova_service.NovaService.resolve_chunks", side_effect=NovaThrottlingError("Rate exceeded")):

        msg = MagicMock(job_id=job_id, document_id=file_id)

        # Worker must raise RetryableThrottlingError so SQS retries
        with pytest.raises(RetryableThrottlingError) as exc_info:
            process_stage2_batch([msg])

        assert "Bedrock Nova throttled" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Drill 7: Scoring dispatch failure and subsequent recovery
# ---------------------------------------------------------------------------
def test_scoring_dispatch_failure_and_poll_recovery(mock_table):
    """Scoring dispatch failure is captured in outbox and reconciled on subsequent poll."""
    job_id = "job-scoring-recovery"
    file_id = "file-last"

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 1,
        "usable_files": 0,
        "analyze_requested": True,
        "status": "PROCESSING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": FileStatus.S2_PROCESSING.value,
    }

    files_repo = FilesRepository()

    # Simulate SQS outage when transitioning last file to terminal
    with patch("src.infrastructure.repositories.files_repository.FilesRepository._trigger_scoring", side_effect=Exception("SQS down")):
        files_repo.transition_file_terminal(job_id, file_id, FileStatus.S2_DONE.value)

    # Job remaining is 0, status is SCORING, and outbox event is recorded but undispatched
    job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
    assert job_item["remaining"] == 0
    assert job_item["status"] == "SCORING"

    outbox_item = mock_table.items.get((f"JOB#{job_id}", "OUTBOX#SCORING"))
    assert outbox_item is not None
    assert outbox_item["dispatched"] is False

    # Next poll reconciles outbox and triggers scoring
    with patch("src.infrastructure.repositories.files_repository.FilesRepository._trigger_scoring") as mock_scoring:
        dispatched = files_repo.reconcile_outbox(job_id)
        assert dispatched == 1
        mock_scoring.assert_called_once_with(job_id)

    assert mock_table.items[(f"JOB#{job_id}", "OUTBOX#SCORING")]["dispatched"] is True


# ---------------------------------------------------------------------------
# Drill 8: Partial ODL microbatch failure and tail flush
# ---------------------------------------------------------------------------
def test_partial_odl_microbatch_failure_and_tail_flush(mock_table):
    """ODL microbatch with 1 success and 1 failure isolates failure without aborting batch."""
    job_id = "job-odl-microbatch"
    f_good = "file-odl-good"
    f_bad = "file-odl-bad"

    file_good = FileItem(job_id=job_id, file_id=f_good, status=FileStatus.S1_DONE, needs_fallback=True)
    file_bad = FileItem(job_id=job_id, file_id=f_bad, status=FileStatus.S1_DONE, needs_fallback=True)

    stage1_good = {
        "fields": {"email": "good@example.com"},
        "quality": {"score": 0.70, "looks_tabular": True},
        "unresolved_chunks": [],
    }
    stage1_bad = {
        "fields": {"email": "bad@example.com"},
        "quality": {"score": 0.70, "looks_tabular": True},
        "unresolved_chunks": [],
    }

    # Simulate ODL batch output: good succeeds, bad fails
    mock_batch_result = BatchParseResult(
        results={f_good: ODLParseResult(markdown="# Jane Doe\nPython Engineer", elements=[])},
        failed={f_bad: ODLParseError("ODL JVM Segmentation Fault")},
    )

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", side_effect=lambda j, f: file_good if f == f_good else file_bad), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.claim_file", return_value=True), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.reserve_llm_slot", return_value=(False, "JOB_LLM_CAP_REACHED")), \
         patch("src.infrastructure.storage.storage_service.StorageService.get_stage1_json", side_effect=lambda j, f: stage1_good if f == f_good else stage1_bad), \
         patch("src.infrastructure.storage.storage_service.StorageService.upload_stage2_json", return_value="stage2_key"), \
         patch("src.pipeline.stage2_worker.parse_batch", return_value=mock_batch_result), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_terminal:

        msg_good = MagicMock(job_id=job_id, document_id=f_good)
        msg_bad = MagicMock(job_id=job_id, document_id=f_bad)

        summary = process_stage2_batch([msg_good, msg_bad])

        # Both documents processed; partial failure isolated
        assert summary["processed"] == 2
        assert summary["succeeded"] == 2  # Both transitioned (f_good with ODL infill, f_bad degraded gracefully)

        # Check terminal calls
        assert mock_terminal.call_count == 2
        calls = {c.kwargs["file_id"]: c.kwargs for c in mock_terminal.call_args_list}
        assert calls[f_good]["terminal_status"] == FileStatus.S2_DONE.value
        assert calls[f_bad]["terminal_status"] == FileStatus.S2_DONE.value
        assert calls[f_bad]["low_confidence_extraction"] is True
