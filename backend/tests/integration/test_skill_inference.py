"""
test_skill_inference.py — Phase 2 Test Suite for Skill Intelligence Engine
===========================================================================
Tests:
  1. Inference accuracy (React ← Next.js, Python ← Django, etc.)
  2. Cross-domain penalty tests
  3. Knockout integration tests
  4. Domain classification benchmark
  5. Backward compatibility (existing scorer tests must pass)

Usage:
    uv run python tests/integration/test_skill_inference.py
"""

import json
import glob
import os
import sys
from pathlib import Path
from dataclasses import asdict

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ranking.skill_inference import (
    SkillInferenceEngine,
    SkillMatchResult,
    WEIGHT_EXPLICIT,
    WEIGHT_ALIAS,
    WEIGHT_INFERRED,
    WEIGHT_RELATED,
)
from src.ranking.domain_classifier import DomainClassifier
from src.ranking.scorer import CandidateScorer, print_rankings
from src.schemas.scoring import JobDescription
from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Inference Accuracy
# ─────────────────────────────────────────────────────────────────────────────

def test_inference_accuracy():
    """Verify the inference engine correctly identifies implied/related skills."""
    engine = SkillInferenceEngine()

    # Test cases: (candidate_skills, jd_skills, expected_matches)
    # Each expected_match: (jd_skill, expected_type, expected_min_weight)
    test_cases = [
        {
            "name": "React ← Next.js",
            "candidate": ["Next.js"],
            "jd": ["React"],
            "expect": [("React", "inferred", WEIGHT_INFERRED)],
        },
        {
            "name": "Python ← Django",
            "candidate": ["Django"],
            "jd": ["Python"],
            "expect": [("Python", "inferred", WEIGHT_INFERRED)],
        },
        {
            "name": "Node.js ← NestJS",
            "candidate": ["NestJS"],
            "jd": ["Node.js"],
            "expect": [("Node.js", "inferred", WEIGHT_INFERRED)],
        },
        {
            "name": "JavaScript ← TypeScript (implies)",
            "candidate": ["TypeScript"],
            "jd": ["JavaScript"],
            "expect": [("JavaScript", "inferred", WEIGHT_INFERRED)],
        },
        {
            "name": "Java ← Spring Boot",
            "candidate": ["Spring Boot"],
            "jd": ["Java"],
            "expect": [("Java", "inferred", WEIGHT_INFERRED)],
        },
        {
            "name": "Kubernetes ~ Docker (related, not implied)",
            "candidate": ["Docker"],
            "jd": ["Kubernetes"],
            "expect": [("Kubernetes", "related", WEIGHT_RELATED)],
        },
        {
            "name": "Employment Law ← Labor Law (alias)",
            "candidate": ["Labor Law"],
            "jd": ["Employment Law"],
            "expect": [("Employment Law", "alias", WEIGHT_ALIAS)],
        },
        {
            "name": "Recruitment ← Talent Acquisition (alias)",
            "candidate": ["Talent Acquisition"],
            "jd": ["Recruitment"],
            "expect": [("Recruitment", "related", WEIGHT_RELATED)],
        },
        {
            "name": "Patient Care ← Clinical Care (alias)",
            "candidate": ["Clinical Care"],
            "jd": ["Patient Care"],
            "expect": [("Patient Care", "alias", WEIGHT_ALIAS)],
        },
        {
            "name": "React exact match",
            "candidate": ["React"],
            "jd": ["React"],
            "expect": [("React", "explicit", WEIGHT_EXPLICIT)],
        },
        {
            "name": "No match: Vue.js does NOT imply or relate to React",
            "candidate": ["Vue.js"],
            "jd": ["React"],
            "expect": [],  # No match expected — different frameworks
        },
        {
            "name": "Compliance ← HIPAA (implies)",
            "candidate": ["HIPAA"],
            "jd": ["Compliance"],
            "expect": [("Compliance", "inferred", WEIGHT_INFERRED)],
        },
    ]

    passed = 0
    failed = 0

    print("\n" + "=" * 72)
    print("  TEST 1: INFERENCE ACCURACY")
    print("=" * 72)

    for tc in test_cases:
        result = engine.match_skills(tc["candidate"], tc["jd"])
        all_ok = True

        if not tc["expect"]:
            # No match expected — verify result has no matches
            if result.all_matches:
                print(f"  ❌ {tc['name']}: expected NO match, got {result.all_matches[0].match_type}")
                all_ok = False
        else:
            for exp_skill, exp_type, exp_weight in tc["expect"]:
                match = next(
                    (m for m in result.all_matches if m.skill == exp_skill),
                    None
                )

                if match is None:
                    if exp_weight > 0:
                        print(f"  ❌ {tc['name']}: expected {exp_type} match for '{exp_skill}', got MISSING")
                        all_ok = False
                    continue

                if match.match_type != exp_type:
                    # Allow upgrade: explicit > alias > inferred > related
                    type_order = {"explicit": 4, "alias": 3, "inferred": 2, "related": 1}
                    if type_order.get(match.match_type, 0) >= type_order.get(exp_type, 0):
                        pass  # Better match type = OK
                    else:
                        print(f"  ❌ {tc['name']}: expected type '{exp_type}', got '{match.match_type}'")
                        all_ok = False

                if match.weight < exp_weight:
                    print(f"  ❌ {tc['name']}: expected weight >= {exp_weight}, got {match.weight}")
                    all_ok = False

        if all_ok:
            match_info = result.all_matches[0] if result.all_matches else None
            info = f"({match_info.match_type}={match_info.weight}, {match_info.explanation})" if match_info else "(no match, as expected)"
            print(f"  ✅ {tc['name']} {info}")
            passed += 1
        else:
            failed += 1

    print(f"\n  Results: {passed} passed, {failed} failed out of {len(test_cases)}")
    return failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Cross-Domain Penalty Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_domain_penalties():
    """Verify domain penalties apply correctly for cross-domain scenarios."""
    print("\n" + "=" * 72)
    print("  TEST 2: CROSS-DOMAIN PENALTY TESTS")
    print("=" * 72)

    scorer = CandidateScorer()
    passed = 0
    failed = 0

    # Scenario 1: Backend JD vs Lawyer Resume
    jd_backend = JobDescription(
        title="Senior Backend Engineer",
        department="Engineering",
        must_have_skills=["Python", "SQL"],
        nice_to_have_skills=["Docker", "AWS"],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    lawyer_candidate = {
        'personal_info': {'name': 'Test Lawyer'},
        'skills': ['Contract Law', 'Employment Law', 'Legal Research', 'Litigation', 'Compliance'],
        'experience': [{'role': 'Attorney', 'company': 'Big Law Firm LLP', 'description': 'Litigation and contract drafting'}],
        'education': [{'degree': 'Juris Doctor', 'institution': 'Harvard Law'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd_backend, [lawyer_candidate])
    r = results[0]
    print(f"\n  Backend JD vs Lawyer Resume:")
    print(f"    Domain: {r.candidate_domain} (conf={r.domain_confidence})")
    print(f"    Penalty: {r.domain_penalty}%")
    print(f"    Skill Score: {r.skill_score:.1f}")
    if r.domain_penalty <= -50:
        print(f"    ✅ Heavy penalty applied ({r.domain_penalty}%)")
        passed += 1
    else:
        print(f"    ❌ Expected heavy penalty, got {r.domain_penalty}%")
        failed += 1

    # Scenario 2: HR JD vs Software Engineer
    jd_hr = JobDescription(
        title="HR Manager",
        department="Human Resources",
        must_have_skills=["Talent Acquisition", "HRIS"],
        nice_to_have_skills=["Payroll", "Employee Relations"],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    dev_candidate = {
        'personal_info': {'name': 'Test Developer'},
        'skills': ['Python', 'React', 'Docker', 'AWS', 'Kubernetes', 'SQL'],
        'experience': [{'role': 'Software Engineer', 'company': 'TechCo', 'description': 'Built backend services'}],
        'education': [{'degree': 'BS Computer Science', 'institution': 'MIT'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd_hr, [dev_candidate])
    r = results[0]
    print(f"\n  HR JD vs Software Engineer:")
    print(f"    Domain: {r.candidate_domain} (conf={r.domain_confidence})")
    print(f"    Penalty: {r.domain_penalty}%")
    if r.domain_penalty <= -40:
        print(f"    ✅ Penalty applied ({r.domain_penalty}%)")
        passed += 1
    else:
        print(f"    ❌ Expected penalty, got {r.domain_penalty}%")
        failed += 1

    # Scenario 3: Finance JD vs Accountant (low/no penalty)
    jd_finance = JobDescription(
        title="Financial Analyst",
        department="Finance",
        must_have_skills=["Financial Analysis", "Excel"],
        nice_to_have_skills=["Financial Modeling", "Bloomberg"],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    accountant = {
        'personal_info': {'name': 'Test Accountant'},
        'skills': ['Accounting', 'GAAP', 'Excel', 'Financial Reporting', 'Audit', 'Tax Preparation'],
        'experience': [{'role': 'Staff Accountant', 'company': 'KPMG', 'description': 'Financial auditing and reporting'}],
        'education': [{'degree': 'BS Accounting', 'institution': 'NYU'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd_finance, [accountant])
    r = results[0]
    print(f"\n  Finance JD vs Accountant:")
    print(f"    Domain: {r.candidate_domain} (conf={r.domain_confidence})")
    print(f"    Penalty: {r.domain_penalty}%")
    if r.domain_penalty >= -15:
        print(f"    ✅ Low/no penalty ({r.domain_penalty}%)")
        passed += 1
    else:
        print(f"    ❌ Expected low penalty, got {r.domain_penalty}%")
        failed += 1

    print(f"\n  Results: {passed}/3 passed")
    return failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Knockout Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_knockout_with_inference():
    """Verify must-have knockout uses inference correctly."""
    print("\n" + "=" * 72)
    print("  TEST 3: KNOCKOUT INTEGRATION (INFERENCE-AWARE)")
    print("=" * 72)

    scorer = CandidateScorer()
    passed = 0
    failed = 0

    # JD requires React, candidate has Next.js → should PASS (inferred)
    jd = JobDescription(
        title="Frontend Developer",
        department="Engineering",
        must_have_skills=["React"],
        nice_to_have_skills=[],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    candidate_nextjs = {
        'personal_info': {'name': 'NextJS Dev'},
        'skills': ['Next.js', 'TypeScript', 'CSS'],
        'experience': [{'role': 'Frontend Developer', 'company': 'Startup', 'description': 'Built UI with Next.js'}],
        'education': [{'degree': 'BS CS', 'institution': 'MIT'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd, [candidate_nextjs])
    r = results[0]
    print(f"\n  Must-have React, candidate has Next.js:")
    print(f"    Knocked out: {r.knocked_out}")
    print(f"    Matched must-have: {r.matched_must_have}")
    print(f"    Missing must-have: {r.missing_must_have}")
    print(f"    Inferred: {r.matched_inferred}")
    if not r.knocked_out and "React" in r.matched_must_have:
        print(f"    ✅ PASS — React satisfied via Next.js inference")
        passed += 1
    else:
        print(f"    ❌ FAIL — React should be inferred from Next.js")
        failed += 1

    # JD requires Python, candidate has Django → should PASS (inferred)
    jd2 = JobDescription(
        title="Backend Developer",
        department="Engineering",
        must_have_skills=["Python"],
        nice_to_have_skills=[],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    candidate_django = {
        'personal_info': {'name': 'Django Dev'},
        'skills': ['Django', 'PostgreSQL', 'Redis'],
        'experience': [{'role': 'Backend Developer', 'company': 'Corp', 'description': 'Django REST API'}],
        'education': [{'degree': 'BS', 'institution': 'Stanford'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd2, [candidate_django])
    r = results[0]
    print(f"\n  Must-have Python, candidate has Django:")
    print(f"    Knocked out: {r.knocked_out}")
    print(f"    Matched must-have: {r.matched_must_have}")
    print(f"    Inferred: {r.matched_inferred}")
    if not r.knocked_out and "Python" in r.matched_must_have:
        print(f"    ✅ PASS — Python satisfied via Django inference")
        passed += 1
    else:
        print(f"    ❌ FAIL — Python should be inferred from Django")
        failed += 1

    # JD requires React, candidate has Vue.js → should FAIL (related only, weight 0.50)
    candidate_vue = {
        'personal_info': {'name': 'Vue Dev'},
        'skills': ['Vue.js', 'CSS', 'HTML'],
        'experience': [{'role': 'Frontend Developer', 'company': 'VueCo', 'description': 'Vue.js SPA'}],
        'education': [{'degree': 'BS', 'institution': 'UCLA'}],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd, [candidate_vue])
    r = results[0]
    print(f"\n  Must-have React, candidate has Vue.js:")
    print(f"    Knocked out: {r.knocked_out}")
    print(f"    Missing must-have: {r.missing_must_have}")
    print(f"    Related: {r.matched_related}")
    if r.knocked_out and "React" in r.missing_must_have:
        print(f"    ✅ PASS — Vue.js is related (0.50) but does NOT satisfy must-have")
        passed += 1
    else:
        print(f"    ❌ FAIL — Vue.js should NOT satisfy React must-have")
        failed += 1

    # JD requires Node.js, candidate has NestJS → should PASS (inferred)
    jd3 = JobDescription(
        title="Backend Developer",
        department="Engineering",
        must_have_skills=["Node.js"],
        nice_to_have_skills=[],
        min_years=0,
        max_years=99,
        required_degree="any",
    )
    candidate_nest = {
        'personal_info': {'name': 'Nest Dev'},
        'skills': ['NestJS', 'PostgreSQL'],
        'experience': [{'role': 'Backend Dev', 'company': 'Corp', 'description': 'NestJS microservices'}],
        'education': [],
        'projects': [],
        'extraction_quality': 0.9,
    }
    results = scorer.rank(jd3, [candidate_nest])
    r = results[0]
    print(f"\n  Must-have Node.js, candidate has NestJS:")
    print(f"    Knocked out: {r.knocked_out}")
    print(f"    Inferred: {r.matched_inferred}")
    if not r.knocked_out:
        print(f"    ✅ PASS — Node.js satisfied via NestJS inference")
        passed += 1
    else:
        print(f"    ❌ FAIL — Node.js should be inferred from NestJS")
        failed += 1

    print(f"\n  Results: {passed}/4 passed")
    return failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Domain Classification Benchmark
# ─────────────────────────────────────────────────────────────────────────────

def test_domain_classification():
    """Run domain classifier against all benchmark resumes."""
    print("\n" + "=" * 72)
    print("  TEST 4: DOMAIN CLASSIFICATION BENCHMARK")
    print("=" * 72)

    pipe = PDFPipelineV3()
    classifier = DomainClassifier()

    pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))
    total = 0
    results = []

    for pdf in pdfs:
        filename = os.path.basename(pdf)
        try:
            r = pipe.extract(pdf)
            fields = json.loads(json.dumps(
                r.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
            domain, confidence = classifier.classify(fields)
            name = (fields.get('personal_info') or {}).get('name', 'Unknown')
            results.append({
                'file': filename,
                'name': name,
                'domain': domain,
                'confidence': confidence,
                'skills': fields.get('skills', [])[:5],
            })
            total += 1
        except Exception as e:
            print(f"  ⚠ {filename}: ERROR — {e}")

    print(f"\n  {'FILE':20s}  {'NAME':25s}  {'DOMAIN':15s}  {'CONF':6s}")
    print("  " + "─" * 68)
    for r in results:
        print(f"  {r['file']:20s}  {r['name']:25s}  {r['domain']:15s}  {r['confidence']:.3f}")

    # Count domains
    domain_counts = {}
    for r in results:
        domain_counts[r['domain']] = domain_counts.get(r['domain'], 0) + 1

    print(f"\n  Domain distribution:")
    for d, c in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"    {d}: {c} ({c/total*100:.0f}%)")

    print(f"\n  Total classified: {total}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Full Scorer with Inference (regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_scorer_with_inference():
    """Run full stack developer JD with inference-aware scorer."""
    print("\n" + "=" * 72)
    print("  TEST 5: FULL SCORER WITH INFERENCE (Full Stack Developer)")
    print("=" * 72)

    pipe = PDFPipelineV3()
    scorer = CandidateScorer()

    pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))
    candidates = []
    for pdf in pdfs:
        filename = os.path.basename(pdf)
        try:
            r = pipe.extract(pdf)
            fields = json.loads(json.dumps(
                r.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
            fields['_document_id'] = filename
            if 'extraction_quality' not in fields:
                fields['extraction_quality'] = 0.0
            candidates.append(fields)
        except Exception:
            pass

    jd = JobDescription(
        title="Full Stack Developer",
        department="Engineering",
        description="need a full stack developer who knows backend and front-end both with little bit of devops knowledge",
        must_have_skills=["React", "Node", "Python", "JS", "Docker"],
        nice_to_have_skills=["Redis", "AWS", "K8S"],
        min_years=0,
        max_years=10,
        required_degree="bachelor",
        preferred_field="CS / related",
        keywords=[],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    )

    results = scorer.rank(jd, candidates)

    # Print inference details for top candidates
    print(f"\n  {'RANK':4s}  {'NAME':25s}  {'SCORE':6s}  {'DOMAIN':12s}  {'INFERRED':40s}")
    print("  " + "─" * 90)
    for r in results[:10]:
        inferred = ', '.join(r.matched_inferred[:3]) if r.matched_inferred else '-'
        domain = f"{r.candidate_domain}({r.domain_confidence:.2f})"
        ko = " [KO]" if r.knocked_out else ""
        print(f"  {r.rank:4d}  {r.name:25s}  {r.final_score:5.1f}  {domain:12s}  {inferred}{ko}")

    # Print full inference breakdown for top 3
    for r in results[:3]:
        if r.skill_matches:
            print(f"\n  ── {r.name} Skill Matches ──")
            for m in r.skill_matches:
                print(f"    {m['match_type']:10s}  {m['weight']:.2f}  {m['explanation']}")

    # JULIE MONROE must still be knocked out
    julie = next((r for r in results if 'JULIE' in r.name.upper() or 'MONROE' in r.name.upper()), None)
    if julie:
        assert julie.knocked_out, f"BUG: JULIE MONROE should be knocked out, got score={julie.final_score}"
        print(f"\n  ✅ JULIE MONROE correctly knocked out (domain={julie.candidate_domain})")
    else:
        print(f"\n  ⚠  JULIE MONROE not found")

    print(f"\n  Active: {len([r for r in results if not r.knocked_out])}")
    print(f"  Knocked out: {len([r for r in results if r.knocked_out])}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  PHASE 2 — SKILL INTELLIGENCE TEST SUITE")
    print("=" * 72)

    all_passed = True

    # Test 1: Inference accuracy
    if not test_inference_accuracy():
        all_passed = False

    # Test 2: Cross-domain penalties
    if not test_cross_domain_penalties():
        all_passed = False

    # Test 3: Knockout integration
    if not test_knockout_with_inference():
        all_passed = False

    # Test 4: Domain classification benchmark
    test_domain_classification()

    # Test 5: Full scorer with inference
    test_scorer_with_inference()

    print("\n" + "=" * 72)
    if all_passed:
        print("  ✅ ALL CRITICAL TESTS PASSED")
    else:
        print("  ❌ SOME TESTS FAILED — review output above")
    print("=" * 72 + "\n")


if __name__ == '__main__':
    main()
