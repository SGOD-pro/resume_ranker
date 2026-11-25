"""
test_golden_20_regression.py — Golden 20-Resume Equivalence Regression Test
==========================================================================
Verifies that the refactored CandidateScorer produces 100% identical
mathematical results (final_score, relevance_score, skill_score,
experience_score, keyword_score, education_score, and knocked_out)
to the baseline golden fixture.
"""

import json
from pathlib import Path

import pytest

from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden_v2_baseline"
GOLDEN_20_PATH = FIXTURES_DIR / "golden_20_resumes.json"


@pytest.fixture
def golden_20_data():
    with open(GOLDEN_20_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_golden_20_scoring_exact_equivalence(golden_20_data):
    """CandidateScorer must produce identical scores and knockout decisions to the golden 20 baseline."""
    job_spec = golden_20_data["metadata"]["job_spec"]
    jd = JobDescription(
        title=job_spec["title"],
        must_have_skills=job_spec["must_have_skills"],
        nice_to_have_skills=job_spec["nice_to_have_skills"],
        min_years=job_spec["min_years"],
        max_years=job_spec["max_years"],
        required_degree=job_spec.get("education_level", "any"),
        preferred_field=job_spec.get("education_field", ""),
        keywords=job_spec["keywords"],
        weights=job_spec["weights"],
    )

    candidates = []
    for profile in golden_20_data["profiles"]:
        fields = profile["extracted_profile"]["fields"]
        candidate_doc = dict(fields)
        candidate_doc["document_id"] = fields.get("name") or profile["filename"]
        candidates.append(candidate_doc)

    scorer = CandidateScorer()
    ranked_candidates = scorer.rank(jd, candidates)
    golden_results = golden_20_data["scoring_results"]

    assert len(ranked_candidates) == len(golden_results) == 20

    for ranked, golden in zip(ranked_candidates, golden_results):
        # 1. Final relevance score exact match
        assert abs(ranked.final_score - golden["final_score"]) < 1e-4, (
            f"Candidate final_score mismatch: computed {ranked.final_score} vs golden {golden['final_score']}"
        )
        assert abs(ranked.relevance_score - golden["relevance_score"]) < 1e-4

        # 2. Component scores exact match
        assert abs(ranked.skill_score - golden["skill_score"]) < 1e-4
        assert abs(ranked.experience_score - golden["experience_score"]) < 1e-4
        assert abs(ranked.keyword_score - golden["keyword_score"]) < 1e-4
        assert abs(ranked.education_score - golden["education_score"]) < 1e-4

        # 3. Knockout state exact match
        assert ranked.knocked_out == golden["knocked_out"]

        # 4. Must-have skill match sets
        assert set(ranked.matched_must_have) == set(golden["matched_must_have"])
        assert set(ranked.missing_must_have) == set(golden["missing_must_have"])
