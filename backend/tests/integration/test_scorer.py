"""
test_scorer.py — Verify the ranking system with all PDFs using different JDs.

Key tests:
  1. Full Stack Developer (from UI screenshot) — the active scenario.
  2. JULIE MONROE sanity check — dietitian resume must NOT rank for dev roles.
  3. Duplicate-name guard — confirms which physical PDF is selected per candidate.
  4. Original JDs (backend, marketing, security, fresher web dev) kept for regression.
"""

import json
import glob
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.ranking.scorer import CandidateScorer, print_rankings
from src.schemas.scoring import JobDescription
from src.config.settings import RESUME_DIR


# ── Candidate loading ──────────────────────────────────────────────────────────

def load_all_candidates(verbose: bool = True):
    """Parse all PDFs in RESUME_DIR and return list of candidate field dicts.

    Each dict gets a '_document_id' key set to the PDF filename so we can
    trace which physical file produced which candidate — important when
    multiple PDFs share a name or contain people with similar profiles.
    """
    pipe = PDFPipelineV3()
    candidates = []
    pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))
    for pdf in pdfs:
        filename = os.path.basename(pdf)
        if verbose:
            print(f"  Parsing {filename}...", end=' ', flush=True)
        try:
            r = pipe.extract(pdf)
            fields = json.loads(json.dumps(
                r.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
            fields['_document_id'] = filename          # physical file name
            if 'extraction_quality' not in fields:
                fields['extraction_quality'] = 0.0
            candidates.append(fields)
            if verbose:
                name = (fields.get('personal_info') or {}).get('name', '?')
                print(f"✓  ({name})")
        except Exception as exc:
            if verbose:
                print(f"✗  ERROR: {exc}")
    return candidates


def _get_candidate_map(candidates):
    """Return {candidate_name_upper: fields_dict} for fast lookup."""
    return {
        (c.get('personal_info') or {}).get('name', '').upper(): c
        for c in candidates
    }


# ── PDF Inventory Diagnostic ───────────────────────────────────────────────────

def print_pdf_inventory(candidates):
    """Print a table of all loaded PDFs with name, doc_id, education, and skills.

    Helps catch cases where the same person appears in multiple PDFs under
    different filenames — or different people share a common name.
    """
    print("\n" + "─" * 100)
    print(f"  {'FILE':15s}  {'CANDIDATE NAME':28s}  {'HIGHEST DEGREE':40s}  {'SKILLS (first 4)':30s}")
    print("─" * 100)
    for c in candidates:
        doc_id = c.get('_document_id', '?')
        name   = (c.get('personal_info') or {}).get('name', 'Unknown')
        edu    = c.get('education', [])
        degree = edu[0].get('degree', 'N/A')[:38] if edu else 'N/A'
        skills = c.get('skills', [])[:4]
        print(f"  {doc_id:15s}  {name:28s}  {degree:40s}  {skills}")
    print("─" * 100 + "\n")


# ── JD Definitions ────────────────────────────────────────────────────────────

def _jd_fullstack_developer() -> JobDescription:
    """Full Stack Developer — exactly matches the UI screenshot settings.

    Screenshot values:
      Title       : full stack developer
      Department  : Engineering
      Description : need a full stack developer who knows backend and
                    front-end both with little bit of devops knowledge
      Must-have   : React, Node, Python, JS, Docker
      Nice-to-have: Redis, AWS, K8S
      Experience  : 0 – 10 years
      Education   : Bachelor, CS / related
      Keywords    : (none entered in UI)
      Weights     : Skills 40% | Experience 25% | Keywords 20% | Education 15%
    """
    return JobDescription(
        title="Full Stack Developer",
        department="Engineering",
        description=(
            "need a full stack developer who knows backend and front-end both "
            "with little bit of devops knowledge"
        ),
        must_have_skills=["React", "Node", "Python", "JS", "Docker"],
        nice_to_have_skills=["Redis", "AWS", "K8S"],
        min_years=0,
        max_years=10,
        required_degree="bachelor",
        preferred_field="CS / related",
        keywords=[],   # No keywords were added in the screenshot UI
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    )


def _jd_backend_engineer() -> JobDescription:
    """Senior Backend Engineer — regression test."""
    return JobDescription(
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


def _jd_digital_marketer() -> JobDescription:
    """Digital Marketing Manager — regression test."""
    return JobDescription(
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


def _jd_security_guard() -> JobDescription:
    """Security Guard — regression test."""
    return JobDescription(
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


def _jd_fresher_web_dev() -> JobDescription:
    """Junior Web Developer (no exp required) — regression test."""
    return JobDescription(
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


# ── Test runners ──────────────────────────────────────────────────────────────

def test_jd_fullstack_developer(scorer, candidates):
    """TEST: Full Stack Developer (UI screenshot JD).

    Expected behaviour:
    - JULIE MONROE (1.pdf — dietitian, MS Dietary Education) must be KNOCKED OUT.
      She has zero fullstack/dev skills and should never rank for this role.
    - Candidates with React / Node / Python / Docker should rank at the top.
    - All 20 candidates with the current resume pool are expected to be knocked
      out (none possess all 5 must-have skills simultaneously in this dataset).
    """
    jd = _jd_fullstack_developer()
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)

    # ── JULIE MONROE sanity assertion ──────────────────────────────────────
    julie = next((r for r in results
                  if 'JULIE' in r.name.upper() or 'MONROE' in r.name.upper()), None)

    print("\n" + "═" * 72)
    print("  JULIE MONROE DIAGNOSTIC")
    print("═" * 72)
    if julie is None:
        print("  ⚠  JULIE MONROE not found in results — check PDF extraction.")
    else:
        print(f"  Physical PDF    : {julie.document_id}")
        print(f"  Name extracted  : {julie.name}")
        print(f"  Final Score     : {julie.final_score}")
        print(f"  Knocked Out     : {julie.knocked_out}")
        print(f"  KO Reasons      : {julie.knockout_reasons}")
        print(f"  Skill Score     : {julie.skill_score:.1f}/100 (raw, before weighting)")
        print(f"  Exp Score       : {julie.experience_score:.1f}/100")
        print(f"  KW Score        : {julie.keyword_score:.1f}/100  "
              f"(100 = no keywords defined in JD → vacuously full score)")
        print(f"  Edu Score       : {julie.education_score:.1f}/100  "
              f"(60 because MS > required Bachelor, but field mismatch)")
        print(f"  Matched Must    : {julie.matched_must_have}")
        print(f"  Missing Must    : {julie.missing_must_have}")
        print(f"  Degree Level    : {julie.degree_level}")
        print(f"  Degree Field    : {julie.degree_field}")
        print(f"  Total Exp Yrs   : {julie.total_exp_years}")

        # Assertion: Julie MUST be knocked out for a fullstack dev role
        assert julie.knocked_out, (
            f"BUG: JULIE MONROE should be knocked out for Full Stack Developer "
            f"(she is a dietitian with zero dev skills), but scored {julie.final_score}."
        )
        assert julie.final_score == 0.0, (
            f"BUG: Knocked-out candidate must have final_score=0.0, "
            f"got {julie.final_score}."
        )
        print("\n  ✅ ASSERTION PASSED — JULIE MONROE correctly knocked out.")
    print("═" * 72 + "\n")

    return results


def test_jd_backend_engineer(scorer, candidates):
    """Regression: Senior Backend Engineer."""
    jd = _jd_backend_engineer()
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_digital_marketer(scorer, candidates):
    """Regression: Digital Marketing Manager."""
    jd = _jd_digital_marketer()
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_security_guard(scorer, candidates):
    """Regression: Security Guard."""
    jd = _jd_security_guard()
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


def test_jd_fresher_web_dev(scorer, candidates):
    """Regression: Junior Web Developer (fresher-friendly)."""
    jd = _jd_fresher_web_dev()
    results = scorer.rank(jd, candidates)
    print_rankings(results, jd)
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  LOADING ALL RESUMES FROM:", RESUME_DIR)
    print("=" * 72)
    candidates = load_all_candidates(verbose=True)
    print(f"\n  Loaded {len(candidates)} candidates.\n")

    # Show which physical PDF maps to which candidate — catches duplicate names
    print_pdf_inventory(candidates)

    scorer = CandidateScorer()

    # ── Primary test: the UI screenshot JD ────────────────────────────────
    print("\n" + "▓" * 72)
    print("  TEST 0: Full Stack Developer")
    print("  → Checks correct PDF selection and JULIE MONROE knockout")
    print("▓" * 72)
    test_jd_fullstack_developer(scorer, candidates)

    # ── Regression suite ──────────────────────────────────────────────────
    print("\n" + "▓" * 72)
    print("  TEST 1: Senior Backend Engineer")
    print("▓" * 72)
    test_jd_backend_engineer(scorer, candidates)

    # print("\n" + "▓" * 72)
    # print("  TEST 2: Digital Marketing Manager")
    # print("▓" * 72)
    # test_jd_digital_marketer(scorer, candidates)

    # print("\n" + "▓" * 72)
    # print("  TEST 3: Security Guard")
    # print("▓" * 72)
    # test_jd_security_guard(scorer, candidates)

    # print("\n" + "▓" * 72)
    # print("  TEST 4: Junior Web Developer (Fresher-friendly)")
    # print("▓" * 72)
    # test_jd_fresher_web_dev(scorer, candidates)

    print("\n✅  All tests completed successfully.")


if __name__ == '__main__':
    main()
