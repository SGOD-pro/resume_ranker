"""
scoring/knockout_evaluator.py — KnockoutEvaluator
===================================================
Phase 1: Hard knockout checks. Directly ports _phase1_knockout() from
scorer.py with no logic changes.

Returns KnockoutResult. If knocked_out=True, ScoringService sets
final_score=0.0 but still computes sub-scores for UI reporting.
"""

from __future__ import annotations

import re
from typing import Any

from src.ranking.scorer import (
    DEGREE_LEVELS,
    _parse_degree_level,
)
from src.ranking.skill_inference import WEIGHT_INFERRED
from src.registries.skill_registry import (
    find_matches as _find_matches,
)
from src.registries.skill_registry import (
    get_search_variants as _get_search_variants,
)
from src.schemas.scoring import JobDescription
from src.scoring.domain import KnockoutResult


class KnockoutEvaluator:
    """
    Evaluates hard knockout criteria for a single candidate.

    Logic ported verbatim from CandidateScorer._phase1_knockout() —
    no changes to the rules, only refactored into a standalone class.
    """

    def evaluate(  # noqa: PLR0912, PLR0917
        self,
        candidate_dict: dict[str, Any],
        job: JobDescription,
        candidate_skills: list[str],
        total_years: float,
        skill_weights: dict[str, float] | None = None,
        augmented_skills: list[str] | None = None,
    ) -> KnockoutResult:
        """
        Run all Phase 1 checks.

        Args:
            candidate_dict: Full candidate dict (for text section access).
            job: Job description with knockout criteria.
            candidate_skills: Structured skill list.
            total_years: Total computed experience years.
            skill_weights: Inference engine weights (allows inferred skills
                           to satisfy must-have requirements at weight >= 0.75).
            augmented_skills: Skills after text-section augmentation.

        Returns:
            KnockoutResult(knocked_out, reasons)
        """
        reasons: list[str] = []
        skills_to_check = augmented_skills if augmented_skills is not None else candidate_skills

        # ── Must-have skills ──────────────────────────────────────────────
        if job.must_have_skills:
            _, missing = _find_matches(skills_to_check, job.must_have_skills)
            if missing:
                skill_text = self._build_skill_text(candidate_dict, skills_to_check)
                still_missing = []
                for sk in missing:
                    sk_lower = sk.lower().strip()

                    # Inference: weight >= 0.75 satisfies must-have
                    if skill_weights and skill_weights.get(sk, 0.0) >= WEIGHT_INFERRED:
                        continue

                    if len(sk_lower) >= 4:  # noqa: PLR2004
                        variants = _get_search_variants(sk)
                        found = False
                        for variant in variants:
                            if len(variant) >= 3 and re.search(  # noqa: PLR2004
                                r"\b" + re.escape(variant.lower()) + r"\b",
                                skill_text,
                            ):
                                found = True
                                break
                        if found:
                            continue

                    still_missing.append(sk)

                if still_missing:
                    reasons.append(
                        f"Missing must-have skills: {', '.join(still_missing)}"
                    )

        # ── Min years ─────────────────────────────────────────────────────
        if job.min_years > 0 and total_years < job.min_years:
            experience = candidate_dict.get("experience", []) or []
            has_entries = len(experience) >= 2  # noqa: PLR2004

            raw_text = (
                (candidate_dict.get("raw_text_sections") or {}).get("full_text", "") or ""
            ).lower()
            raw_match = re.search(
                r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
                raw_text,
            )
            raw_years = int(raw_match.group(1)) if raw_match else 0

            if not has_entries and raw_years < job.min_years and total_years < job.min_years * 0.5:
                reasons.append(
                    f"Insufficient experience: {total_years:.1f}yr vs {job.min_years}yr required"
                )

        # ── Max years ─────────────────────────────────────────────────────
        if job.max_years < 99 and total_years > job.max_years:  # noqa: PLR2004
            reasons.append(
                f"Exceeds maximum experience: {total_years:.1f}yr vs {job.max_years}yr max"
            )

        # ── Required degree ───────────────────────────────────────────────
        if job.required_degree and job.required_degree.lower() not in ("any", "none", ""):
            required_level = _parse_degree_level(job.required_degree)
            education = candidate_dict.get("education", []) or []
            best_level = max(
                (_parse_degree_level(e.get("degree") or "") for e in education),
                default=0,
            )

            raw_text = (
                (candidate_dict.get("raw_text_sections") or {}).get("full_text", "") or ""
            ).lower()
            for deg_key, deg_val in DEGREE_LEVELS.items():
                if deg_val >= required_level and deg_key in raw_text:
                    best_level = max(best_level, deg_val)
                    break

            if best_level < required_level and required_level > 0:
                reasons.append(
                    f"Degree not met: level {best_level} vs {required_level} ({job.required_degree})"  # noqa: E501
                )

        return KnockoutResult(knocked_out=bool(reasons), reasons=reasons)

    def _build_skill_text(
        self,
        candidate_dict: dict[str, Any],
        skills: list[str],
    ) -> str:
        """Build a text string from skill-bearing sections only."""
        sections = candidate_dict.get("raw_text_sections") or {}
        experience = candidate_dict.get("experience") or []
        projects = candidate_dict.get("projects") or []

        parts = [" ".join(str(s) for s in skills)]
        for key in ("skills", "technical_skills", "summary", "profile"):
            if sections.get(key):
                parts.append(str(sections[key]))
        for exp in experience:
            desc = exp.get("description") or exp.get("responsibilities") or ""
            if desc:
                parts.append(str(desc))
        for proj in projects:
            tech = proj.get("technologies") or []
            if isinstance(tech, list):
                parts.append(" ".join(str(t) for t in tech))

        return " ".join(parts).lower()
