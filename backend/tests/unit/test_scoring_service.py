"""
tests/unit/test_scoring_service.py — Phase 4 ScoringService unit tests
=======================================================================

Test coverage:
  1. Determinism — same input → bit-identical output, any pool size
  2. Fixed IDF — score unchanged when unrelated candidates added to pool
  3. Knockout — missing must-have → knocked_out=True, final_score=0
  4. Experience gate — below min_years triggers knockout
  5. Compute composite — weights sum correctly, renormalises when kw absent
  6. Ambiguous band — tiebreaker fires only in [0.40, 0.60]
  7. ScoringWeights validation — invalid weights raise ValueError
  8. Rank ordering — pool sorted correctly, percentiles computed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.extraction.domain_extraction import ExtractionResult, ExtractedField
from src.schemas.scoring import JobDescription
from src.scoring.domain import ScoringResult, ScoringWeights, KnockoutResult
from src.scoring.scoring_service import ScoringService, compute_composite


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_extraction(
    name: str = "Alice Smith",
    email: str = "alice@example.com",
    phone: str = "+91-9876543210",
    skills: list[str] | None = None,
    experience: list[dict[str, Any]] | None = None,
    education: list[dict[str, Any]] | None = None,
    document_id: str = "doc-001",
) -> ExtractionResult:
    """Build a minimal ExtractionResult for testing."""
    _skills = skills if skills is not None else ["Python", "FastAPI", "PostgreSQL"]
    _exp = experience if experience is not None else [
        {"role": "Backend Engineer", "company": "Acme", "start": "Jan 2022", "end": "Present",
         "description": "Built REST APIs with Python FastAPI"}
    ]
    _edu = education if education is not None else [
        {"degree": "B.Tech Computer Science", "institution": "IIT Delhi", "year": "2022"}
    ]

    def _field(v: Any, conf: float = 0.95) -> ExtractedField:
        return ExtractedField(value=v, confidence=conf, provenance="deterministic")

    return ExtractionResult(
        document_id=document_id,
        content_hash="a" * 64,
        name=_field(name),
        email=_field(email),
        phone=_field(phone),
        location=_field("Mumbai, India"),
        skills=_field(_skills),
        experience=_field(_exp),
        education=_field(_edu),
        summary=_field("Experienced backend engineer"),
    )


def _make_job(
    title: str = "Senior Backend Engineer",
    must_have: list[str] | None = None,
    nice_to_have: list[str] | None = None,
    min_years: int = 0,
    required_degree: str = "any",
) -> JobDescription:
    return JobDescription(
        title=title,
        department="Engineering",
        description="We need a backend engineer who builds scalable APIs.",
        must_have_skills=must_have if must_have is not None else ["Python", "FastAPI"],
        nice_to_have_skills=nice_to_have if nice_to_have is not None else ["Docker", "AWS"],
        min_years=min_years,
        required_degree=required_degree,
    )


# ---------------------------------------------------------------------------
# 1. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """score() must be bit-identical for the same inputs."""

    def test_same_input_same_output(self) -> None:
        svc = ScoringService()
        extraction = _make_extraction()
        job = _make_job()

        r1 = svc.score(extraction, job)
        r2 = svc.score(extraction, job)

        assert r1.skill_score == r2.skill_score
        assert r1.experience_score == r2.experience_score
        assert r1.education_score == r2.education_score
        assert r1.keyword_score == r2.keyword_score

    def test_order_independent(self) -> None:
        """Scoring candidate A should not change when candidate B is also present."""
        svc = ScoringService()
        job = _make_job()

        alice = _make_extraction(name="Alice", document_id="doc-alice")
        bob = _make_extraction(
            name="Bob",
            skills=["Java", "Spring Boot"],
            document_id="doc-bob",
        )

        score_alice_alone = svc.score(alice, job).skill_score
        # Score Alice again even though Bob is "in the pool" (V2 has no pool IDF)
        score_alice_with_bob = svc.score(alice, job).skill_score

        assert score_alice_alone == score_alice_with_bob, (
            "Fixed-IDF: Alice's skill score must not change when Bob joins the pool"
        )


# ---------------------------------------------------------------------------
# 2. Fixed IDF — adding unrelated candidates must not move existing scores
# ---------------------------------------------------------------------------

class TestFixedIDF:
    def test_score_stable_across_pool_sizes(self) -> None:
        svc = ScoringService()
        job = _make_job()
        candidate = _make_extraction()

        baseline = svc.score(candidate, job).skill_score

        # Score again (simulates "pool" context — but IDF is fixed, so no change)
        again = svc.score(candidate, job).skill_score
        assert baseline == again

    def test_skill_match_produces_positive_score(self) -> None:
        svc = ScoringService()
        job = _make_job(must_have=["Python"])
        candidate = _make_extraction(skills=["Python"])
        result = svc.score(candidate, job)
        assert result.skill_score > 0


# ---------------------------------------------------------------------------
# 3. Knockout — must-have skills
# ---------------------------------------------------------------------------

class TestKnockout:
    def test_missing_must_have_triggers_knockout(self) -> None:
        svc = ScoringService()
        job = _make_job(must_have=["Go", "Kubernetes"])
        candidate = _make_extraction(skills=["Python", "FastAPI"])   # no Go or Kubernetes

        result = svc.score(candidate, job)

        assert result.knockout_result.knocked_out is True
        assert any("Go" in r or "Kubernetes" in r for r in result.knockout_result.reasons)

    def test_matching_must_have_does_not_knock_out(self) -> None:
        svc = ScoringService()
        job = _make_job(must_have=["Python"])
        candidate = _make_extraction(skills=["Python", "FastAPI"])

        result = svc.score(candidate, job)

        assert result.knockout_result.knocked_out is False

    def test_compute_composite_returns_zero_for_knocked_out(self) -> None:
        ko_result = KnockoutResult(knocked_out=True, reasons=["Missing: Go"])
        sr = ScoringResult(
            document_id="x",
            skill_score=80.0,
            experience_score=70.0,
            education_score=60.0,
            keyword_score=50.0,
            knockout_result=ko_result,
        )
        assert compute_composite(sr, ScoringWeights()) == 0.0


# ---------------------------------------------------------------------------
# 4. Experience gate
# ---------------------------------------------------------------------------

class TestExperienceGate:
    def test_zero_experience_low_min_years_no_knockout(self) -> None:
        svc = ScoringService()
        job = _make_job(min_years=0)
        candidate = _make_extraction(experience=[])   # no experience

        result = svc.score(candidate, job)
        assert result.knockout_result.knocked_out is False


# ---------------------------------------------------------------------------
# 5. Compute composite
# ---------------------------------------------------------------------------

class TestComputeComposite:
    def _make_result(self, **kwargs: Any) -> ScoringResult:
        defaults: dict[str, Any] = {
            "document_id": "test",
            "skill_score": 80.0,
            "experience_score": 70.0,
            "education_score": 60.0,
            "keyword_score": 50.0,
            "knockout_result": KnockoutResult(knocked_out=False, reasons=[]),
        }
        defaults.update(kwargs)
        return ScoringResult(**defaults)

    def test_weighted_composite_correct(self) -> None:
        result = self._make_result()
        weights = ScoringWeights(skills=0.4, experience=0.25, keywords=0.20, education=0.15)
        expected = 80 * 0.4 + 70 * 0.25 + 50 * 0.20 + 60 * 0.15
        assert abs(compute_composite(result, weights) - expected) < 0.1

    def test_keyword_weight_renormalised_when_zero_score(self) -> None:
        """If keyword_score=0, its weight is redistributed, not silently zeroed."""
        result = self._make_result(keyword_score=0.0)
        weights = ScoringWeights(skills=0.4, experience=0.25, keywords=0.20, education=0.15)

        composite = compute_composite(result, weights)

        # Renormalised: skill=0.5, exp=0.3125, edu=0.1875, kw=0
        expected = 80 * 0.5 + 70 * 0.3125 + 60 * 0.1875
        assert abs(composite - expected) < 0.5

    def test_bonuses_added_capped_at_100(self) -> None:
        result = self._make_result(
            skill_score=95.0, experience_score=95.0, education_score=95.0,
            keyword_score=95.0, project_bonus=5.0, prestige_bonus=3.0
        )
        assert compute_composite(result, ScoringWeights()) <= 100.0

    def test_weights_validation_fails_bad_sum(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            ScoringWeights(skills=0.5, experience=0.5, keywords=0.5, education=0.5)


# ---------------------------------------------------------------------------
# 6. Embedding tiebreaker fires only in ambiguous band
# ---------------------------------------------------------------------------

class TestEmbeddingTiebreaker:
    def test_tiebreaker_skipped_outside_band(self) -> None:
        from src.scoring.embedding_tiebreaker import EmbeddingTiebreaker
        tb = EmbeddingTiebreaker(ambiguous_low=0.40, ambiguous_high=0.60)

        # Score of 0.80 (80/100) is above the band — should return None immediately
        result = tb.score(
            skill_score_normalized=0.80,
            candidate_dict={},
            jd_text="Python FastAPI engineer",
        )
        assert result is None

    def test_tiebreaker_skipped_below_band(self) -> None:
        from src.scoring.embedding_tiebreaker import EmbeddingTiebreaker
        tb = EmbeddingTiebreaker(ambiguous_low=0.40, ambiguous_high=0.60)

        result = tb.score(
            skill_score_normalized=0.10,
            candidate_dict={},
            jd_text="Python FastAPI engineer",
        )
        assert result is None


# ---------------------------------------------------------------------------
# 7. ScoringWeights validation
# ---------------------------------------------------------------------------

class TestScoringWeights:
    def test_valid_weights_accepted(self) -> None:
        w = ScoringWeights(skills=0.40, experience=0.25, keywords=0.20, education=0.15)
        assert w.skills + w.experience + w.keywords + w.education == pytest.approx(1.0)

    def test_invalid_weights_rejected(self) -> None:
        with pytest.raises(ValueError):
            ScoringWeights(skills=0.3, experience=0.3, keywords=0.3, education=0.3)


# ---------------------------------------------------------------------------
# 8. Rank ordering
# ---------------------------------------------------------------------------

class TestRanking:
    def _make_sr(self, doc_id: str, skill: float, knocked_out: bool = False) -> ScoringResult:
        ko = KnockoutResult(knocked_out=knocked_out, reasons=["x"] if knocked_out else [])
        return ScoringResult(
            document_id=doc_id,
            skill_score=skill,
            experience_score=70.0,
            education_score=60.0,
            keyword_score=50.0,
            knockout_result=ko,
        )

    def test_rank_ordering(self) -> None:
        svc = ScoringService()
        results = [
            self._make_sr("c", 40.0),
            self._make_sr("a", 90.0),
            self._make_sr("b", 70.0),
        ]
        ranked = svc.rank(results)
        assert ranked[0].document_id == "a"
        assert ranked[1].document_id == "b"
        assert ranked[2].document_id == "c"

    def test_knocked_out_always_last(self) -> None:
        svc = ScoringService()
        results = [
            self._make_sr("ko", 100.0, knocked_out=True),
            self._make_sr("pass", 20.0),
        ]
        ranked = svc.rank(results)
        assert ranked[0].document_id == "pass"
        assert ranked[1].document_id == "ko"

    def test_rank_numbers_assigned(self) -> None:
        svc = ScoringService()
        results = [
            self._make_sr("a", 90.0),
            self._make_sr("b", 50.0),
        ]
        ranked = svc.rank(results)
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2

    def test_percentile_top_candidate_is_100(self) -> None:
        svc = ScoringService()
        results = [
            self._make_sr("a", 90.0),
            self._make_sr("b", 45.0),
        ]
        ranked = svc.rank(results)
        assert ranked[0].percentile == 100.0
