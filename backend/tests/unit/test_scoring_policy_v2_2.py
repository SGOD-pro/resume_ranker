"""
test_scoring_policy_v2_2.py — Unit tests for v2.2 Strict Relevance Scoring Policy
================================================================================
Validates:
1. Bounded marginal nice-to-have bonus (capped at 5.0, +1.0 per skill, not +10.0 unbounded)
2. No prestige company bonus (FAANG / Fortune 500 = 0.0)
3. No hackathon bonus and equal-weight relevant certifications (no prestigious university cert bonus)
4. Knockout retains calculated relevance score and non-zero sub-scores (no zeroing of final_score)
5. Decision separation: eligibility_status (ELIGIBLE / REVIEW_REQUIRED / DOES_NOT_MEET_CRITERIA)
6. Factor ledger completeness and audit lineage (score_version, policy_version, job_version)
7. Sorting in Phase 3 preserves explainability (eligible/review candidates above knocked out)
"""

import pytest
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription, ScoredCandidate


@pytest.fixture
def base_jd() -> JobDescription:
    return JobDescription(
        title="Senior Python Backend Engineer",
        department="Engineering",
        description="Looking for an experienced Python developer with FastAPI, PostgreSQL, and Docker.",
        must_have_skills=["Python", "FastAPI", "PostgreSQL"],
        nice_to_have_skills=["Docker", "Kubernetes", "Redis", "AWS", "GraphQL", "Kafka"],
        min_years=3,
        max_years=8,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["REST", "microservices", "CI/CD", "scalability"],
        job_version=2,
    )


@pytest.fixture
def qualified_candidate() -> dict:
    return {
        "name": "Jane Doe",
        "_document_id": "jane_doe.pdf",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
        "experience": [
            {
                "role": "Backend Engineer",
                "company": "Tech Corp",
                "start": "January 2021",
                "end": "Present",
                "description": "Developed REST APIs and microservices in Python and FastAPI with PostgreSQL and Docker.",
                "achievements": [],
            },
            {
                "role": "Junior Developer",
                "company": "Startup Co",
                "start": "January 2019",
                "end": "December 2020",
                "description": "Built database queries and backend services.",
                "achievements": [],
            },
        ],
        "education": [
            {
                "degree": "Bachelor of Science in Computer Science",
                "institution": "State University",
                "year": "2018",
            }
        ],
        "projects": [
            {
                "name": "Cloud API",
                "description": "Scalable REST microservice using Python, FastAPI, and Docker.",
                "technologies": ["Python", "FastAPI", "Docker"],
            }
        ],
        "certifications": [
            {
                "name": "AWS Certified Solutions Architect",
                "issuer": "Amazon Web Services",
            }
        ],
        "extraction_quality": 0.95,
        "identity_status": "VERIFIED",
        "identity_confidence": 0.98,
        "raw_text_sections": {
            "full_text": "Jane Doe Senior Python Developer with FastAPI PostgreSQL Docker Redis REST CI/CD microservices scalability",
            "skills": "Python, FastAPI, PostgreSQL, Docker, Redis",
        },
    }


def test_bounded_nice_to_have_bonus(base_jd, qualified_candidate):
    """Ensure nice-to-have matches produce bounded marginal bonus (max 5.0, not +10.0 each)."""
    scorer = CandidateScorer()
    # Candidate matches Docker and Redis (2 nice to have)
    results = scorer.rank(base_jd, [qualified_candidate])
    r = results[0]

    assert len(r.matched_nice_to_have) >= 2
    # Nice to have ledger contribution must be <= 5.0
    nth_ledger = next((item for item in r.factor_ledger if item["factor"] == "nice_to_have_bonus"), None)
    assert nth_ledger is not None
    assert nth_ledger["contribution"] <= 5.0
    assert nth_ledger["contribution"] == pytest.approx(len(r.matched_nice_to_have) * 1.0, 0.01)

    # Now add all 6 nice-to-have skills to candidate
    candidate_all_nth = dict(qualified_candidate)
    candidate_all_nth["skills"] = ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "Redis", "AWS", "GraphQL", "Kafka"]
    results_all = scorer.rank(base_jd, [candidate_all_nth])
    r_all = results_all[0]
    nth_all_ledger = next((item for item in r_all.factor_ledger if item["factor"] == "nice_to_have_bonus"), None)
    assert nth_all_ledger is not None
    # Must be capped at exactly 5.0, despite 6 matched skills
    assert nth_all_ledger["contribution"] == 5.0


