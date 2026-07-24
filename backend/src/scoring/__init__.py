"""
scoring/__init__.py — Phase 4 JD Scoring Engine
"""

from src.scoring.domain import (
    CompositeScore,
    KnockoutResult,
    ScoringResult,
    ScoringWeights,
)
from src.scoring.scoring_service import ScoringService, compute_composite

__all__ = [
    "ScoringService",
    "compute_composite",
    "ScoringResult",
    "KnockoutResult",
    "CompositeScore",
    "ScoringWeights",
]
