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
