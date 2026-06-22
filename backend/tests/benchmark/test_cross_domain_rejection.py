"""
test_cross_domain_rejection.py — Benchmark 3: Cross-Domain Rejection
=======================================================================
Ensures irrelevant resumes are knocked out or score below threshold (20.0).

Tracks: correct rejections, false positives, false negatives.
Returns RejectionResult with overall accuracy percentage.
"""

from __future__ import annotations

import json
import glob
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription
from src.config.settings import RESUME_DIR
from tests.benchmark.benchmark_models import RejectionCheck, RejectionResult


# ── JD definitions used for cross-domain tests ─────────────────────────────

_JD_REGISTRY: Dict[str, JobDescription] = {
    "Backend Engineer": JobDescription(
        title="Backend Engineer",
        department="Engineering",
        description="Senior backend engineer building scalable microservices",
        must_have_skills=["Python", "SQL"],
        nice_to_have_skills=["Docker", "Kubernetes", "AWS"],
        min_years=2,
        max_years=10,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["microservices", "api", "database", "scalable", "backend"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "Full Stack Developer": JobDescription(
        title="Full Stack Developer",
        department="Engineering",
        description="Full stack developer with backend and frontend experience",
        must_have_skills=["JavaScript", "Python"],
        nice_to_have_skills=["React", "Node.js", "Docker", "AWS"],
        min_years=0,
        max_years=10,
        required_degree="any",
        preferred_field="Computer Science",
        keywords=["fullstack", "frontend", "backend", "api", "web"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "Security Guard": JobDescription(
        title="Security Guard",
        department="Operations",
        must_have_skills=["Surveillance", "Access Control"],
        nice_to_have_skills=["Criminal Justice", "Law Enforcement", "CPR", "First Aid"],
        min_years=1,
        max_years=20,
        required_degree="any",
        keywords=["security", "patrol", "monitor", "safety", "guard"],
        weights={"skills": 0.40, "experience": 0.30, "keywords": 0.20, "education": 0.10},
    ),
    "Junior Web Developer": JobDescription(
        title="Junior Web Developer",
        department="Engineering",
        must_have_skills=["HTML", "CSS", "JavaScript"],
        nice_to_have_skills=["React", "Python", "Django", "Git", "TypeScript"],
        min_years=0,
        max_years=3,
        required_degree="any",
        preferred_field="Computer Science",
        keywords=["web", "frontend", "responsive", "api"],
        weights={"skills": 0.50, "experience": 0.10, "keywords": 0.25, "education": 0.15},
    ),
}

# Rejection threshold: candidate is considered "rejected" if knocked out OR score < 20
REJECTION_THRESHOLD = 20.0


def run(config: Dict[str, Any], verbose: bool = True) -> RejectionResult:
    """Run cross-domain rejection benchmark."""
    rejection_cases = config.get("cross_domain_rejections", [])
    if not rejection_cases:
        return RejectionResult()

    pipe = PDFPipelineV3()
    scorer = CandidateScorer()
    result = RejectionResult()

    # Pre-extract all needed candidates
    needed_files = set(case["candidate_file"] for case in rejection_cases)
    candidate_cache: Dict[str, Dict] = {}
    for fn in needed_files:
        pdf_path = str(RESUME_DIR / fn)
        if os.path.exists(pdf_path):
            try:
                r = pipe.extract(pdf_path)
                fields = json.loads(json.dumps(
                    r.fields,
                    default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
                ))
                fields['_document_id'] = fn
                fields.setdefault('extraction_quality', 0.0)
                candidate_cache[fn] = fields
            except Exception as e:
                result.checks.append(RejectionCheck(
                    name=f"ERROR: {fn}",
                    candidate_file=fn,
                    jd_title="",
                    expected_rejected=True,
                    actually_rejected=False,
                    final_score=0.0,
                    correct=False,
                    detail=str(e),
                ))

    # Also need all candidates for BM25 IDF
    all_pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))
    all_candidates = []
    for pdf in all_pdfs:
        fn = os.path.basename(pdf)
        if fn in candidate_cache:
            all_candidates.append(candidate_cache[fn])
        else:
            try:
                r = pipe.extract(pdf)
                fields = json.loads(json.dumps(
                    r.fields,
                    default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
                ))
                fields['_document_id'] = fn
                fields.setdefault('extraction_quality', 0.0)
                all_candidates.append(fields)
            except Exception:
                pass

    if verbose:
        print("\n" + "=" * 78)
        print("  BENCHMARK 3: CROSS-DOMAIN REJECTION")
        print("=" * 78)

    for case in rejection_cases:
        fn = case["candidate_file"]
        jd_title = case["jd_title"]
        expected_rejected = case.get("expected_rejected", True)

        if fn not in candidate_cache:
            continue

        jd = _JD_REGISTRY.get(jd_title)
        if not jd:
            result.checks.append(RejectionCheck(
                name=case.get("name", ""),
                candidate_file=fn,
                jd_title=jd_title,
                expected_rejected=expected_rejected,
                actually_rejected=False,
                final_score=0.0,
                correct=False,
                detail=f"Unknown JD: {jd_title}",
            ))
            continue

        # Score all candidates (needed for BM25 IDF normalization)
        scored = scorer.rank(jd, all_candidates)

        # Find our target candidate
        target = next((r for r in scored if r.document_id == fn), None)
        if not target:
            continue

        actually_rejected = target.knocked_out or target.final_score < REJECTION_THRESHOLD
        correct = (expected_rejected == actually_rejected)

        check = RejectionCheck(
            name=case.get("name", f"{fn} vs {jd_title}"),
            candidate_file=fn,
            jd_title=jd_title,
            expected_rejected=expected_rejected,
            actually_rejected=actually_rejected,
            final_score=target.final_score,
            correct=correct,
            detail=f"KO={target.knocked_out}, score={target.final_score:.1f}",
        )
        result.checks.append(check)
        result.total += 1

        if correct:
            if expected_rejected:
                result.correct_rejections += 1
            # (no "correct acceptance" counter needed for this benchmark)
        else:
            if expected_rejected and not actually_rejected:
                result.false_negatives += 1  # Should have rejected but didn't
            else:
                result.false_positives += 1  # Wrongly rejected

        if verbose:
            icon = "✅" if correct else "❌"
            print(f"  {icon} {case.get('name', ''):40s} | KO={target.knocked_out:5} | score={target.final_score:5.1f}")

    result.accuracy = round(
        ((result.correct_rejections + (result.total - result.correct_rejections - result.false_positives - result.false_negatives)) / result.total * 100.0)
        if result.total > 0 else 0.0,
        1
    )

    if verbose:
        print(f"\n  Cross-Domain Rejection Accuracy: {result.accuracy}%")
        print(f"    Correct rejections: {result.correct_rejections}")
        print(f"    False positives:    {result.false_positives}")
        print(f"    False negatives:    {result.false_negatives}")

    return result
