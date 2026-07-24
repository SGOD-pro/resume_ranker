"""
scoring/skill_scorer.py — BM25SkillScorer
==========================================
Wraps the fixed-IDF BM25 variant. Single responsibility: skill score only.
"""

from __future__ import annotations

from typing import Any

from src.ranking.bm25_scorer import bm25_skill_score_fixed_idf
from src.ranking.idf_table import get_idf
from src.ranking.skill_inference import WEIGHT_INFERRED, SkillInferenceEngine
from src.registries.skill_registry import match as _skill_match


class BM25SkillScorer:
    """
    Fixed-IDF BM25 skill scorer.

    ADR-04: IDF comes from the synthetic reference corpus in idf_table.py,
    never from the current request pool.

    Inference engine is injected so tests can mock it.
    """

    def __init__(self, inference_engine: SkillInferenceEngine | None = None) -> None:
        self._inference = inference_engine or SkillInferenceEngine()  # type: ignore[no-untyped-call]

    def score(
        self,
        candidate_skills: list[str],
        jd_must_have: list[str],
        jd_nice_to_have: list[str],
        candidate_dict: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        """
        Score a candidate's skills against JD requirements.

        Args:
            candidate_skills: Extracted skill list.
            jd_must_have: JD must-have skills.
            jd_nice_to_have: JD nice-to-have skills.
            candidate_dict: Full candidate dict (for text-section skill augmentation).

        Returns:
            (raw_score 0–100, detail_dict)
            detail_dict contains: matched_must, missing_must, matched_nice,
                                  matched_inferred, matched_related, extra_skills,
                                  skill_weights
        """
        all_jd_skills = list(set(jd_must_have + jd_nice_to_have))

        # Augment candidate skills by scanning targeted text sections
        augmented = self._augment_skills(candidate_skills, all_jd_skills, candidate_dict)

        # Inference engine: returns fractional weights for inferred/related skills
        inference = self._inference.match_skills(augmented, all_jd_skills)
        skill_weights = inference.skill_weights

        # Fixed-IDF BM25
        raw_score = bm25_skill_score_fixed_idf(
            candidate_skills=augmented,
            jd_skills=all_jd_skills,
            get_idf_fn=get_idf,
            skill_weights=skill_weights,
        )

        # Build breakdown detail
        matched_must = [
            sk for sk in jd_must_have
            if skill_weights.get(sk, 0.0) >= WEIGHT_INFERRED
        ]
        missing_must = [sk for sk in jd_must_have if sk not in matched_must]

        matched_nice = [
            sk for sk in jd_nice_to_have
            if skill_weights.get(sk, 0.0) > 0
        ]

        all_jd_set = {s.lower() for s in all_jd_skills}
        extra = [
            s for s in candidate_skills
            if s.lower() not in all_jd_set
            and not any(_skill_match(s, j) for j in all_jd_skills)
        ]

        detail: dict[str, Any] = {
            "matched_must_have":    matched_must,
            "missing_must_have":    missing_must,
            "matched_nice_to_have": matched_nice,
            "matched_inferred":     [m.skill for m in inference.inferred_skills],
            "matched_related":      [m.skill for m in inference.related_skills],
            "extra_skills":         extra,
            "skill_weights":        skill_weights,
            "augmented_skills":     augmented,
        }
        return raw_score, detail

    def _augment_skills(
        self,
        base_skills: list[str],
        jd_skills: list[str],
        candidate_dict: dict[str, Any],
    ) -> list[str]:
        """
        Scan text sections to find JD skills the candidate has but didn't list.
        Same logic as V1's _score_candidate → augmented_skills block.
        """
        import re  # noqa: PLC0415

        from src.registries.skill_registry import get_search_variants  # noqa: PLC0415

        sections = candidate_dict.get("raw_text_sections", {}) or {}
        experience = candidate_dict.get("experience", []) or []
        projects = candidate_dict.get("projects", []) or []

        skill_text_parts = [" ".join(str(s) for s in base_skills)]
        for key in ("skills", "technical_skills", "summary", "profile"):
            if sections.get(key):
                skill_text_parts.append(str(sections[key]))
        for exp in experience:
            desc = exp.get("description") or exp.get("responsibilities") or ""
            if desc:
                skill_text_parts.append(str(desc))
        for proj in projects:
            tech = proj.get("technologies") or []
            if isinstance(tech, list):
                skill_text_parts.append(" ".join(str(t) for t in tech))
        skill_text = " ".join(skill_text_parts).lower()

        augmented = list(base_skills)
        for jd_sk in jd_skills:
            if any(_skill_match(cs, jd_sk) for cs in augmented):
                continue
            for variant in get_search_variants(jd_sk):
                if len(variant) >= 3 and re.search(  # noqa: PLR2004
                    r"\b" + re.escape(variant.lower()) + r"\b", skill_text
                ):
                    augmented.append(jd_sk)
                    break

        return augmented
