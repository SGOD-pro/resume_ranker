"""
scoring/flag_detector.py — FlagDetector
========================================
Anomaly detection: wraps _detect_anomalies() from scorer.py.
Single responsibility: produce human-readable flags for the UI.
"""

from __future__ import annotations

from typing import Any

from src.ranking.scorer import _detect_anomalies
from src.ranking.similarity import compute_total_experience_years as _exp_years
from src.schemas.scoring import JobDescription


class FlagDetector:
    """
    Detects anomalies in a candidate profile (gaps, overqualification, etc.)
    and returns a list of human-readable flag strings for the recruiter UI.
    """

    def detect(
        self,
        candidate_dict: dict[str, Any],
        job: JobDescription,
    ) -> list[str]:
        """
        Returns a list of anomaly flag strings. Empty list = no anomalies.
        """
        experience = candidate_dict.get("experience") or []
        total_years = _exp_years(experience)
        return _detect_anomalies(candidate_dict, total_years, job)
