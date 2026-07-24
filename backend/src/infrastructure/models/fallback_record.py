"""
fallback_record.py — DynamoDB model for Nova Fallback usage
============================================================
PK = DOC#{document_id}
SK = FALLBACK#{field_name}#{timestamp}

Tracks individual fields resolved by Amazon Nova during Phase 3 fallback,
including confidence scores and the specific model (Micro vs Lite) used.
"""

from typing import Any

from pydantic import BaseModel, Field

from src.infrastructure.models.document import _new_uuid, _utcnow_iso


class FallbackRecordItem(BaseModel):
    """Pydantic model for a FallbackRecord entity in DynamoDB."""

    document_id: str
    field_name: str
    record_id: str = Field(default_factory=_new_uuid)
    entity_type: str = "FALLBACK_RECORD"

    # ── Fallback Metadata ──────────────────────────────────────────────────
    nova_model_used: str          # e.g., "us.amazon.nova-micro-v1:0"
    confidence: float             # 0.0–1.0 returned by LLM
    resolved_value: Any           # The JSON value extracted
    
    # ── Original Context ───────────────────────────────────────────────────
    original_text: str            # The UnresolvedChunk text sent to Nova

    # ── Versioning ─────────────────────────────────────────────────────────
    created_at: str = Field(default_factory=_utcnow_iso)

    # ── DynamoDB Keys ──────────────────────────────────────────────────────

    @property
    def pk(self) -> str:
        return f"DOC#{self.document_id}"

    @property
    def sk(self) -> str:
        return f"FALLBACK#{self.field_name}#{self.created_at}"

    def to_dynamodb_item(self) -> dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        return {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "document_id": self.document_id,
            "record_id": self.record_id,
            "field_name": self.field_name,
            "nova_model_used": self.nova_model_used,
            "confidence": str(self.confidence),  # DynamoDB handles floats poorly, store as string or Decimal
            "resolved_value": self.resolved_value,
            "original_text": self.original_text,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dynamodb_item(cls, item: dict[str, Any]) -> "FallbackRecordItem":
        """Deserialize from a DynamoDB item dict."""
        return cls(
            document_id=item["document_id"],
            field_name=item["field_name"],
            record_id=item.get("record_id", _new_uuid()),
            entity_type=item.get("entity_type", "FALLBACK_RECORD"),
            nova_model_used=item["nova_model_used"],
            confidence=float(item["confidence"]),
            resolved_value=item["resolved_value"],
            original_text=item["original_text"],
            created_at=item["created_at"],
        )
