"""
scoring/embedding_tiebreaker.py — EmbeddingTiebreaker
=======================================================
Conditional semantic similarity scorer.

ADR-06: Invoked ONLY when skill_score is in the ambiguous band (default 0.40–0.60).
Skipped for the ~95% of candidates with a clear skill-match outcome.

Uses sentence-transformers all-MiniLM-L6-v2, self-hosted (no API calls).
Model is loaded lazily on first invocation to avoid Lambda cold-start cost
when the tiebreaker is never needed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default ambiguous band — configurable via ScoringService
AMBIGUOUS_LOW: float = 0.40
AMBIGUOUS_HIGH: float = 0.60


class EmbeddingTiebreaker:
    """
    Semantic embedding cosine-similarity tiebreaker.

    Only fires when skill_score (normalised to 0–1) falls in [AMBIGUOUS_LOW, AMBIGUOUS_HIGH].
    Otherwise returns None immediately — caller treats None as zero-weight.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        ambiguous_low: float = AMBIGUOUS_LOW,
        ambiguous_high: float = AMBIGUOUS_HIGH,
    ) -> None:
        self._model_name = model_name
        self._model: Any = None          # Loaded lazily
        self._low = ambiguous_low
        self._high = ambiguous_high

    def score(
        self,
        skill_score_normalized: float,   # 0.0–1.0 (divide raw score by 100)
        candidate_dict: dict[str, Any],
        jd_text: str,
    ) -> float | None:
        """
        Compute semantic cosine similarity between candidate text and JD.

        Returns:
            float 0–100 if in ambiguous band, else None.
        """
        if not (self._low <= skill_score_normalized <= self._high):
            return None

        try:
            model = self._get_model()
        except Exception:
            logger.warning("sentence-transformers unavailable — skipping tiebreaker")
            return None

        candidate_text = self._build_candidate_text(candidate_dict)
        if not candidate_text or not jd_text:
            return None

        try:
            from sentence_transformers import util as st_util  # noqa: PLC0415

            embeddings = model.encode(
                [candidate_text, jd_text],
                convert_to_tensor=True,
                normalize_embeddings=True,
            )
            cosine = float(st_util.cos_sim(embeddings[0], embeddings[1]).item())
            # Cosine is [-1, 1] — map to [0, 100]
            return max(0.0, min(100.0, (cosine + 1.0) / 2.0 * 100.0))
        except Exception as exc:
            logger.warning("EmbeddingTiebreaker failed: %s", exc)
            return None

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            logger.info("Loading sentence-transformers model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _build_candidate_text(self, candidate_dict: dict[str, Any]) -> str:
        """Build a short representative text from the candidate."""
        skills = candidate_dict.get("skills") or []
        sections = candidate_dict.get("raw_text_sections") or {}
        summary = sections.get("summary") or ""
        experience_text = " ".join(
            (exp.get("description") or "") for exp in (candidate_dict.get("experience") or [])
        )
        return " ".join(filter(None, [
            " ".join(str(s) for s in skills),
            summary,
            experience_text[:500],
        ]))
