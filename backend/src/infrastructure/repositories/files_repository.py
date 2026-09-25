"""
files_repository.py — File/Document entity operations on DynamoDB Single Table
================================================================================
Targets PK=JOB#{job_id}, SK=FILE#{file_id}.
Implements Amendment 2:
- Idempotent conditional transitions to terminal states (S1_FAILED, S2_DONE, S2_FAILED, REMOVED)
- Exactly-once conditional decrement of job.remaining
- Scoring trigger when remaining == 0 AND analyze_requested
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.infrastructure.models.file import (
    FileItem,
    FileStatus,
    TERMINAL_FILE_STATUSES,
)
from src.infrastructure.models.job import JobStatus
from src.infrastructure.queue.queue_manager import (
    FINAL_RANK_QUEUE,
    get_queue_adapter,
)
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.repositories.base import _get_table

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FilesRepository:
    """CRUD and atomic state transition operations for File entities."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create_files(self, job_id: str, files: List[FileItem]) -> List[FileItem]:
        """Batch write new file items with PENDING_UPLOAD status."""
        if not files:
            return []

        # DynamoDB batch_writer handles batches up to 25 items automatically
        with self._table.batch_writer() as batch:
            for f in files:
                item = f.to_dynamodb_item()
                batch.put_item(Item=item)

        logger.info("Created %d file records for job %s", len(files), job_id)
        return files

    def get_file(self, job_id: str, file_id: str) -> Optional[FileItem]:
        """Fetch a single file item by job_id and file_id."""
        resp = self._table.get_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"FILE#{file_id}"}
        )
        item = resp.get("Item")
        if not item:
            return None
        return FileItem.from_dynamodb_item(item)

    def list_files_for_job(self, job_id: str) -> List[FileItem]:
        """Query all FILE# items for a given job."""
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("FILE#")
        )
        items = resp.get("Items", [])
        return [FileItem.from_dynamodb_item(item) for item in items]

    def update_file_non_terminal(
        self,
        job_id: str,
        file_id: str,
        status: FileStatus,
        s3_stage1_key: Optional[str] = None,
        s3_extracted_key: Optional[str] = None,
        needs_fallback: Optional[bool] = None,
        candidate_name: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update a file's non-terminal progress (e.g. S1_PROCESSING, S1_DONE, S2_PROCESSING).
        
        Guarded: will NOT overwrite if the file is already in a terminal state.
        """
        now = _utcnow_iso()
        set_parts = ["#st = :status", "#upd = :now"]
        expr_names = {"#st": "status", "#upd": "updated_at"}
        expr_values: Dict[str, Any] = {
            ":status": status.value,
            ":now": now,
            ":s1_f": FileStatus.S1_FAILED.value,
            ":s2_d": FileStatus.S2_DONE.value,
            ":s2_f": FileStatus.S2_FAILED.value,
            ":rem": FileStatus.REMOVED.value,
        }

        if s3_stage1_key is not None:
            set_parts.append("#s1k = :s1k")
            expr_names["#s1k"] = "s3_stage1_key"
            expr_values[":s1k"] = s3_stage1_key

        if s3_extracted_key is not None:
            set_parts.append("#s2k = :s2k")
            expr_names["#s2k"] = "s3_extracted_key"
            expr_values[":s2k"] = s3_extracted_key

        if needs_fallback is not None:
            set_parts.append("#nfb = :nfb")
            expr_names["#nfb"] = "needs_fallback"
            expr_values[":nfb"] = needs_fallback

        if candidate_name is not None:
            set_parts.append("#cn = :cn")
            expr_names["#cn"] = "candidate_name"
            expr_values[":cn"] = candidate_name

        if error_message is not None:
            set_parts.append("#err = :err")
            expr_names["#err"] = "error_message"
            expr_values[":err"] = error_message

        update_expr = "SET " + ", ".join(set_parts)
        condition_expr = "attribute_not_exists(#st) OR NOT (#st IN (:s1_f, :s2_d, :s2_f, :rem))"

        try:
            self._table.update_item(
                Key={"PK": f"JOB#{job_id}", "SK": f"FILE#{file_id}"},
                UpdateExpression=update_expr,
                ConditionExpression=condition_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Skipping non-terminal update for %s/%s: already in terminal state",
                    job_id, file_id
                )
                return False
            raise

    def transition_file_terminal(
        self,
        job_id: str,
        file_id: str,
        terminal_status: str,
        error_message: Optional[str] = None,
        candidate_name: Optional[str] = None,
        s3_extracted_key: Optional[str] = None,
        low_confidence_extraction: bool = False,
        fallback_reason: Optional[str] = None,
    ) -> bool:
        """Idempotently transition file to a terminal state (S1_FAILED, S2_DONE, S2_FAILED, REMOVED).
        
        Decrements job.remaining exactly once via conditional check.
        Returns True if transition occurred; False if already terminal.
        """
        if terminal_status not in TERMINAL_FILE_STATUSES:
            raise ValueError(f"Invalid terminal status: {terminal_status}. Must be one of {TERMINAL_FILE_STATUSES}")

        now = _utcnow_iso()

        # Step 1: Conditionally update file status only if not already terminal
        set_parts = ["#st = :status", "#upd = :now"]
        expr_names = {"#st": "status", "#upd": "updated_at"}
        expr_values: Dict[str, Any] = {
            ":status": terminal_status,
            ":now": now,
            ":s1_f": FileStatus.S1_FAILED.value,
            ":s2_d": FileStatus.S2_DONE.value,
            ":s2_f": FileStatus.S2_FAILED.value,
            ":rem": FileStatus.REMOVED.value,
        }

        if low_confidence_extraction:
            set_parts.append("#lce = :lce")
            expr_names["#lce"] = "low_confidence_extraction"
            expr_values[":lce"] = True

        if fallback_reason:
            set_parts.append("#fbr = :fbr")
            expr_names["#fbr"] = "fallback_reason"
            expr_values[":fbr"] = fallback_reason

        if error_message:
            set_parts.append("#err = :err")
            expr_names["#err"] = "error_message"
            expr_values[":err"] = error_message

        if candidate_name:
            set_parts.append("#cn = :cn")
            expr_names["#cn"] = "candidate_name"
            expr_values[":cn"] = candidate_name

        if s3_extracted_key:
            set_parts.append("#s2k = :s2k")
            expr_names["#s2k"] = "s3_extracted_key"
            expr_values[":s2k"] = s3_extracted_key

        update_expr = "SET " + ", ".join(set_parts)
        condition_expr = "attribute_not_exists(#st) OR NOT (#st IN (:s1_f, :s2_d, :s2_f, :rem))"

        try:
            self._table.update_item(
                Key={"PK": f"JOB#{job_id}", "SK": f"FILE#{file_id}"},
                UpdateExpression=update_expr,
                ConditionExpression=condition_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Idempotent skip: file %s/%s already in terminal state", job_id, file_id
                )
                return False
            raise

        # Step 2: Since Step 1 succeeded, decrement job.remaining exactly once
        is_usable = 1 if terminal_status == FileStatus.S2_DONE.value else 0
        try:
            job_resp = self._table.update_item(
                Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                UpdateExpression="SET #rem = #rem - :one, #upd = :now, #usable = #usable + :usable_inc",
                ConditionExpression="attribute_exists(PK) AND #rem > :zero",
                ExpressionAttributeNames={
                    "#rem": "remaining",
                    "#upd": "updated_at",
                    "#usable": "usable_files",
                },
                ExpressionAttributeValues={
                    ":one": 1,
                    ":usable_inc": is_usable,
                    ":now": now,
                    ":zero": 0,
                },
                ReturnValues="ALL_NEW",
            )
            updated_job = job_resp.get("Attributes", {})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning("Job %s remaining is already 0, cannot decrement", job_id)
                # Fetch fresh job attributes
                fetch_resp = self._table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "METADATA"})
                updated_job = fetch_resp.get("Item", {})
            else:
                raise

        new_remaining = int(updated_job.get("remaining", 0))
        usable_count = int(updated_job.get("usable_files", 0))
        analyze_requested = bool(updated_job.get("analyze_requested", False))

        logger.info(
            "File %s/%s -> %s (job remaining: %d, usable: %d, analyze_requested: %s)",
            job_id, file_id, terminal_status, new_remaining, usable_count, analyze_requested,
        )

        # Step 3: Check barrier terminal condition
        if new_remaining == 0:
            self._handle_zero_remaining(job_id, usable_count, analyze_requested, now)

        return True

    def _handle_zero_remaining(
        self,
        job_id: str,
        usable_count: int,
        analyze_requested: bool,
        now_iso: str,
    ) -> None:
        """Handle barrier completion when remaining hits 0."""
        if analyze_requested:
            if usable_count == 0:
                logger.warning("Job %s has 0 usable files remaining -> DONE_WITH_ERRORS", job_id)
                self._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                    UpdateExpression="SET #st = :done_err, #upd = :now",
                    ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                    ExpressionAttributeValues={
                        ":done_err": JobStatus.DONE_WITH_ERRORS.value,
                        ":now": now_iso,
                    },
                )
            else:
                logger.info("Job %s remaining == 0 and analyze_requested == True -> trigger SCORING", job_id)
                self._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                    UpdateExpression="SET #st = :scoring, #upd = :now",
                    ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                    ExpressionAttributeValues={
                        ":scoring": JobStatus.SCORING.value,
                        ":now": now_iso,
                    },
                )
                self._trigger_scoring(job_id)
        else:
            target_status = JobStatus.DONE_WITH_ERRORS.value if usable_count == 0 else JobStatus.READY_TO_ANALYZE.value
            logger.info("Job %s remaining == 0 but analyze not requested -> status = %s", job_id, target_status)
            self._table.update_item(
                Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                UpdateExpression="SET #st = :t_st, #upd = :now",
                ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                ExpressionAttributeValues={
                    ":t_st": target_status,
                    ":now": now_iso,
                },
            )

    def _trigger_scoring(self, job_id: str) -> None:
        """Enqueue scoring event to scoring queue."""
        adapter = get_queue_adapter()
        msg = QueueMessage(
            job_id=job_id,
            session_id=job_id,
            document_id=job_id,
            org_id="org_default",
            job_version=1,
            stage="FINAL_RANK",
        )
        adapter.send_message(FINAL_RANK_QUEUE, msg)
        logger.info("Enqueued scoring message for job %s", job_id)

    def check_and_increment_daily_llm_cap(self, limit: int = 100) -> bool:
        """Atomically check and increment global daily LLM count.
        
        Returns True if within limit; False if daily cap exceeded.
        Uses DynamoDB conditional update on PK=GLOBAL#METRICS, SK=DAILY_LLM#{YYYY-MM-DD}.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = _utcnow_iso()
        try:
            self._table.update_item(
                Key={"PK": "GLOBAL#METRICS", "SK": f"DAILY_LLM#{today}"},
                UpdateExpression="ADD #cnt :inc SET #upd = :now",
                ConditionExpression="attribute_not_exists(#cnt) OR #cnt < :limit",
                ExpressionAttributeNames={"#cnt": "llm_count", "#upd": "updated_at"},
                ExpressionAttributeValues={":inc": 1, ":limit": limit, ":now": now_iso},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning("Global daily LLM cap reached (%d/day for %s)", limit, today)
                return False
            raise
