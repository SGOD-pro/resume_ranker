"""
job.py — Job entity model for DynamoDB Single Table Design
============================================================
PK = JOB#{job_id}   SK = METADATA

Stores job description config, status lifecycle, file counts, and remaining barrier counter.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job lifecycle states."""
    CREATED = "created"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    READY_TO_ANALYZE = "READY_TO_ANALYZE"
    SCORING = "SCORING"
    DONE = "DONE"
    DONE_WITH_ERRORS = "DONE_WITH_ERRORS"
    FAILED = "FAILED"

    # Legacy/compatibility aliases
    DOCUMENTS_UPLOADED = "documents_uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SCORED = "scored"
    ARCHIVED = "archived"
    FAST_PARSING = "FAST_PARSING"
    FALLBACK_PROCESSING = "FALLBACK_PROCESSING"
    FINAL_RANKING = "FINAL_RANKING"
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class JobItem(BaseModel):
    """Pydantic model for a Job entity in DynamoDB."""

    # ── Identity & Tenant ──────────────────────────────────────────────────
    job_id: str = Field(default_factory=_new_uuid)
    org_id: str = "org_default"
    session_id: Optional[str] = None
    entity_type: str = "JOB"

    # ── Job Description Config ────────────────────────────────────────────
    title: str = ""
    department: str = ""
    description: str = ""
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    min_years: int = 0
    max_years: int = 99
    education_level: str = "any"
    education_field: str = ""
    keywords: List[str] = Field(default_factory=list)
    weights: Dict[str, float] = Field(default_factory=lambda: {
        "skills": 0.40,
        "experience": 0.25,
        "keywords": 0.20,
        "education": 0.15,
    })

    # ── State & Barrier Accounting ─────────────────────────────────────────
    status: JobStatus = JobStatus.CREATED
    total_files: int = 0
    remaining: int = 0
    usable_files: int = 0
    analyze_requested: bool = False
    analyze_file_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None

    # Legacy compatibility
    document_count: int = 0

    # ── Versioning & Timestamps ───────────────────────────────────────────
    version: int = 1
    job_version: int = 1
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    # ── DynamoDB Keys ─────────────────────────────────────────────────────

    @property
    def pk(self) -> str:
        return f"JOB#{self.job_id}"

    @property
    def sk(self) -> str:
        return "METADATA"

    def is_stalled(self, threshold_seconds: int = 600) -> bool:
        """Return True if job is in active processing state but has made no progress for 10+ minutes."""
        if self.status not in (
            JobStatus.UPLOADING,
            JobStatus.PROCESSING,
            JobStatus.SCORING,
            JobStatus.FAST_PARSING,
            JobStatus.FALLBACK_PROCESSING,
            JobStatus.FINAL_RANKING,
        ):
            return False

        if not self.updated_at:
            return False

        try:
            # Parse ISO timestamp
            dt_str = self.updated_at.replace("Z", "+00:00")
            updated_dt = datetime.fromisoformat(dt_str)
            now_dt = datetime.now(timezone.utc)
            delta = (now_dt - updated_dt).total_seconds()
            return delta > threshold_seconds
        except Exception:
            return False

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        from decimal import Decimal
        serialized_weights = {k: Decimal(str(v)) for k, v in self.weights.items()}
        item: Dict[str, Any] = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "job_id": self.job_id,
            "org_id": self.org_id,
            "title": self.title,
            "department": self.department,
            "description": self.description,
            "must_have_skills": self.must_have_skills,
            "nice_to_have_skills": self.nice_to_have_skills,
            "min_years": self.min_years,
            "max_years": self.max_years,
            "education_level": self.education_level,
            "education_field": self.education_field,
            "keywords": self.keywords,
            "weights": serialized_weights,
            "status": self.status.value,
            "total_files": self.total_files,
            "remaining": self.remaining,
            "usable_files": self.usable_files,
            "analyze_requested": self.analyze_requested,
            "analyze_file_ids": self.analyze_file_ids,
            "document_count": self.document_count or self.total_files,
            "version": self.version,
            "job_version": self.job_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.session_id:
            item["session_id"] = self.session_id
        if self.error_message:
            item["error_message"] = self.error_message
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "JobItem":
        """Deserialize from a DynamoDB item dict."""
        raw_weights = item.get("weights", {})
        weights = {k: float(v) for k, v in raw_weights.items()}
        raw_status = item.get("status", "created")
        try:
            status_obj = JobStatus(raw_status)
        except ValueError:
            status_obj = JobStatus.CREATED

        total_files = int(item.get("total_files", item.get("document_count", 0)))
        remaining = int(item.get("remaining", total_files))
        usable_files = int(item.get("usable_files", 0))

        return cls(
            job_id=item["job_id"],
            org_id=item.get("org_id", "org_default"),
            session_id=item.get("session_id"),
            entity_type=item.get("entity_type", "JOB"),
            title=item.get("title", ""),
            department=item.get("department", ""),
            description=item.get("description", ""),
            must_have_skills=item.get("must_have_skills", []),
            nice_to_have_skills=item.get("nice_to_have_skills", []),
            min_years=int(item.get("min_years", 0)),
            max_years=int(item.get("max_years", 99)),
            education_level=item.get("education_level", "any"),
            education_field=item.get("education_field", ""),
            keywords=item.get("keywords", []),
            weights=weights,
            status=status_obj,
            total_files=total_files,
            remaining=remaining,
            usable_files=usable_files,
            analyze_requested=bool(item.get("analyze_requested", False)),
            analyze_file_ids=item.get("analyze_file_ids", []),
            error_message=item.get("error_message"),
            document_count=int(item.get("document_count", total_files)),
            version=int(item.get("version", 1)),
            job_version=int(item.get("job_version", 1)),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
