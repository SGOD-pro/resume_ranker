"""
scoring/domain.py — Phase 4 domain types
=========================================
All output types from ScoringService live here.
These are FROZEN dataclasses — immutable after construction.

Key contract:
  - ScoringResult: raw per-signal scores, never a weighted composite.
  - CompositeScore: weighted composite, computed at read time from ScoringResult.
  - KnockoutResult: Phase 1 hard knockout — if knocked_out=True, final_score=0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Phase 1 output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnockoutResult:
    """
    Result of Phase 1 hard knockout checks.

    If knocked_out=True, the candidate is still scored (sub-scores computed)
    but final_score is forced to 0.0 for ranking purposes.
    Sub-scores are preserved so the UI can explain why the candidate was filtered.
    """
    knocked_out: bool
    reasons: list[str]


# ---------------------------------------------------------------------------
# Phase 2 output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringResult:
    """
    Raw per-signal scores for a single candidate against a single JD.

    These are NEVER stored as a composite — composite is computed at read time
    from these values + a ScoringWeights config. This is ADR-07.

    All scores are 0.0–100.0 before weighting.
    """
    document_id: str

    # Core signal scores (0–100)
    skill_score: float          # BM25 fixed-IDF skill match
    experience_score: float     # Years + title match
    education_score: float      # Degree level match
    keyword_score: float        # Free-text keyword overlap (0.0 if JD has none)

    # Knockout
    knockout_result: KnockoutResult

    # Bonuses (added after weighting, capped at 100 total)
    project_bonus: float = 0.0
    prestige_bonus: float = 0.0
    cert_bonus: float = 0.0

    # Domain penalty (negative float, applied to skill_score only)
    domain_penalty: float = 0.0     # e.g. -30.0 means -30% off skill_score

    # Match detail (for UI breakdown)
    matched_must_have: list[str] = field(default_factory=list)
    missing_must_have: list[str] = field(default_factory=list)
    matched_nice_to_have: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    extra_skills: list[str] = field(default_factory=list)

    # Inference detail (inferred / related skills that contributed)
    matched_inferred: list[str] = field(default_factory=list)
    matched_related: list[str] = field(default_factory=list)

    # Anomaly flags (for UI warnings)
    flags: list[str] = field(default_factory=list)

    # Semantic score (None = not computed, only fires in ambiguous band)
    semantic_score: float | None = None


# ---------------------------------------------------------------------------
# Phase 3: Composite (computed at read time)
# ---------------------------------------------------------------------------

@dataclass
class CompositeScore:
    """
    Final ranked output for a single candidate.

    final_score is computed from ScoringResult + ScoringWeights at read time.
    This object is NOT persisted — it is derived on demand.
    """
    document_id: str
    final_score: float          # 0–100, weighted composite
    percentile: float           # 0–100 (relative to the pool)
    rank: int                   # 1-based
    scoring_result: ScoringResult


# ---------------------------------------------------------------------------
# Scoring weights (passed in by the caller — not hard-coded here)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringWeights:
    """
    Per-JD scoring weights. Must sum to 1.0 (enforced at construction).

    Default mirrors V1's benchmark-tuned weights.
    """
    skills: float = 0.40
    experience: float = 0.25
    keywords: float = 0.20
    education: float = 0.15
    semantic: float = 0.0       # Only non-zero when EmbeddingTiebreaker fires

    def __post_init__(self) -> None:
        total = self.skills + self.experience + self.keywords + self.education
        if not (0.99 <= total <= 1.01):  # noqa: PLR2004
            raise ValueError(
                f"ScoringWeights must sum to 1.0 (got {total:.3f}). "
                "semantic weight is additive — do not include it in the base sum."
            )
