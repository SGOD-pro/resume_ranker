"""
fallback_record_repository.py — FallbackRecord CRUD on DynamoDB
================================================================
PK = DOC#{document_id}
SK = FALLBACK#{field_name}#{created_at}
"""

import logging

from boto3.dynamodb.conditions import Key  # type: ignore

from src.infrastructure.models.fallback_record import FallbackRecordItem
from src.infrastructure.repositories.base import _get_table

logger = logging.getLogger(__name__)


class FallbackRecordRepository:
    """CRUD operations for FallbackRecord entities."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create(self, record: FallbackRecordItem) -> FallbackRecordItem:
        """Insert a new FallbackRecord item."""
        item = record.to_dynamodb_item()
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        logger.info("Created fallback record for %s field %s", record.document_id, record.field_name)
        return record

    def list_for_document(self, document_id: str) -> list[FallbackRecordItem]:
        """List all fallback records for a specific document."""
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"DOC#{document_id}") & Key("SK").begins_with("FALLBACK#")
            ),
        )
        items = response.get("Items", [])
        return [FallbackRecordItem.from_dynamodb_item(item) for item in items]
