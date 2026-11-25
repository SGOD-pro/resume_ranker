"""
message.py — Immutable Queue Message DTO
=========================================
All SQS messages contain IDs and immutable references only, never PDF bytes:
- event_id
- job_id
- session_id
- document_id (or document_ids for batch queues)
- org_id
- job_version
- s3_key
- content_hash
- stage
- attempt_number
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class QueueMessage(BaseModel):
    """Pydantic model for immutable queue messages."""
    event_id: str = Field(default_factory=_new_uuid)
    job_id: str
    session_id: str
    document_id: Optional[str] = None
    document_ids: List[str] = Field(default_factory=list)
    org_id: str = "org_default"
    job_version: int = 1
    s3_key: Optional[str] = None
    content_hash: Optional[str] = None
    stage: str  # "FAST_PARSE", "ODL_BATCH", "NOVA", "FINAL_RANK"
    attempt_number: int = 1
    created_at: str = Field(default_factory=_utcnow_iso)
    receipt_handle: Optional[str] = None
    error_reason: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(self.model_dump(exclude={"receipt_handle"}), default=str)

    @classmethod
    def from_json(cls, json_str: str, receipt_handle: Optional[str] = None) -> "QueueMessage":
        data = json.loads(json_str)
        msg = cls(**data)
        if receipt_handle:
            msg.receipt_handle = receipt_handle
        return msg
