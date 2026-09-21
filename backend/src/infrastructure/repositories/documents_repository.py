"""
documents_repository.py — Document entity CRUD on DynamoDB Single Table
=========================================================================
All operations target PK=JOB#{job_id}, SK=DOC#{document_id} in ResumePlatform.
Uses optimistic locking via version + ConditionExpression.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key, Attr

from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.repositories.base import _get_table

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DocumentsRepository:
    """CRUD operations for Document entities in the ResumePlatform table."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create(self, doc: DocumentItem) -> DocumentItem:
        """Insert a new Document item.

        Uses ConditionExpression to prevent overwrites.
        """
        item = doc.to_dynamodb_item()
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        logger.info("Created document: %s for job: %s", doc.document_id, doc.job_id)
        return doc

    def get(self, job_id: str, document_id: str) -> Optional[DocumentItem]:
        """Get a Document by job_id + document_id. Returns None if not found."""
        response = self._table.get_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
        )
        item = response.get("Item")
        if not item:
            return None
        return DocumentItem.from_dynamodb_item(item)

    def list_for_job(self, job_id: str) -> List[DocumentItem]:
        """List all Documents for a job.

        Uses Query with SK begins_with "DOC#" to get only document entities.
        """
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("DOC#")
            ),
        )
        items = response.get("Items", [])
        return [DocumentItem.from_dynamodb_item(item) for item in items]

    def update_status(
        self,
        job_id: str,
        document_id: str,
        status: DocumentStatus,
        expected_version: int,
    ) -> DocumentItem:
        """Update only the status field with optimistic locking."""
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
            UpdateExpression="SET #s = :status, #v = #v + :one, updated_at = :now",
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#s": "status", "#v": "version"},
            ExpressionAttributeValues={
                ":status": status.value,
                ":one": 1,
                ":now": _utcnow_iso(),
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        logger.info("Updated doc %s status → %s", document_id, status.value)
        return DocumentItem.from_dynamodb_item(response["Attributes"])

    def update_extraction(
        self,
        job_id: str,
        document_id: str,
        s3_extracted_key: str,
        extraction_quality: float,
        candidate_name: str,
        page_count: int,
        expected_version: int,
    ) -> DocumentItem:
        """Update extraction metadata after successful extraction.

        Sets status to EXTRACTED, stores S3 key, quality score, and candidate name.
        """
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
            UpdateExpression=(
                "SET #s = :status, s3_extracted_key = :s3key, "
                "extraction_quality = :quality, candidate_name = :cname, "
                "page_count = :pages, #v = #v + :one, updated_at = :now"
            ),
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#s": "status", "#v": "version"},
            ExpressionAttributeValues={
                ":status": DocumentStatus.PARSED.value,
                ":s3key": s3_extracted_key,
                ":quality": str(extraction_quality),
                ":cname": candidate_name,
                ":pages": page_count,
                ":one": 1,
                ":now": _utcnow_iso(),
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        logger.info(
            "Updated extraction for doc %s: quality=%.2f, name=%s",
            document_id, extraction_quality, candidate_name,
        )
        return DocumentItem.from_dynamodb_item(response["Attributes"])

    def find_by_hash(self, job_id: str, content_hash: str) -> Optional[DocumentItem]:
        """Find a document by SHA-256 content hash within a job.

        Used for deduplication — prevents uploading the same PDF twice.
        Queries DOC# items for the specific job and filters by content_hash.
        (This uses a targeted query on the Partition Key, NOT a full table scan, complying with R-04)
        """
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("DOC#")
            ),
            FilterExpression=Attr("content_hash").eq(content_hash),
        )
        items = response.get("Items", [])
        if items:
            return DocumentItem.from_dynamodb_item(items[0])
        return None

    def list_for_session(self, job_id: str, session_id: str) -> List[DocumentItem]:
        """List all documents belonging to an upload session."""
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("DOC#")
            ),
            FilterExpression=Attr("session_id").eq(session_id),
        )
        items = response.get("Items", [])
        return [DocumentItem.from_dynamodb_item(item) for item in items]

    def update_status_conditional(
        self,
        job_id: str,
        document_id: str,
        new_status: DocumentStatus,
        allowed_current_statuses: Optional[List[DocumentStatus]] = None,
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[DocumentItem]:
        """Update document status conditionally for idempotent state machine transitions.

        If current status is not in allowed_current_statuses, returns None without raising,
        preventing duplicate SQS message processing.
        """
        import botocore.exceptions
        from src.infrastructure.repositories.base import to_decimal

        set_parts = ["#s = :status", "#v = #v + :one", "updated_at = :now"]
        expr_names: Dict[str, str] = {"#s": "status", "#v": "version"}
        expr_values: Dict[str, Any] = {
            ":status": new_status.value,
            ":one": 1,
            ":now": _utcnow_iso(),
        }

        if extra_updates:
            for i, (k, v) in enumerate(extra_updates.items()):
                placeholder = f":val{i}"
                name_placeholder = f"#f{i}"
                set_parts.append(f"{name_placeholder} = {placeholder}")
                expr_names[name_placeholder] = k
                expr_values[placeholder] = to_decimal(v)

        cond_parts = ["attribute_exists(PK)"]
        if allowed_current_statuses:
            status_placeholders = []
            for j, st in enumerate(allowed_current_statuses):
                st_ph = f":curr_s{j}"
                status_placeholders.append(st_ph)
                expr_values[st_ph] = st.value
            cond_parts.append(f"#s IN ({', '.join(status_placeholders)})")

        try:
            response = self._table.update_item(
                Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
                UpdateExpression="SET " + ", ".join(set_parts),
                ConditionExpression=" AND ".join(cond_parts),
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ReturnValues="ALL_NEW",
            )
            return DocumentItem.from_dynamodb_item(response["Attributes"])
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Conditional status update skipped for doc %s (current status not in %s)",
                    document_id, [s.value for s in allowed_current_statuses] if allowed_current_statuses else [],
                )
                return None
            raise

    def delete(self, job_id: str, document_id: str) -> None:
        """Delete a single Document item."""
        self._table.delete_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
        )
        logger.info("Deleted document: %s from job: %s", document_id, job_id)
