"""
file.py — File/Document entity model for DynamoDB Single Table Design
=====================================================================
PK = JOB#{job_id}   SK = FILE#{file_id}

Tracks per-file upload, Stage 1 (PyMuPDF), Stage 2 (ODL/Nova), and terminal status.
Terminal states: S1_FAILED, S2_DONE, S2_FAILED, REMOVED.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """File processing lifecycle states."""
    # Non-terminal states
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    S1_PROCESSING = "S1_PROCESSING"
    S1_DONE = "S1_DONE"            # Fast parse succeeded but needs Stage 2 fallback
    S2_PROCESSING = "S2_PROCESSING"

    # Terminal states (Amendment 2: exactly these 4 decrement job.remaining)
    S1_FAILED = "S1_FAILED"
    S2_DONE = "S2_DONE"            # Either directly from fast-path or via Stage 2
    S2_FAILED = "S2_FAILED"
    REMOVED = "REMOVED"


TERMINAL_FILE_STATUSES: Set[str] = {
    FileStatus.S1_FAILED.value,
    FileStatus.S2_DONE.value,
    FileStatus.S2_FAILED.value,
    FileStatus.REMOVED.value,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class FileItem(BaseModel):
    """Pydantic model for a File item in DynamoDB."""

    job_id: str
    file_id: str = Field(default_factory=_new_uuid)
    filename: str = ""
    file_size: int = 0
    status: FileStatus = FileStatus.PENDING_UPLOAD

    # S3 Keys
    s3_raw_key: str = ""        # jobs/{job_id}/raw/{file_id}.pdf
    s3_stage1_key: Optional[str] = None  # jobs/{job_id}/stage1/{file_id}.json
    s3_extracted_key: Optional[str] = None  # jobs/{job_id}/stage2/{file_id}.json

    # Metadata & Quality
    needs_fallback: bool = False
    low_confidence_extraction: bool = False
    fallback_reason: Optional[str] = None
    candidate_name: Optional[str] = None
    error_message: Optional[str] = None

    # Timestamps
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    @property
    def pk(self) -> str:
        return f"JOB#{self.job_id}"

    @property
    def sk(self) -> str:
        return f"FILE#{self.file_id}"

    @property
    def is_terminal(self) -> bool:
        return self.status.value in TERMINAL_FILE_STATUSES

    def to_dynamodb_item(self) -> Dict[str, Any]:
        item: Dict[str, Any] = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": "FILE",
            "job_id": self.job_id,
            "file_id": self.file_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "status": self.status.value,
            "s3_raw_key": self.s3_raw_key or f"jobs/{self.job_id}/raw/{self.file_id}.pdf",
            "needs_fallback": self.needs_fallback,
            "low_confidence_extraction": self.low_confidence_extraction,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.fallback_reason:
            item["fallback_reason"] = self.fallback_reason
        if self.s3_stage1_key:
            item["s3_stage1_key"] = self.s3_stage1_key
        if self.s3_extracted_key:
            item["s3_extracted_key"] = self.s3_extracted_key
        if self.candidate_name:
            item["candidate_name"] = self.candidate_name
        if self.error_message:
            item["error_message"] = self.error_message
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "FileItem":
        raw_status = item.get("status", "PENDING_UPLOAD")
        try:
            status_obj = FileStatus(raw_status)
        except ValueError:
            status_obj = FileStatus.PENDING_UPLOAD

        return cls(
            job_id=item.get("job_id", ""),
            file_id=item.get("file_id", ""),
            filename=item.get("filename", ""),
            file_size=int(item.get("file_size", 0)),
            status=status_obj,
            s3_raw_key=item.get("s3_raw_key", ""),
            s3_stage1_key=item.get("s3_stage1_key"),
            s3_extracted_key=item.get("s3_extracted_key"),
            needs_fallback=bool(item.get("needs_fallback", False)),
            low_confidence_extraction=bool(item.get("low_confidence_extraction", False)),
            fallback_reason=item.get("fallback_reason"),
            candidate_name=item.get("candidate_name"),
            error_message=item.get("error_message"),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
