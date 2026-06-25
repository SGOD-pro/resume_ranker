"""
job.py — Job entity model for DynamoDB Single Table Design
============================================================
PK = JOB#{job_id}   SK = METADATA

Stores job description config, status lifecycle, and document count.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job lifecycle states."""
    CREATED = "created"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SCORING = "scoring"
    SCORED = "scored"
    ARCHIVED = "archived"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class JobItem(BaseModel):
    """Pydantic model for a Job entity in DynamoDB."""

    # ── Identity ──────────────────────────────────────────────────────────
    job_id: str = Field(default_factory=_new_uuid)
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

    # ── State ─────────────────────────────────────────────────────────────
    status: JobStatus = JobStatus.CREATED
    document_count: int = 0

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
        return "METADATA"

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        from decimal import Decimal
        # Convert float weights to Decimal
        serialized_weights = {k: Decimal(str(v)) for k, v in self.weights.items()}
        item = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "job_id": self.job_id,
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
            "document_count": self.document_count,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "JobItem":
        """Deserialize from a DynamoDB item dict."""
        raw_weights = item.get("weights", {})
        # Convert Decimal values back to float
        weights = {k: float(v) for k, v in raw_weights.items()}
        return cls(
            job_id=item["job_id"],
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
            status=JobStatus(item.get("status", "created")),
            document_count=int(item.get("document_count", 0)),
            version=int(item.get("version", 1)),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
