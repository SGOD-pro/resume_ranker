"""
test_api_end_to_end.py — Benchmark 5: API E2E Validation
===========================================================
Spins up the FastAPI backend via TestClient, exercises the full lifecycle:
    POST /jobs           → create job
    POST /jobs/{id}/resumes → upload resumes
    GET  /jobs/{id}/extract → SSE extraction
    POST /jobs/{id}/score   → score candidates
    GET  /jobs/{id}/results → retrieve results

Verifies all endpoints succeed and debug_jd matches submitted JD.
Returns APIResult with overall reliability percentage.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.benchmark.benchmark_models import APICheck, APIResult


def run(config: Dict[str, Any], verbose: bool = True) -> APIResult:
    """Run API E2E benchmark using FastAPI TestClient."""
    # Import inside function to avoid import-time side effects
    from fastapi.testclient import TestClient
    from src.api.app import app
    from src.config.settings import RESUME_DIR

    result = APIResult()

    if verbose:
        print("\n" + "=" * 78)
        print("  BENCHMARK 5: API END-TO-END VALIDATION")
        print("=" * 78)

    client = TestClient(app)

    # ── 1. POST /jobs ──
    t0 = time.time()
    create_resp = client.post("/jobs", json={
        "title": "Benchmark Test Engineer",
        "department": "Engineering",
        "description": "E2E benchmark test job",
        "must_have_skills": ["Python"],
        "nice_to_have_skills": ["Docker"],
        "min_years": 0,
        "max_years": 99,
        "education_level": "any",
        "education_field": "",
        "keywords": ["test", "benchmark"],
    })
    elapsed = (time.time() - t0) * 1000

    check = APICheck(
        endpoint="POST /jobs",
        method="POST",
        status_code=create_resp.status_code,
        passed=create_resp.status_code == 200,
        response_time_ms=round(elapsed, 1),
    )
    result.checks.append(check)
    result.total += 1
    if check.passed:
        result.passed += 1

    if verbose:
        icon = "✅" if check.passed else "❌"
        print(f"  {icon} POST /jobs → {create_resp.status_code} ({elapsed:.0f}ms)")

    if not check.passed:
        result.accuracy = 0.0
        return result

    job_id = create_resp.json()["id"]

    # ── 2. POST /jobs/{id}/resumes ──
    # Upload 3 test PDFs
    pdfs_to_upload = ["backend.pdf", "fullstack.pdf", "1.pdf"]
    files = []
    for fn in pdfs_to_upload:
        pdf_path = str(RESUME_DIR / fn)
        if os.path.exists(pdf_path):
            files.append(("files", (fn, open(pdf_path, "rb"), "application/pdf")))

    t0 = time.time()
    upload_resp = client.post(f"/jobs/{job_id}/resumes", files=files)
    elapsed = (time.time() - t0) * 1000

    # Close file handles
    for _, (_, fh, _) in files:
        fh.close()

    check = APICheck(
        endpoint=f"POST /jobs/{job_id}/resumes",
        method="POST",
        status_code=upload_resp.status_code,
        passed=upload_resp.status_code == 200,
        response_time_ms=round(elapsed, 1),
    )
    result.checks.append(check)
    result.total += 1
    if check.passed:
        result.passed += 1

    if verbose:
        icon = "✅" if check.passed else "❌"
        print(f"  {icon} POST /jobs/{job_id}/resumes → {upload_resp.status_code} ({elapsed:.0f}ms)")

    # ── 3. GET /jobs/{id}/extract (SSE) ──
    t0 = time.time()
    with client.stream("GET", f"/jobs/{job_id}/extract") as extract_resp:
        status = extract_resp.status_code
        # Read all SSE events
        events = []
        for line in extract_resp.iter_lines():
            if line:
                events.append(line)
    elapsed = (time.time() - t0) * 1000

    check = APICheck(
        endpoint=f"GET /jobs/{job_id}/extract",
        method="GET",
        status_code=status,
        passed=status == 200,
        response_time_ms=round(elapsed, 1),
        detail=f"{len(events)} SSE events",
    )
    result.checks.append(check)
    result.total += 1
    if check.passed:
        result.passed += 1

    if verbose:
        icon = "✅" if check.passed else "❌"
        print(f"  {icon} GET  /jobs/{job_id}/extract → {status} ({elapsed:.0f}ms, {len(events)} events)")

    # ── 4. POST /jobs/{id}/score ──
    t0 = time.time()
    score_resp = client.post(f"/jobs/{job_id}/score", json={
        "weights": {"skills": 40, "experience": 25, "keywords": 20, "education": 15},
    })
    elapsed = (time.time() - t0) * 1000

    check = APICheck(
        endpoint=f"POST /jobs/{job_id}/score",
        method="POST",
        status_code=score_resp.status_code,
        passed=score_resp.status_code == 200,
        response_time_ms=round(elapsed, 1),
    )
    result.checks.append(check)
    result.total += 1
    if check.passed:
        result.passed += 1

    if verbose:
        icon = "✅" if check.passed else "❌"
        print(f"  {icon} POST /jobs/{job_id}/score → {score_resp.status_code} ({elapsed:.0f}ms)")

    # Verify debug_jd matches
    if score_resp.status_code == 200:
        score_data = score_resp.json()
        debug_jd = score_data.get("debug_jd", {})
        jd_title_match = debug_jd.get("title") == "Benchmark Test Engineer"
        jd_skills_match = "Python" in debug_jd.get("must_have_skills", [])
        result.debug_jd_match = jd_title_match and jd_skills_match

        if verbose:
            icon = "✅" if result.debug_jd_match else "❌"
            print(f"  {icon} debug_jd title match: {jd_title_match}, skills match: {jd_skills_match}")

    # ── 5. GET /jobs/{id}/results ──
    t0 = time.time()
    results_resp = client.get(f"/jobs/{job_id}/results")
    elapsed = (time.time() - t0) * 1000

    check = APICheck(
        endpoint=f"GET /jobs/{job_id}/results",
        method="GET",
        status_code=results_resp.status_code,
        passed=results_resp.status_code == 200,
        response_time_ms=round(elapsed, 1),
    )
    result.checks.append(check)
    result.total += 1
    if check.passed:
        result.passed += 1

    if verbose:
        icon = "✅" if check.passed else "❌"
        n_candidates = len(results_resp.json().get("candidates", [])) if results_resp.status_code == 200 else 0
        print(f"  {icon} GET  /jobs/{job_id}/results → {results_resp.status_code} ({elapsed:.0f}ms, {n_candidates} candidates)")

    # ── Compute accuracy ──
    result.accuracy = round(
        (result.passed / result.total * 100.0) if result.total > 0 else 0.0, 1
    )

    if verbose:
        print(f"\n  API Reliability: {result.accuracy}%")
        print(f"    Passed: {result.passed}/{result.total}")
        if not result.debug_jd_match:
            print(f"    ⚠ debug_jd does NOT match submitted JD")

    return result
