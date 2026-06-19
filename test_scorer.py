"""
test_scorer.py — Verify the ranking system with all PDFs using different JDs.
"""

import json
import glob
import os
import sys

sys.path.insert(0, '.')
from pipeline import PDFPipelineV3
from scorer import CandidateScorer, JobDescription, print_rankings


def load_all_candidates():
    """Parse all PDFs and return list of candidate field dicts."""
    pipe = PDFPipelineV3()
    candidates = []
    for pdf in sorted(glob.glob('resume/*.pdf')):
        name = os.path.basename(pdf)
        print(f"  Parsing {name}...", end=' ', flush=True)
        r = pipe.extract(pdf)
        fields = json.loads(json.dumps(
            r.fields, default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
        ))
        fields['_document_id'] = name
        candidates.append(fields)
        print("✓")
    return candidates


def test_jd_1_backend_engineer(scorer, candidates):
    """JD 1: Senior Backend Engineer — targets Data Engineers & Developers."""
    jd = JobDescription(
        title="Senior Backend Engineer",
        department="Engineering",
        must_have_skills=["Python", "SQL"],
        nice_to_have_skills=["Docker", "Kubernetes", "AWS", "MongoDB", "REST", "Java"],
        min_years=3,
        max_years=10,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["microservices", "api", "database", "scalable", "agile",
                   "backend", "server", "deployment"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    )
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_2_digital_marketer(scorer, candidates):
    """JD 2: Digital Marketing Manager — targets marketers."""
    jd = JobDescription(
        title="Digital Marketing Manager",
        department="Marketing",
        must_have_skills=["SEO", "Marketing"],
        nice_to_have_skills=["Social Media", "Email Marketing", "Instagram",
                              "Facebook", "Google Ads", "Analytics"],
        min_years=2,
        max_years=15,
        required_degree="bachelor",
        preferred_field="Marketing",
        keywords=["campaign", "brand", "content", "traffic", "conversion",
                   "strategy", "audience", "engagement"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    )
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_3_security_guard(scorer, candidates):
    """JD 3: Security Guard — targets security professionals."""
    jd = JobDescription(
        title="Security Guard",
        department="Operations",
        must_have_skills=["Surveillance", "Access Control"],
        nice_to_have_skills=["Criminal Justice", "Law Enforcement",
                              "Martial Arts", "CPR", "First Aid"],
        min_years=1,
        max_years=20,
        required_degree="any",
        preferred_field="",
        keywords=["security", "patrol", "monitor", "safety", "guard",
                   "investigation", "compliance"],
        weights={"skills": 0.40, "experience": 0.30, "keywords": 0.20, "education": 0.10},
    )
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_4_fresher_web_dev(scorer, candidates):
    """JD 4: Junior Web Developer (no exp required) — should rank freshers well."""
    jd = JobDescription(
        title="Junior Web Developer",
        department="Engineering",
        must_have_skills=["HTML", "CSS", "JavaScript"],
        nice_to_have_skills=["React", "Python", "Django", "MongoDB",
                              "Git", "TypeScript", "Node.js"],
        min_years=0,
        max_years=3,
        required_degree="any",
        preferred_field="Computer Science",
        keywords=["web", "frontend", "responsive", "api", "github"],
        weights={"skills": 0.50, "experience": 0.10, "keywords": 0.25, "education": 0.15},
    )
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def main():
    print("=" * 72)
    print("  LOADING ALL RESUMES...")
    print("=" * 72)
    candidates = load_all_candidates()
    print(f"\n  Loaded {len(candidates)} candidates.\n")

    scorer = CandidateScorer()

    print("\n" + "▓" * 72)
    print("  TEST 1: Senior Backend Engineer")
    print("▓" * 72)
    test_jd_1_backend_engineer(scorer, candidates)

    print("\n" + "▓" * 72)
    print("  TEST 2: Digital Marketing Manager")
    print("▓" * 72)
    test_jd_2_digital_marketer(scorer, candidates)

    print("\n" + "▓" * 72)
    print("  TEST 3: Security Guard")
    print("▓" * 72)
    test_jd_3_security_guard(scorer, candidates)

    print("\n" + "▓" * 72)
    print("  TEST 4: Junior Web Developer (Fresher-friendly)")
    print("▓" * 72)
    test_jd_4_fresher_web_dev(scorer, candidates)


if __name__ == '__main__':
    main()
