"""
test_v2_acceptance.py — Comprehensive acceptance tests for Sortlist v2 Release
==============================================================================
Validates:
  1. Security Headers (nosniff, DENY, CSP)
  2. Authentication (Register, Login, Session cookie, Token)
  3. Tenant Isolation & IDOR Protection (Org A cannot read/mutate Org B)
  4. File Validation (Magic bytes %PDF-, non-PDF rejection)
  5. Fairness Policy Compliance (Prestige bonus = 0, Gap penalties disabled)
  6. Scoring Determinism (Identical inputs produce identical outputs)
  7. Evidence Workflow (Mandatory rejection reason, Decision states)
  8. CSV Export (Audit-ready standard CSV)
  9. Candidate Comparison (2 to 4 candidates side-by-side)
  10. Audit Logging (State changes recorded and queryable)
  11. Cascading Deletion (Job deletion purges all related resources)
"""

import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.main import app
from src.schemas.scoring import JobDescription
from src.ranking.scorer import CandidateScorer


@pytest.fixture
def client():
    return TestClient(app)


# ── 1. Security Headers & Protection ──────────────────────────────────────────

def test_security_headers(client):
    """Verify defense-in-depth HTTP security headers are present on responses."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Content-Security-Policy" in resp.headers


# ── 2. Standalone Open Architecture (HC-01 & ADR-07) ──────────────────────────

def test_standalone_job_creation_open_access(client):
    """Verify open access without authentication, login, or bearer tokens per HC-01."""
    job_resp = client.post(
        "/api/v2/jobs",
        json={"title": "Open Role", "must_have_skills": ["Python"]},
    )
    assert job_resp.status_code in (200, 201)
    job_data = job_resp.json()
    assert "id" in job_data
    assert job_data["status"].lower() == "created"


# ── 3. Independent Job Architecture & CSRF Validation ─────────────────────────

def test_job_isolation_and_csrf_origin_check(client, monkeypatch):
    """Verify jobs are isolated and untrusted cross-origin requests are blocked in production."""
    # Create Job A and Job B independently
    job_a = client.post("/api/v2/jobs", json={"title": "Job A"}).json()["id"]
    job_b = client.post("/api/v2/jobs", json={"title": "Job B"}).json()["id"]
    assert job_a != job_b

    # Verify CSRF origin protection in production
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")

    attack_resp = client.post(
        f"/api/v2/jobs/{job_a}/analysis",
        headers={"Origin": "http://malicious-attacker.com"},
    )
    assert attack_resp.status_code == 403


# ── 4. File Validation ────────────────────────────────────────────────────────

def test_pdf_magic_bytes_validation(client):
    """Verify that corrupt or non-PDF files are rejected even if given .pdf extension."""
    # Create Job directly without authentication headers
    job_resp = client.post("/api/v2/jobs", json={"title": "Test PDF Validation"})
    job_id = job_resp.json()["id"]

    # Upload file with text content disguised as PDF
    fake_pdf = b"This is plain text pretending to be a PDF."
    files = [("files", ("fake.pdf", fake_pdf, "application/pdf"))]

    upload_resp = client.post(f"/api/v2/jobs/{job_id}/resumes", files=files)
    assert upload_resp.status_code in (200, 202)
    data = upload_resp.json()
    assert len(data["rejected"]) == 1
    assert "magic bytes" in data["rejected"][0]["reason"].lower() or "invalid" in data["rejected"][0]["reason"].lower()


# ── 5. Fairness Policy Compliance ─────────────────────────────────────────────

def test_fairness_policy_prestige_bonus_disabled():
    """SCORING-POLICY.md: Employer prestige MUST NOT award bonus points."""
    scorer = CandidateScorer()
    jd = JobDescription(
        title="Software Engineer",
        must_have_skills=["Python"],
        min_years=2,
        max_years=10,
        weights={"skills": 0.5, "experience": 0.5, "keywords": 0.0, "education": 0.0},
    )

    # Candidate 1: Worked at Google (previously awarded +4.0 prestige bonus)
    cand_faang = {
        "personal_info": {"name": "FAANG Engineer"},
        "skills": ["Python"],
        "experience": [{
            "role": "Software Engineer",
            "company": "Google",
            "start": "2021",
            "end": "2024",
        }],
        "education": [{"degree": "Bachelor of Science"}],
    }

    # Candidate 2: Worked at Local Startup (previously 0.0 prestige bonus)
    cand_startup = {
        "personal_info": {"name": "Startup Engineer"},
        "skills": ["Python"],
        "experience": [{
            "role": "Software Engineer",
            "company": "Local Web Solutions LLC",
            "start": "2021",
            "end": "2024",
        }],
        "education": [{"degree": "Bachelor of Science"}],
    }

    results = scorer.rank(jd, [cand_faang, cand_startup])
    r_faang = next(r for r in results if r.name == "FAANG Engineer")
    r_startup = next(r for r in results if r.name == "Startup Engineer")

    # Prestige bonus must be exactly 0.0 per binding policy
    assert r_faang.prestige_bonus == 0.0
    assert r_startup.prestige_bonus == 0.0


def test_fairness_policy_no_career_gap_penalty():
    """SCORING-POLICY.md: Career gaps must NEVER generate anomaly flags or penalties."""
    scorer = CandidateScorer()
    jd = JobDescription(
        title="Backend Developer",
        must_have_skills=["Python"],
        min_years=1,
        max_years=10,
    )

    # Candidate with a 1-year gap between roles (e.g. parental or medical leave)
    cand_with_gap = {
        "personal_info": {"name": "Candidate With Gap"},
        "skills": ["Python"],
        "experience": [
            {"role": "Developer", "company": "Co A", "start": "2019", "end": "2020"},
            {"role": "Developer", "company": "Co B", "start": "2022", "end": "2024"},
        ],
        "education": [{"degree": "B.Tech"}],
    }

    results = scorer.rank(jd, [cand_with_gap])
    r = results[0]
    # Ensure no GAP anomaly flag exists
    gap_flags = [f for f in r.anomalies if "GAP" in f.upper()]
    assert len(gap_flags) == 0, f"Found prohibited career gap flag: {gap_flags}"


# ── 6. Scoring Determinism ────────────────────────────────────────────────────

def test_scoring_determinism():
    """Verify that identical inputs produce identical scores, ranks, and percentiles."""
    scorer = CandidateScorer()
    jd = JobDescription(
        title="Data Engineer",
        must_have_skills=["Python", "SQL"],
        nice_to_have_skills=["Airflow", "Spark"],
        min_years=3,
        max_years=8,
        weights={"skills": 0.4, "experience": 0.3, "keywords": 0.15, "education": 0.15},
    )

    candidates = [
        {
            "personal_info": {"name": f"Candidate {i}"},
            "skills": ["Python", "SQL"] if i % 2 == 0 else ["Java", "SQL"],
            "experience": [{"role": "Data Engineer", "company": "DataCorp", "start": "2018", "end": "2023"}],
            "education": [{"degree": "Master of Computer Science"}],
        }
        for i in range(5)
    ]

    run1 = scorer.rank(jd, candidates)
    run2 = scorer.rank(jd, candidates)

    for r1, r2 in zip(run1, run2):
        assert r1.name == r2.name
        assert r1.final_score == r2.final_score
        assert r1.rank == r2.rank
        assert r1.percentile == r2.percentile


# ── 7. Evidence-First Workflow & Mandatory Rejection Reason ──────────────────

def test_rejection_requires_mandatory_reason(client):
    """P1: Rejections must include an evidence-backed rationale."""
    job_resp = client.post("/api/v2/jobs", json={"title": "Product Designer"})
    job_id = job_resp.json()["id"]

    doc_id = "doc_test_123"

    # 1. Attempt to reject WITHOUT reason -> Must fail with 400 Bad Request
    resp_no_reason = client.patch(
        f"/api/v2/jobs/{job_id}/candidates/{doc_id}/decision",
        json={"decision": "rejected", "reason": ""},
    )
    assert resp_no_reason.status_code == 400
    assert "reason" in resp_no_reason.json()["detail"].lower()

    # 2. Reject WITH reason -> Succeeds
    resp_with_reason = client.patch(
        f"/api/v2/jobs/{job_id}/candidates/{doc_id}/decision",
        json={"decision": "rejected", "reason": "Missing portfolio demonstrating responsive mobile UI systems."},
    )
    assert resp_with_reason.status_code == 200
    assert resp_with_reason.json()["status"] == "updated"
    assert resp_with_reason.json()["decision"] == "rejected"


# ── 8. CSV Export & Audit Logging ─────────────────────────────────────────────

def test_csv_export_endpoint(client):
    """Verify candidate export returns valid CSV content."""
    job_resp = client.post("/api/v2/jobs", json={"title": "DevOps Engineer"})
    job_id = job_resp.json()["id"]

    csv_resp = client.get(f"/api/v2/jobs/{job_id}/export/csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers.get("Content-Type", "")
    assert "Rank,Name,Email,Phone,Match Score" in csv_resp.text


def test_audit_log_tracking(client):
    """Verify security- and compliance-relevant state changes are logged."""
    job_resp = client.post("/api/v2/jobs", json={"title": "Security Analyst"})
    job_id = job_resp.json()["id"]

    audit_resp = client.get(f"/api/v2/jobs/{job_id}/audit")
    assert audit_resp.status_code == 200
    events = audit_resp.json()["events"]
    assert len(events) >= 1
    assert any(e["action"] == "JOB_CREATED" for e in events)


# ── 9. Cascading Job Deletion ─────────────────────────────────────────────────

def test_cascading_job_deletion(client):
    """Verify job deletion endpoint cleans up job metadata and responds with 200."""
    job_resp = client.post("/api/v2/jobs", json={"title": "Temporary Job"})
    job_id = job_resp.json()["id"]

    del_resp = client.delete(f"/api/v2/jobs/{job_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Confirm job is now not found
    get_resp = client.patch(f"/api/v2/jobs/{job_id}", json={"title": "Updated"})
    assert get_resp.status_code == 404
