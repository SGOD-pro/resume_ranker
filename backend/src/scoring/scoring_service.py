"""
scoring/scoring_service.py — ScoringService orchestrator
=========================================================
Phase 4 JD Scoring Engine entry point.

Responsibilities (each delegated to a single-responsibility component):
  1. KnockoutEvaluator   — Phase 1 hard knockout
  2. BM25SkillScorer     — fixed-IDF skill score (ADR-04)
  3. ExperienceScorer    — years + title match
  4. EducationScorer     — degree level match
  5. FlagDetector        — anomaly flags
  6. EmbeddingTiebreaker — conditional semantic score (ambiguous band only)

Composite score is NEVER stored — computed at read time by compute_composite().
"""

from __future__ import annotations

import logging

from src.extraction.domain_extraction import ExtractionResult
from src.ranking.domain_classifier import DomainClassifier
from src.ranking.scorer import (
    _cert_bonus,
    _prestige_bonus,
    _project_skill_bonus,
)
from src.ranking.similarity import (
    compute_total_experience_years as _exp_years,
)
from src.ranking.similarity import (
    keyword_score as _keyword_score,
)
from src.schemas.scoring import JobDescription
from src.scoring.domain import (
    CompositeScore,
    ScoringResult,
    ScoringWeights,
)
from src.scoring.education_scorer import EducationScorer
from src.scoring.embedding_tiebreaker import EmbeddingTiebreaker
from src.scoring.experience_scorer import ExperienceScorer
from src.scoring.extraction_adapter import extraction_result_to_candidate_dict
from src.scoring.flag_detector import FlagDetector
from src.scoring.knockout_evaluator import KnockoutEvaluator
from src.scoring.skill_scorer import BM25SkillScorer

logger = logging.getLogger(__name__)


class ScoringService:
    """
    JD Scoring Engine.

    Usage (single candidate):
        svc = ScoringService()
        result = svc.score(extraction, job)

    Usage (rank a pool):
        results = [svc.score(e, job) for e in extractions]
        ranked  = svc.rank(results, weights=ScoringWeights())

    Design invariant:
        score() is a pure function over (ExtractionResult, JobDescription).
        Given identical inputs it MUST return bit-identical outputs.
        This is enforced by the determinism unit test.
    """

    def __init__(  # noqa: PLR0917
        self,
        skill_scorer: BM25SkillScorer | None = None,
        experience_scorer: ExperienceScorer | None = None,
        education_scorer: EducationScorer | None = None,
        knockout_evaluator: KnockoutEvaluator | None = None,
        flag_detector: FlagDetector | None = None,
        embedding_tiebreaker: EmbeddingTiebreaker | None = None,
        domain_classifier: DomainClassifier | None = None,
    ) -> None:
        self._skill = skill_scorer or BM25SkillScorer()
        self._exp = experience_scorer or ExperienceScorer()
        self._edu = education_scorer or EducationScorer()
        self._knockout = knockout_evaluator or KnockoutEvaluator()
        self._flags = flag_detector or FlagDetector()
        self._tiebreaker = embedding_tiebreaker or EmbeddingTiebreaker()
        self._domain = domain_classifier or DomainClassifier()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        extraction: ExtractionResult,
        job: JobDescription,
        document_id: str = "",
    ) -> ScoringResult:
        """
        Score a single candidate against a single JD.

        Returns ScoringResult with per-signal scores and breakdown detail.
        final_score is NOT computed here — call compute_composite().
        """
        doc_id = document_id or extraction.document_id

        # Bridge Phase 2/3 output to legacy dict format
        cand = extraction_result_to_candidate_dict(extraction, doc_id)

        all_jd_skills = list(set(job.must_have_skills + job.nice_to_have_skills))
        experience = cand.get("experience") or []
        total_years = _exp_years(experience)

        # ── Skills (fixed-IDF BM25 + inference) ──────────────────────────
        skill_raw, skill_detail = self._skill.score(
            candidate_skills=cand.get("skills") or [],
            jd_must_have=job.must_have_skills,
            jd_nice_to_have=job.nice_to_have_skills,
            candidate_dict=cand,
        )

        augmented_skills: list[str] = skill_detail.get("augmented_skills") or []
        skill_weights: dict[str, float] = skill_detail.get("skill_weights") or {}

        # ── Knockout (Phase 1) ─────────────────────────────────────────
        knockout = self._knockout.evaluate(
            candidate_dict=cand,
            job=job,
            candidate_skills=cand.get("skills") or [],
            total_years=total_years,
            skill_weights=skill_weights,
            augmented_skills=augmented_skills,
        )

        # ── Apply domain penalty to skill score ───────────────────────
        cand_domain, _, cand_conf = self._domain.classify_with_subdomain(cand)
        jd_domain, jd_conf = self._domain.classify_jd(
            job.title, all_jd_skills, job.description, job.department
        )
        domain_penalty = self._compute_domain_penalty(
            jd_domain, cand_domain, jd_conf, cand_conf
        )
        skill_score = max(0.0, skill_raw * (1.0 + domain_penalty / 100.0))

        # ── Experience ─────────────────────────────────────────────────
        exp_score, _ = self._exp.score(cand, job)

        # ── Education ──────────────────────────────────────────────────
        edu_score, _, _ = self._edu.score(cand, job)

        # ── Keywords (free-text overlap) ───────────────────────────────
        kw_score, matched_kw, missing_kw = _keyword_score(cand, job)

        # ── Bonuses ────────────────────────────────────────────────────
        proj_bonus, _ = _project_skill_bonus(cand, all_jd_skills)
        pres_bonus, _ = _prestige_bonus(cand)
        cert_bonus_val, _ = _cert_bonus(cand, job)

        # ── Semantic tiebreaker (conditional) ─────────────────────────
        jd_text = f"{job.title} {job.description} {' '.join(all_jd_skills)}"
        semantic = self._tiebreaker.score(
            skill_score_normalized=skill_score / 100.0,
            candidate_dict=cand,
            jd_text=jd_text,
        )

        # ── Anomaly flags ──────────────────────────────────────────────
        flags = self._flags.detect(cand, job)

        return ScoringResult(
            document_id=doc_id,
            skill_score=round(skill_score, 2),
            experience_score=round(exp_score, 2),
            education_score=round(edu_score, 2),
            keyword_score=round(kw_score, 2),
            knockout_result=knockout,
            project_bonus=round(proj_bonus, 2),
            prestige_bonus=round(pres_bonus, 2),
            cert_bonus=round(cert_bonus_val, 2),
            domain_penalty=round(domain_penalty, 2),
            matched_must_have=skill_detail.get("matched_must_have") or [],
            missing_must_have=skill_detail.get("missing_must_have") or [],
            matched_nice_to_have=skill_detail.get("matched_nice_to_have") or [],
            matched_keywords=list(matched_kw) if matched_kw else [],
            missing_keywords=list(missing_kw) if missing_kw else [],
            extra_skills=skill_detail.get("extra_skills") or [],
            matched_inferred=skill_detail.get("matched_inferred") or [],
            matched_related=skill_detail.get("matched_related") or [],
            flags=flags,
            semantic_score=round(semantic, 2) if semantic is not None else None,
        )

    def rank(
        self,
        results: list[ScoringResult],
        weights: ScoringWeights | None = None,
    ) -> list[CompositeScore]:
        """
        Compute composite scores and rank a pool of ScoringResult objects.

        Deterministic: same input list in any order → same relative ranking.
        Knocked-out candidates always rank below non-knocked-out candidates.
        """
        w = weights or ScoringWeights()

        composites: list[CompositeScore] = []
        for r in results:
            final = compute_composite(r, w)
            composites.append(CompositeScore(
                document_id=r.document_id,
                final_score=final,
                percentile=0.0,   # Populated after sort
                rank=0,            # Populated after sort
                scoring_result=r,
            ))

        # Sort: non-knocked-out first, then by final_score descending
        composites.sort(
            key=lambda c: (
                not c.scoring_result.knockout_result.knocked_out,
                c.final_score,
            ),
            reverse=True,
        )

        # Assign ranks and percentiles
        active = [c for c in composites if not c.scoring_result.knockout_result.knocked_out]
        max_score = active[0].final_score if active else 1.0

        for i, c in enumerate(composites):
            c.rank = i + 1
            if c.scoring_result.knockout_result.knocked_out:
                c.percentile = 0.0
            elif max_score > 0:
                c.percentile = round((c.final_score / max_score) * 100.0, 1)
            else:
                c.percentile = 0.0

        return composites

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_domain_penalty(
        self,
        jd_domain: str,
        cand_domain: str,
        jd_conf: float,
        cand_conf: float,
    ) -> float:
        """Return negative penalty (0.0 if no penalty applies)."""
        if not jd_domain or not cand_domain:
            return 0.0
        if jd_conf < 0.4 or cand_conf < 0.4:  # noqa: PLR2004
            return 0.0
        if jd_domain == cand_domain:
            return 0.0
        if jd_domain == "unknown" or cand_domain == "unknown":
            return 0.0

        import json  # noqa: PLC0415
        import os  # noqa: PLC0415
        prox_path = os.path.join(
            os.path.dirname(__file__), "..", "registries", "domain_proximity.json"
        )
        try:
            with open(prox_path) as f:
                prox = json.load(f)
        except OSError:
            return 0.0

        penalties = prox.get("penalties", {})
        return float(penalties.get(jd_domain, {}).get(cand_domain, -50.0))


