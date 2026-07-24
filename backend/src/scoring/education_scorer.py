"""
scoring/education_scorer.py — EducationScorer
===============================================
Delegates to V1's education_score() from similarity.py. No math changes.
Single responsibility: education score only.
"""

from __future__ import annotations

from typing import Any

from src.ranking.similarity import education_score as _education_score
from src.schemas.scoring import JobDescription


class EducationScorer:
    """
    Scores candidate education against JD degree requirements.
    Delegates to V1's education scoring math unchanged.
    """

    def score(
        self,
        candidate_dict: dict[str, Any],
        job: JobDescription,
    ) -> tuple[float, str | None, str | None]:
        """
        Returns:
            (score 0–100, degree_level_str | None, degree_field_str | None)
        """
        return _education_score(candidate_dict, job)
