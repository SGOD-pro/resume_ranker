"""
jobs_repository.py — Job entity CRUD on DynamoDB Single Table
===============================================================
All operations target PK=JOB#{job_id}, SK=METADATA in the ResumePlatform table.
Uses optimistic locking via version + ConditionExpression.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.repositories.base import _get_table, to_decimal

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobsRepository:
    """CRUD operations for Job entities in the ResumePlatform table."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create(self, job: JobItem) -> JobItem:
        """Insert a new Job item.

        Uses ConditionExpression to prevent overwrites.
        """
        item = job.to_dynamodb_item()
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK)",
        )
        logger.info("Created job: %s", job.job_id)
        return job

    def get(self, job_id: str) -> Optional[JobItem]:
        """Get a Job by ID. Returns None if not found."""
        # Use to_decimal when querying if needed (not needed for simple string keys)
        response = self._table.get_item(
            Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
        )
        item = response.get("Item")
        if not item:
            return None
        return JobItem.from_dynamodb_item(item)

    def update(
        self,
        job_id: str,
        updates: Dict[str, Any],
        expected_version: int,
    ) -> JobItem:
        """Update Job attributes with optimistic locking.

        Args:
            job_id: Job UUID.
            updates: Dict of field names → new values.
            expected_version: Current version for optimistic lock.

        Returns:
            Updated JobItem.

        Raises:
            botocore.exceptions.ClientError: If version mismatch (ConditionalCheckFailedException).
        """
        # Build SET expression dynamically from updates dict
        set_parts = ["#v = #v + :one", "updated_at = :now"]
        expr_names: Dict[str, str] = {"#v": "version"}
        expr_values: Dict[str, Any] = {
            ":one": 1,
            ":now": _utcnow_iso(),
            ":expected_version": expected_version,
        }

        for i, (field, value) in enumerate(updates.items()):
            placeholder = f":val{i}"
            name_placeholder = f"#f{i}"
            set_parts.append(f"{name_placeholder} = {placeholder}")
            expr_names[name_placeholder] = field
            expr_values[placeholder] = to_decimal(value)

        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
            UpdateExpression="SET " + ", ".join(set_parts),
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW",
        )
        logger.info("Updated job: %s (v%d → v%d)", job_id, expected_version, expected_version + 1)
        return JobItem.from_dynamodb_item(response["Attributes"])

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        expected_version: int,
    ) -> JobItem:
        """Update only the status field with optimistic locking."""
        return self.update(job_id, {"status": status.value}, expected_version)

    def increment_document_count(
        self,
        job_id: str,
        expected_version: int,
    ) -> JobItem:
        """Atomically increment document_count by 1."""
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
            UpdateExpression="SET #v = #v + :one, updated_at = :now, document_count = document_count + :one",
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#v": "version"},
            ExpressionAttributeValues={
                ":one": 1,
                ":now": _utcnow_iso(),
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        logger.info("Incremented doc count for job: %s", job_id)
        return JobItem.from_dynamodb_item(response["Attributes"])

    def delete(self, job_id: str) -> None:
        """Delete a Job and ALL its related items (documents, scoring results).

        Queries all items with PK=JOB#{job_id} and batch-deletes them.
        """
        # Query all items for this job (metadata + docs + scoring results)
        response = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}"),
        )
        items = response.get("Items", [])

        if not items:
            logger.warning("Delete: job %s not found", job_id)
            return

        # Batch delete all items (max 25 per batch)
        with self._table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

        logger.info("Deleted job %s and %d related items", job_id, len(items))

    def get_job_with_files(self, job_id: str) -> tuple[Optional[JobItem], List[Any]]:
        """Fetch Job METADATA and all FILE# items in a single DynamoDB query."""
        from src.infrastructure.models.file import FileItem
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}")
        )
        items = resp.get("Items", [])
        job: Optional[JobItem] = None
        files: List[FileItem] = []

        for item in items:
            sk = item.get("SK", "")
            if sk == "METADATA":
                job = JobItem.from_dynamodb_item(item)
            elif sk.startswith("FILE#"):
                files.append(FileItem.from_dynamodb_item(item))

        return job, files

    def request_analysis(self, job_id: str, file_ids: List[str]) -> JobItem:
        """Process recruiter's Analyze request (Amendment 2).
        
        - Marks unselected files REMOVED (conditionally decrements remaining)
        - Enqueues S1_DONE files that need fallback to Stage 2
        - Sets analyze_requested = True
        - Triggers scoring if remaining == 0
        """
        from src.infrastructure.models.file import FileStatus
        from src.infrastructure.repositories.files_repository import FilesRepository
        from src.infrastructure.queue.queue_manager import (
            ODL_BATCH_QUEUE,
            FINAL_RANK_QUEUE,
            get_queue_adapter,
        )
        from src.infrastructure.queue.message import QueueMessage

        files_repo = FilesRepository()
        all_files = files_repo.list_files_for_job(job_id)
        selected_set = set(file_ids)

        # 1. Mark unselected files as REMOVED (this conditionally decrements remaining if not already terminal)
        for f in all_files:
            if f.file_id not in selected_set:
                files_repo.transition_file_terminal(
                    job_id=job_id,
                    file_id=f.file_id,
                    terminal_status=FileStatus.REMOVED.value,
                    error_message="Excluded from analysis",
                )

        # 2. For selected files currently waiting in S1_DONE, enqueue them to Stage 2 fallback
        adapter = get_queue_adapter()
        for f in all_files:
            if f.file_id in selected_set and f.status == FileStatus.S1_DONE:
                msg = QueueMessage(
                    job_id=job_id,
                    session_id=job_id,
                    document_id=f.file_id,
                    org_id="org_default",
                    job_version=1,
                    s3_key=f.s3_raw_key,
                    stage="ODL_BATCH",
                )
                adapter.send_message(ODL_BATCH_QUEUE, msg)
                logger.info("Enqueued file %s/%s to Stage 2 fallback queue", job_id, f.file_id)

        # 3. Update job metadata
        now = _utcnow_iso()
        job_resp = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
            UpdateExpression="SET #ar = :true, #afids = :afids, #upd = :now",
            ExpressionAttributeNames={
                "#ar": "analyze_requested",
                "#afids": "analyze_file_ids",
                "#upd": "updated_at",
            },
            ExpressionAttributeValues={
                ":true": True,
                ":afids": file_ids,
                ":now": now,
            },
            ReturnValues="ALL_NEW",
        )
        updated_job = JobItem.from_dynamodb_item(job_resp["Attributes"])

        # 4. Check if remaining reached 0
        if updated_job.remaining == 0:
            if updated_job.usable_files == 0:
                logger.warning("Job %s analyze requested but 0 usable files -> DONE_WITH_ERRORS", job_id)
                self._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                    UpdateExpression="SET #st = :done_err, #upd = :now",
                    ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                    ExpressionAttributeValues={
                        ":done_err": JobStatus.DONE_WITH_ERRORS.value,
                        ":now": now,
                    },
                )
                updated_job.status = JobStatus.DONE_WITH_ERRORS
            else:
                logger.info("Job %s analyze requested and remaining == 0 -> SCORING", job_id)
                self._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                    UpdateExpression="SET #st = :scoring, #upd = :now",
                    ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                    ExpressionAttributeValues={
                        ":scoring": JobStatus.SCORING.value,
                        ":now": now,
                    },
                )
                updated_job.status = JobStatus.SCORING
                # Enqueue scoring event
                score_msg = QueueMessage(
                    job_id=job_id,
                    session_id=job_id,
                    document_id=job_id,
                    org_id="org_default",
                    job_version=updated_job.job_version,
                    stage="FINAL_RANK",
                )
                adapter.send_message(FINAL_RANK_QUEUE, score_msg)
        else:
            # Active processing
            if updated_job.status not in (JobStatus.DONE, JobStatus.DONE_WITH_ERRORS, JobStatus.FAILED):
                self._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": "METADATA"},
                    UpdateExpression="SET #st = :proc, #upd = :now",
                    ExpressionAttributeNames={"#st": "status", "#upd": "updated_at"},
                    ExpressionAttributeValues={
                        ":proc": JobStatus.PROCESSING.value,
                        ":now": now,
                    },
                )
                updated_job.status = JobStatus.PROCESSING

        return updated_job
