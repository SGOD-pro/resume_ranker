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
    """Document extraction lifecycle states."""
    # Phase 2 legacy
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    SCORED = "scored"
    PARSE_FAILED = "parse_failed"

    # Durable pipeline states (v2.2)
    UPLOAD_INITIALIZED = "UPLOAD_INITIALIZED"
    UPLOADED = "UPLOADED"
    FAST_PARSE_QUEUED = "FAST_PARSE_QUEUED"
    FAST_PARSING = "FAST_PARSING"
    NEEDS_ODL = "NEEDS_ODL"
    ODL_QUEUED = "ODL_QUEUED"
    ODL_PARSING = "ODL_PARSING"
    NEEDS_NOVA = "NEEDS_NOVA"
    NOVA_QUEUED = "NOVA_QUEUED"
    NOVA_PARSING = "NOVA_PARSING"
    STRUCTURED_PARSED = "STRUCTURED_PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"

    # ── V1 backwards-compat aliases ────
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    EXTRACTION_FAILED = "extraction_failed"

    def is_terminal_fast_parse(self) -> bool:
        return self in (
            DocumentStatus.STRUCTURED_PARSED,
            DocumentStatus.NEEDS_ODL,
            DocumentStatus.NEEDS_NOVA,
            DocumentStatus.REVIEW_REQUIRED,
            DocumentStatus.FAILED,
            DocumentStatus.REJECTED_DUPLICATE,
            DocumentStatus.PARSED,
            DocumentStatus.PARSE_FAILED,
            DocumentStatus.SCORED,
        )

    def is_terminal_extraction(self) -> bool:
        return self in (
            DocumentStatus.STRUCTURED_PARSED,
            DocumentStatus.REVIEW_REQUIRED,
            DocumentStatus.FAILED,
            DocumentStatus.REJECTED_DUPLICATE,
            DocumentStatus.PARSED,
            DocumentStatus.PARSE_FAILED,
            DocumentStatus.SCORED,
        )




def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DocumentItem(BaseModel):
    """Pydantic model for a Document entity in DynamoDB."""

    # ── Identity & Tenant ──────────────────────────────────────────────────
    document_id: str = Field(default_factory=_new_uuid)
    job_id: str
    session_id: Optional[str] = None
    org_id: str = "org_default"
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
    identity_status: Optional[str] = None           # CONFIRMED, PROVISIONAL, UNRESOLVED
    identity_confidence: Optional[float] = None
    fallback_reason: Optional[str] = None
    error_reason: Optional[str] = None
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
            "org_id": self.org_id,
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
        if self.session_id is not None:
            item["session_id"] = self.session_id
        if self.identity_status is not None:
            item["identity_status"] = self.identity_status
        if self.identity_confidence is not None:
            item["identity_confidence"] = str(self.identity_confidence)
        if self.fallback_reason is not None:
            item["fallback_reason"] = self.fallback_reason
        if self.error_reason is not None:
            item["error_reason"] = self.error_reason
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
        ic = item.get("identity_confidence")
        
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

        try:
            status_obj = DocumentStatus(raw_status)
        except ValueError:
            status_obj = DocumentStatus.PENDING
            
        return cls(
            document_id=item["document_id"],
            job_id=item["job_id"],
            session_id=item.get("session_id"),
            org_id=item.get("org_id", "org_default"),
            entity_type=item.get("entity_type", "DOCUMENT"),
            filename=item.get("filename", ""),
            file_size=int(item.get("file_size", 0)),
            content_hash=item.get("content_hash", ""),
            s3_pdf_key=item.get("s3_pdf_key", ""),
            s3_extracted_key=item.get("s3_extracted_key"),
            extraction_quality=float(eq) if eq is not None else None,
            page_count=int(item["page_count"]) if item.get("page_count") is not None else None,
            candidate_name=item.get("candidate_name"),
            identity_status=item.get("identity_status"),
            identity_confidence=float(ic) if ic is not None else None,
            fallback_reason=item.get("fallback_reason"),
            error_reason=item.get("error_reason"),
            parser_version=item.get("parser_version"),
            pipeline_version=item.get("pipeline_version", "v3"),
            status=status_obj,
            version=int(item.get("version", 1)),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
