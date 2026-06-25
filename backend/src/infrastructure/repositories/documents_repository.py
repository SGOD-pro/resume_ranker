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
                ":status": DocumentStatus.EXTRACTED.value,
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
        Scans DOC# items for the job and filters by content_hash.
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

    def delete(self, job_id: str, document_id: str) -> None:
        """Delete a single Document item."""
        self._table.delete_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"DOC#{document_id}"},
        )
        logger.info("Deleted document: %s from job: %s", document_id, job_id)
