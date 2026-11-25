"""
test_terminal_state_accounting.py — Unit tests for Amendment 2 terminal-state accounting
========================================================================================
Verifies:
1. S1_FAILED, S2_DONE, S2_FAILED, REMOVED are terminal states.
2. Each terminal transition decrements job.remaining exactly once via conditional check.
3. Repeated transitions are idempotent (conditional failure, remaining NOT decremented).
4. Zero usable files condition routes job to DONE_WITH_ERRORS without scoring.
5. remaining == 0 AND analyze_requested triggers scoring.
6. Job stalling detection: is_stalled() returns True after 600 seconds, False otherwise.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.infrastructure.models.file import (
    FileItem,
    FileStatus,
    TERMINAL_FILE_STATUSES,
)
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository


class InMemoryDynamoTable:
    """In-memory mock for single-table DynamoDB operations."""

    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        k = (Key["PK"], Key["SK"])
        if k in self.items:
            return {"Item": dict(self.items[k])}
        return {}

    def put_item(self, Item, ConditionExpression=None):
        k = (Item["PK"], Item["SK"])
        if ConditionExpression == "attribute_not_exists(PK)" and k in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[k] = dict(Item)
        return {}

    def query(self, KeyConditionExpression=None):
        results = []
        # KeyConditionExpression evaluation
        for (pk, sk), item in self.items.items():
            results.append(dict(item))
        return {"Items": results}

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
                current_st = item.get("status")
                if current_st in ("S1_FAILED", "S2_DONE", "S2_FAILED", "REMOVED"):
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")
            if "#rem > :zero" in ConditionExpression:
                rem = item.get("remaining", 0)
                if rem <= 0:
                    raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")

        # Apply basic updates
        if ExpressionAttributeNames and ExpressionAttributeValues:
            for alias, val in ExpressionAttributeValues.items():
                if alias == ":status" or alias == ":new_st":
                    item["status"] = val
                elif alias == ":one":
                    if "#rem = #rem - :one" in UpdateExpression:
                        item["remaining"] = item.get("remaining", 0) - 1
                elif alias == ":usable_inc":
                    item["usable_files"] = item.get("usable_files", 0) + val
                elif alias == ":now":
                    item["updated_at"] = val
                elif alias == ":true":
                    item["analyze_requested"] = True
                elif alias == ":t_st":
                    item["status"] = val
                elif alias == ":scoring":
                    item["status"] = "SCORING"
                elif alias == ":done_err":
                    item["status"] = "DONE_WITH_ERRORS"

        self.items[k] = item
        return {"Attributes": dict(item)}


@pytest.fixture
def mock_table():
    tbl = InMemoryDynamoTable()
    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=tbl), \
         patch("src.infrastructure.repositories.jobs_repository._get_table", return_value=tbl):
        yield tbl


def test_terminal_states_defined():
    """Verify exactly the 4 required terminal states are defined."""
    expected = {"S1_FAILED", "S2_DONE", "S2_FAILED", "REMOVED"}
    assert TERMINAL_FILE_STATUSES == expected


def test_single_file_terminal_transition_decrements_remaining(mock_table):
    """File transition to S2_DONE decrements remaining by 1 and increments usable_files."""
    job_id = "test-job-01"
    file_id = "file-01"

    # Setup job with 2 files
    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "job_id": job_id,
        "remaining": 2,
        "total_files": 2,
        "usable_files": 0,
        "analyze_requested": False,
        "status": "UPLOADING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": "S1_PROCESSING",
    }

    files_repo = FilesRepository()
    success = files_repo.transition_file_terminal(job_id, file_id, "S2_DONE")
    assert success is True

    # Check updated job
    job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
    assert job_item["remaining"] == 1
    assert job_item["usable_files"] == 1

    # Check file item
    file_item = mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")]
    assert file_item["status"] == "S2_DONE"


def test_idempotent_duplicate_terminal_transition(mock_table):
    """Calling terminal transition twice on the same file does NOT decrement remaining again."""
    job_id = "test-job-02"
    file_id = "file-dup"

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 1,
        "total_files": 1,
        "usable_files": 0,
        "analyze_requested": False,
        "status": "UPLOADING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": "S1_DONE",
    }

    files_repo = FilesRepository()

    # First transition -> Success
    res1 = files_repo.transition_file_terminal(job_id, file_id, "S2_DONE")
    assert res1 is True
    assert mock_table.items[(f"JOB#{job_id}", "METADATA")]["remaining"] == 0

    # Second transition with duplicate event -> Skipped
    res2 = files_repo.transition_file_terminal(job_id, file_id, "S2_DONE")
    assert res2 is False
    # remaining MUST NOT become negative or decrement again
    assert mock_table.items[(f"JOB#{job_id}", "METADATA")]["remaining"] == 0


def test_zero_usable_files_routes_to_done_with_errors(mock_table):
    """If all files fail (0 usable files), job goes to DONE_WITH_ERRORS without scoring."""
    job_id = "test-job-fail"
    file_id = "file-bad"

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 1,
        "total_files": 1,
        "usable_files": 0,
        "analyze_requested": True,
        "status": "PROCESSING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": "S1_PROCESSING",
    }

    files_repo = FilesRepository()
    files_repo.transition_file_terminal(job_id, file_id, "S1_FAILED", error_message="Corrupt PDF")

    job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
    assert job_item["remaining"] == 0
    assert job_item["usable_files"] == 0
    assert job_item["status"] == "DONE_WITH_ERRORS"


def test_remaining_zero_with_analyze_requested_triggers_scoring(mock_table):
    """When remaining hits 0 and analyze_requested == True, status becomes SCORING."""
    job_id = "test-job-score"
    file_id = "file-good"

    mock_table.items[(f"JOB#{job_id}", "METADATA")] = {
        "PK": f"JOB#{job_id}",
        "SK": "METADATA",
        "remaining": 1,
        "total_files": 1,
        "usable_files": 0,
        "analyze_requested": True,
        "status": "PROCESSING",
    }
    mock_table.items[(f"JOB#{job_id}", f"FILE#{file_id}")] = {
        "PK": f"JOB#{job_id}",
        "SK": f"FILE#{file_id}",
        "status": "S2_PROCESSING",
    }

    with patch("src.infrastructure.repositories.files_repository.FilesRepository._trigger_scoring") as mock_trig:
        files_repo = FilesRepository()
        files_repo.transition_file_terminal(job_id, file_id, "S2_DONE")

        job_item = mock_table.items[(f"JOB#{job_id}", "METADATA")]
        assert job_item["remaining"] == 0
        assert job_item["usable_files"] == 1
        assert job_item["status"] == "SCORING"
        mock_trig.assert_called_once_with(job_id)


def test_job_stalling_detection():
    """Verify is_stalled() flags jobs after 10 minutes without progress."""
    now = datetime.now(timezone.utc)
    old_time = datetime.fromtimestamp(now.timestamp() - 650, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent_time = datetime.fromtimestamp(now.timestamp() - 100, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stalled_job = JobItem(
        job_id="stalled-01",
        status=JobStatus.PROCESSING,
        updated_at=old_time,
    )
    assert stalled_job.is_stalled(threshold_seconds=600) is True

    active_job = JobItem(
        job_id="active-01",
        status=JobStatus.PROCESSING,
        updated_at=recent_time,
    )
    assert active_job.is_stalled(threshold_seconds=600) is False

    # Terminal jobs are never stalled
    completed_job = JobItem(
        job_id="done-01",
        status=JobStatus.DONE,
        updated_at=old_time,
    )
    assert completed_job.is_stalled(threshold_seconds=600) is False