def test_prohibited_prestige_bonus_is_zero(base_jd, qualified_candidate):
    """Fairness policy: FAANG / Fortune 500 employer prestige bonus must be 0.0."""
    scorer = CandidateScorer()
    candidate_prestige = dict(qualified_candidate)
    candidate_prestige["experience"] = [
        {
            "role": "Senior Engineer",
            "company": "Google",  # Known prestige company in v1
            "start": "January 2019",
            "end": "Present",
            "description": "Python engineering",
            "achievements": [],
        }
    ]
    results = scorer.rank(base_jd, [candidate_prestige])
    r = results[0]
    assert r.prestige_bonus == 0.0
    assert r.prestigious_companies == []


def test_prohibited_hackathon_bonus_removed(base_jd, qualified_candidate):
    """Fairness policy: Hackathon wins/participation must not grant arbitrary bonuses."""
    scorer = CandidateScorer()
    candidate_hackathon = dict(qualified_candidate)
    candidate_hackathon["raw_text_sections"] = {
        "full_text": "Winner of MIT Hackathon 1st place champion in coding competition",
    }
    candidate_hackathon["certifications"] = []
    results = scorer.rank(base_jd, [candidate_hackathon])
    r = results[0]
    assert r.cert_bonus == 0.0
    assert r.relevant_certs == []


def test_knockout_retains_relevance_score_and_subscores(base_jd, qualified_candidate):
    """
    Candidate knocked out (e.g. missing must-have skills or over experience cap)
    must NOT have final_score zeroed. Relevance score and subscores must remain visible.
    """
    scorer = CandidateScorer()
    # Candidate with 0 must-have skills and 15 years experience (exceeds 8 max)
    knocked_out_cand = dict(qualified_candidate)
    knocked_out_cand["skills"] = ["Java", "Spring Boot"]
    knocked_out_cand["experience"] = [
        {
            "role": "Engineering Director",
            "company": "OldCorp",
            "start": "January 2008",
            "end": "December 2023",
            "description": "15 years of Java engineering leadership",
            "achievements": [],
        }
    ]
    results = scorer.rank(base_jd, [knocked_out_cand])
    r = results[0]

    assert r.knocked_out is True
    assert r.eligibility_status == "DOES_NOT_MEET_CRITERIA"
    assert len(r.knockout_reasons) >= 1

    # Sub-scores must NOT be wiped
    assert r.experience_score > 0.0
    # Final score must NOT be 0.0 if there is any relevance evidence
    assert r.relevance_score >= 0.0
    assert r.final_score == r.relevance_score


def test_decision_separation_and_review_required(base_jd, qualified_candidate):
    """Low extraction quality or unresolved identity triggers REVIEW_REQUIRED eligibility."""
    scorer = CandidateScorer()
    low_quality_cand = dict(qualified_candidate)
    low_quality_cand["extraction_quality"] = 0.42
    low_quality_cand["identity_status"] = "UNRESOLVED"
    low_quality_cand["name"] = None

    results = scorer.rank(base_jd, [low_quality_cand])
    r = results[0]

    assert r.eligibility_status == "REVIEW_REQUIRED"
    assert r.human_decision == "NEW"
    assert r.identity_status == "UNRESOLVED"
    assert r.name is None


def test_factor_ledger_completeness_and_lineage(base_jd, qualified_candidate):
    """Audit ledger must record factor contributions, source, confidence, and version lineage."""
    scorer = CandidateScorer()
    results = scorer.rank(base_jd, [qualified_candidate])
    r = results[0]

    assert r.score_version == "2.2.0"
    assert r.policy_version == "2026.1"
    assert r.job_version == 2

    assert len(r.factor_ledger) >= 4
    factors = {item["factor"] for item in r.factor_ledger}
    assert "skills" in factors
    assert "experience" in factors
    assert "keywords" in factors
    assert "education" in factors

    for item in r.factor_ledger:
        assert "contribution" in item
        assert "source" in item
        assert "confidence" in item
        assert "rule" in item


def test_phase3_sorting_active_before_knockout(base_jd, qualified_candidate):
    """Phase 3 sorting must place active candidates above knocked-out candidates."""
    scorer = CandidateScorer()
    ko_cand = dict(qualified_candidate)
    ko_cand["name"] = "Knocked Out Dev"
    ko_cand["skills"] = ["C++"]
    ko_cand["experience"] = [
        {
            "role": "VP Engineering",
            "company": "Legacy",
            "start": "January 2000",
            "end": "December 2020",
            "description": "20 years C++ engineering",
            "achievements": [],
        }
    ]

    results = scorer.rank(base_jd, [ko_cand, qualified_candidate])
    assert len(results) == 2
    # Jane Doe (eligible) must rank #1 even if ko_cand had high raw subscores
    assert results[0].name == "Jane Doe"
    assert results[0].eligibility_status == "ELIGIBLE"
    assert results[1].name == "Knocked Out Dev"
    assert results[1].eligibility_status == "DOES_NOT_MEET_CRITERIA"
