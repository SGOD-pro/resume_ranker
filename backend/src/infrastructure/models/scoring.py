"""
scoring.py — Scoring Result entity model for DynamoDB Single Table Design
===========================================================================
PK = JOB#{job_id}   SK = SCORING#{scoring_id}

Stores scoring run metadata. The full ranking JSON (List[ScoredCandidate])
lives ONLY in S3. DynamoDB stores only metadata + denormalized top candidate.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ScoringStatus(str, Enum):
    """Scoring lifecycle states."""
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


class ScoringItem(BaseModel):
    """Pydantic model for a Scoring Result entity in DynamoDB."""

    # ── Identity ──────────────────────────────────────────────────────────
    scoring_id: str = Field(default_factory=_new_uuid)
    job_id: str
    entity_type: str = "SCORING"

    # ── S3 Reference ──────────────────────────────────────────────────────
    s3_result_key: str = ""                         # jobs/{job_id}/scoring/{scoring_id}.json

    # ── Scoring Metadata ──────────────────────────────────────────────────
    ranking_version: int = 1                        # Incremented per re-score
    scoring_algorithm_version: str = "bm25_v1"
    candidate_count: int = 0
    weights_used: Dict[str, float] = Field(default_factory=dict)

    # ── Denormalized Top Candidate (for fast display) ─────────────────────
    top_candidate_name: Optional[str] = None
    top_candidate_score: Optional[float] = None

    # ── State ─────────────────────────────────────────────────────────────
    status: ScoringStatus = ScoringStatus.SCORING

    # ── Versioning ────────────────────────────────────────────────────────
    version: int = 1
    created_at: str = Field(default_factory=_utcnow_iso)
    completed_at: Optional[str] = None

    # ── DynamoDB Keys ─────────────────────────────────────────────────────

    @property
    def pk(self) -> str:
        return f"JOB#{self.job_id}"

    @property
    def sk(self) -> str:
        return f"SCORING#{self.scoring_id}"

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Serialize to a DynamoDB-compatible dict."""
        from decimal import Decimal
        serialized_weights = {k: Decimal(str(v)) for k, v in self.weights_used.items()}
        item: Dict[str, Any] = {
            "PK": self.pk,
            "SK": self.sk,
            "entity_type": self.entity_type,
            "scoring_id": self.scoring_id,
            "job_id": self.job_id,
            "s3_result_key": self.s3_result_key,
            "ranking_version": self.ranking_version,
            "scoring_algorithm_version": self.scoring_algorithm_version,
            "candidate_count": self.candidate_count,
            "weights_used": serialized_weights,
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at,
        }
        if self.top_candidate_name is not None:
            item["top_candidate_name"] = self.top_candidate_name
        if self.top_candidate_score is not None:
            item["top_candidate_score"] = str(self.top_candidate_score)
        if self.completed_at is not None:
            item["completed_at"] = self.completed_at
        return item

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "ScoringItem":
        """Deserialize from a DynamoDB item dict."""
        tcs = item.get("top_candidate_score")
        raw_weights = item.get("weights_used", {})
        weights_used = {k: float(v) for k, v in raw_weights.items()}
        return cls(
            scoring_id=item["scoring_id"],
            job_id=item["job_id"],
            entity_type=item.get("entity_type", "SCORING"),
            s3_result_key=item.get("s3_result_key", ""),
            ranking_version=int(item.get("ranking_version", 1)),
            scoring_algorithm_version=item.get("scoring_algorithm_version", "bm25_v1"),
            candidate_count=int(item.get("candidate_count", 0)),
            weights_used=weights_used,
            top_candidate_name=item.get("top_candidate_name"),
            top_candidate_score=float(tcs) if tcs is not None else None,
            status=ScoringStatus(item.get("status", "scoring")),
            version=int(item.get("version", 1)),
            created_at=item.get("created_at", ""),
            completed_at=item.get("completed_at"),
        )
