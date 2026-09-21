"""
upload_session.py — UploadSession entity model for DynamoDB Single Table Design
================================================================================
PK = JOB#{job_id}   SK = SESSION#{session_id}

Tracks multi-file upload batches, client-to-S3 presigned uploads, pinned job_version,
and coordinates the fast-parse and fallback barrier.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class UploadSessionStatus(str, Enum):
    """Lifecycle states for an upload session."""
    UPLOADING = "UPLOADING"
    FAST_PARSING = "FAST_PARSING"
    FALLBACK_PROCESSING = "FALLBACK_PROCESSING"
    FINAL_RANKING = "FINAL_RANKING"
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class UploadSessionItem(BaseModel):
    """Pydantic model for an UploadSession entity in DynamoDB."""

    session_id: str = Field(default_factory=_new_uuid)
    job_id: str
    org_id: str = "org_default"
    entity_type: str = "UPLOAD_SESSION"

    job_version: int = 1
    expected_document_count: int = 0
    uploaded_document_count: int = 0

    status: UploadSessionStatus = UploadSessionStatus.UPLOADING
    error_message: Optional[str] = None

    version: int = 1
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)
    expires_at: Optional[str] = None

    @property
    def pk(self) -> str:
        return f"JOB#{self.job_id}"

    @property
    def sk(self) -> str:
        return f"SESSION#{self.session_id}"

    def to_dynamodb_item(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "session_id": self.session_id,
            "job_id": self.job_id,
            "org_id": self.org_id,
            "job_version": self.job_version,
            "expected_document_count": self.expected_document_count,
            "uploaded_document_count": self.uploaded_document_count,
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.error_message:
            item["error_message"] = self.error_message
        if self.expires_at:
            item["expires_at"] = self.expires_at
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "UploadSessionItem":
        status_val = item.get("status", UploadSessionStatus.UPLOADING.value)
        try:
            session_status = UploadSessionStatus(status_val)
        except ValueError:
            session_status = UploadSessionStatus.UPLOADING

        return cls(
            session_id=item.get("session_id", ""),
            job_id=item.get("job_id", ""),
            org_id=item.get("org_id", "org_default"),
            entity_type=item.get("entity_type", "UPLOAD_SESSION"),
            job_version=int(item.get("job_version", 1)),
            expected_document_count=int(item.get("expected_document_count", 0)),
            uploaded_document_count=int(item.get("uploaded_document_count", 0)),
            status=session_status,
            error_message=item.get("error_message"),
            version=int(item.get("version", 1)),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            expires_at=item.get("expires_at"),
        )
