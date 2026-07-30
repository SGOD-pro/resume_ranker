"""
document.py — Document entity model for DynamoDB Single Table Design
=====================================================================
PK = JOB#{job_id}   SK = DOC#{document_id}

Stores uploaded resume metadata, S3 keys, and extraction state.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Document extraction lifecycle states.

    Phase 2 state machine: PENDING → PARSING → PARSED → SCORED
    See phases.md for gate criteria.
    """
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    SCORED = "scored"
    PARSE_FAILED = "parse_failed"

    # ── V1 backwards-compat aliases (mapped in from_dynamodb_item) ────
    UPLOADED = "uploaded"           # V1 alias → treated as PENDING
    EXTRACTING = "extracting"      # V1 alias → treated as PARSING
    EXTRACTED = "extracted"        # V1 alias → treated as PARSED
    EXTRACTION_FAILED = "extraction_failed"  # V1 alias → treated as PARSE_FAILED


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DocumentItem(BaseModel):
    """Pydantic model for a Document entity in DynamoDB."""

    # ── Identity ──────────────────────────────────────────────────────────
    document_id: str = Field(default_factory=_new_uuid)
    job_id: str
    entity_type: str = "DOCUMENT"

    # ── File Metadata ─────────────────────────────────────────────────────
    filename: str = ""
    file_size: int = 0
    content_hash: str = ""                          # SHA-256 for dedup

    # ── S3 Keys ───────────────────────────────────────────────────────────
    s3_pdf_key: str = ""                            # jobs/{job_id}/resumes/{doc_id}.pdf
    s3_extracted_key: Optional[str] = None          # jobs/{job_id}/extracted/{doc_id}.json

    # ── Extraction Results ────────────────────────────────────────────────
    extraction_quality: Optional[float] = None      # 0.0–1.0
    page_count: Optional[int] = None
    candidate_name: Optional[str] = None            # Extracted name
    parser_version: Optional[str] = None            # Extraction pipeline version
    pipeline_version: str = "v3"

    # ── State ─────────────────────────────────────────────────────────────
    status: DocumentStatus = DocumentStatus.PENDING

    # ── Versioning ────────────────────────────────────────────────────────
    version: int = 1
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    # ── DynamoDB Keys ─────────────────────────────────────────────────────

    @property
    def pk(self) -> str:
        return f"JOB#{self.job_id}"

    @property
    def sk(self) -> str:
        return f"DOC#{self.document_id}"

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        item: Dict[str, Any] = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "document_id": self.document_id,
            "job_id": self.job_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "content_hash": self.content_hash,
            "s3_pdf_key": self.s3_pdf_key,
            "status": self.status.value,
            "pipeline_version": self.pipeline_version,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        # Optional fields — only include if not None (DynamoDB doesn't like None)
        if self.s3_extracted_key is not None:
            item["s3_extracted_key"] = self.s3_extracted_key
        if self.extraction_quality is not None:
            item["extraction_quality"] = str(self.extraction_quality)
        if self.page_count is not None:
            item["page_count"] = self.page_count
        if self.candidate_name is not None:
            item["candidate_name"] = self.candidate_name
        if self.parser_version is not None:
            item["parser_version"] = self.parser_version
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "DocumentItem":
        """Deserialize from a DynamoDB item dict."""
        eq = item.get("extraction_quality")
        
        # Map V1 backwards-compatibility statuses to Phase 2
        raw_status = item.get("status", "pending")
        if raw_status == "uploaded":
            raw_status = "pending"
        elif raw_status == "extracting":
            raw_status = "parsing"
        elif raw_status == "extracted":
            raw_status = "parsed"
        elif raw_status == "extraction_failed":
            raw_status = "parse_failed"
            
        return cls(
            document_id=item["document_id"],
            job_id=item["job_id"],
            entity_type=item.get("entity_type", "DOCUMENT"),
            filename=item.get("filename", ""),
            file_size=int(item.get("file_size", 0)),
            content_hash=item.get("content_hash", ""),
            s3_pdf_key=item.get("s3_pdf_key", ""),
            s3_extracted_key=item.get("s3_extracted_key"),
            extraction_quality=float(eq) if eq is not None else None,
            page_count=int(item["page_count"]) if item.get("page_count") is not None else None,
            candidate_name=item.get("candidate_name"),
            parser_version=item.get("parser_version"),
            pipeline_version=item.get("pipeline_version", "v3"),
            status=DocumentStatus(raw_status),
            version=int(item.get("version", 1)),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
