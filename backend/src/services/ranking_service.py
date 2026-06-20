"""
ranking_service.py — Candidate ranking orchestrator
=====================================================
Thin service wrapper around CandidateScorer for dependency injection
and FastAPI integration.
"""

from typing import Any, Dict, List
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription, ScoredCandidate


class RankingService:
    """Service layer for candidate ranking."""

    def __init__(self):
        self.scorer = CandidateScorer()

    def rank_candidates(self, jd: JobDescription,
                        candidates: List[Dict[str, Any]]) -> List[ScoredCandidate]:
        """Rank a list of candidate field dicts against a job description."""
        return self.scorer.rank(jd, candidates)