# ---------------------------------------------------------------------------
# Composite scoring — computed at read time (ADR-07)
# ---------------------------------------------------------------------------

def compute_composite(result: ScoringResult, weights: ScoringWeights) -> float:
    """
    Compute weighted composite score from ScoringResult + ScoringWeights.

    This is a pure function — it NEVER mutates result.
    Called at read time, NOT stored in the database.

    Weight renormalisation: if keyword_score is 0 (no JD keywords), the
    keyword weight is redistributed proportionally to avoid a silent zero-
    score contribution from an unconfigured signal. Same fix as design.md §2.6.
    """
    if result.knockout_result.knocked_out:
        return 0.0

    skill_w = weights.skills
    exp_w = weights.experience
    kw_w = weights.keywords
    edu_w = weights.education

    # Renormalise if keyword signal is absent
    if result.keyword_score == 0.0 and kw_w > 0:
        total_non_kw = skill_w + exp_w + edu_w
        if total_non_kw > 0:
            skill_w = skill_w / total_non_kw
            exp_w = exp_w / total_non_kw
            edu_w = edu_w / total_non_kw
        kw_w = 0.0

    base = (
        result.skill_score * skill_w
        + result.experience_score * exp_w
        + result.keyword_score * kw_w
        + result.education_score * edu_w
    )

    # Optional semantic tiebreaker — additive with renormalised weight
    if result.semantic_score is not None and weights.semantic > 0:
        sem_w = weights.semantic
        total_w = skill_w + exp_w + kw_w + edu_w + sem_w
        if total_w > 0:
            base = (base + result.semantic_score * sem_w) / total_w * (total_w - sem_w + sem_w)

    bonuses = result.project_bonus + result.prestige_bonus + result.cert_bonus
    return round(min(100.0, base + bonuses), 1)
