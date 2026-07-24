"""
scoring/experience_scorer.py — ExperienceScorer
=================================================
Delegates to V1's experience_score() from similarity.py. No math changes.
Single responsibility: experience score only.
"""

from __future__ import annotations

from typing import Any

from src.ranking.similarity import experience_score as _experience_score
from src.schemas.scoring import JobDescription


class ExperienceScorer:
    """
    Scores candidate experience against JD requirements.

    Delegates directly to the V1 experience scoring math, which was
    already validated at 100% F1 on the benchmark. No changes.
    """

    def score(
        self,
        candidate_dict: dict[str, Any],
        job: JobDescription,
    ) -> tuple[float, str | None]:
        """
        Returns:
            (score 0–100, best_title_match_str | None)
        """
        return _experience_score(candidate_dict, job)
