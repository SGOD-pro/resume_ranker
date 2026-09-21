"""
test_candidate_identity_resolver.py — P0 Identity Resolution Test Suite
=======================================================================
Table-driven verification of CandidateIdentityResolver against synthetic,
consent-safe fixtures.

Enforces:
  - Strict rejection of descriptive phrases (e.g. 'Insights possible sub-space.')
  - True candidate names resolved with verified or plausible confidence
  - Deterministic status assignment (VERIFIED, PLAUSIBLE, UNRESOLVED)
  - Zero fabricated identities on empty/scanned inputs
"""

import json
import os
import pytest
from typing import Dict, Any, List

from src.extractors.contact.identity_resolver import (
    CandidateIdentityResolver,
    CandidateIdentityResult,
    IdentityStatus,
    IdentitySource,
)


FIXTURES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "identity", "cases.json"
)


def load_fixtures() -> List[Dict[str, Any]]:
    with open(FIXTURES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def resolver() -> CandidateIdentityResolver:
    return CandidateIdentityResolver()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Table-Driven Fixture Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", load_fixtures(), ids=lambda c: c["id"])
def test_identity_resolver_cases(resolver: CandidateIdentityResolver, case: Dict[str, Any]):
    """Evaluate resolver against canonical synthetic test fixtures."""
    inputs = case["inputs"]
    expected = case["expected"]

    result = resolver.resolve(
        tagged_name=inputs.get("tagged_name"),
        visual_header_lines=inputs.get("visual_header_lines"),
        odl_headings=inputs.get("odl_headings"),
        adjacent_lines=inputs.get("adjacent_lines"),
        text_lines=inputs.get("text_lines"),
        email=inputs.get("email"),
        phone=inputs.get("phone"),
    )

    # 1. Display name assertion
    assert result.display_name == expected["display_name"], (
        f"[{case['id']}] Expected display_name {expected['display_name']!r}, got {result.display_name!r}. "
        f"Rejections: {result.candidate_rejections}"
    )

    # 2. Status assertion
    assert result.status.value == expected["status"], (
        f"[{case['id']}] Expected status {expected['status']!r}, got {result.status.value!r}"
    )

    # 3. Validity boolean
    if expected["is_valid_name"]:
        assert result.display_name is not None
        assert result.status in (IdentityStatus.VERIFIED, IdentityStatus.PLAUSIBLE)
        assert result.confidence >= 0.50
    else:
        assert result.display_name is None
        assert result.status == IdentityStatus.UNRESOLVED


# ─────────────────────────────────────────────────────────────────────────────
# 2. Specific Defect & Edge Case Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_subspace_defect_phrase_is_strictly_unresolved(resolver: CandidateIdentityResolver):
    """
    CRITICAL REAL-WORLD REGRESSION TEST:
    The phrase 'Insights possible sub-space.' must NEVER be emitted as a candidate name.
    """
    result = resolver.resolve(
        text_lines=[
            "Insights possible sub-space.",
            "Summary of qualifications in scientific computing",
        ]
    )
    assert result.display_name is None
    assert result.status == IdentityStatus.UNRESOLVED
    assert any("sentence or section punctuation" in r["reason"] or "descriptor" in r["reason"]
               for r in result.candidate_rejections)


def test_action_verbs_and_summary_phrases_rejected(resolver: CandidateIdentityResolver):
    """Verbs, gerunds, and resume summary fragments must be rejected."""
    bad_phrases = [
        "Enhanced Application Performance",
        "Motivated Towards Learning",
        "Developing Cloud Microservices",
        "Spearheaded Engineering Initiatives",
        "Results-Driven Team Player",
        "Experienced In Python",
    ]
    for phrase in bad_phrases:
        res = resolver.resolve(text_lines=[phrase])
        assert res.display_name is None, f"Phrase {phrase!r} should be rejected, but got {res.display_name!r}"
        assert res.status == IdentityStatus.UNRESOLVED


def test_job_titles_and_skills_rejected(resolver: CandidateIdentityResolver):
    """Job titles and skill lists must never become candidate names."""
    bad_titles = [
        "Senior Full Stack Developer",
        "Lead DevOps Specialist",
        "Technical Project Manager",
        "Registered Nurse",
        "Chief Executive Officer",
    ]
    for title in bad_titles:
        res = resolver.resolve(text_lines=[title])
        assert res.display_name is None, f"Title {title!r} should be rejected, but got {res.display_name!r}"
        assert res.status == IdentityStatus.UNRESOLVED


def test_company_names_rejected(resolver: CandidateIdentityResolver):
    """Company names with corporate suffixes must be rejected."""
    bad_companies = [
        "Acme Technologies Inc.",
        "Global Solutions LLC",
        "Stanford University",
        "General Motors Corp",
    ]
    for comp in bad_companies:
        res = resolver.resolve(text_lines=[comp])
        assert res.display_name is None, f"Company {comp!r} should be rejected, but got {res.display_name!r}"
        assert res.status == IdentityStatus.UNRESOLVED


def test_clean_name_not_discarded(resolver: CandidateIdentityResolver):
    """Legitimate candidate names must not be discarded by overly aggressive filters."""
    valid_names = [
        ("Kiran Malhotra", "kiran@example.com"),
        ("Jean-Luc Picard", "picard@enterprise.org"),
        ("Siddharth Gupta", "sid@domain.com"),
        ("Maria Garcia", "maria@corp.es"),
    ]
    for name, email in valid_names:
        res = resolver.resolve(
            visual_header_lines=[{"text": name, "font_size": 18.0, "is_bold": True, "page": 1}],
            email=email,
        )
        assert res.display_name == name, f"Valid name {name!r} was falsely rejected!"
        assert res.status in (IdentityStatus.VERIFIED, IdentityStatus.PLAUSIBLE)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Comprehensive Metric Reporting Helper
# ─────────────────────────────────────────────────────────────────────────────

def run_identity_benchmark_report() -> Dict[str, Any]:
    """
    Executes all test fixtures and computes gold-set performance metrics:
    total cases, exact name match, false-name rate, unresolved rate, per-source counts.
    """
    resolver = CandidateIdentityResolver()
    fixtures = load_fixtures()

    total_cases = len(fixtures)
    exact_matches = 0
    false_name_count = 0
    unresolved_count = 0
    failed_fixture_ids = []
    source_counts: Dict[str, int] = {}

    for case in fixtures:
        cid = case["id"]
        inputs = case["inputs"]
        expected = case["expected"]

        res = resolver.resolve(
            tagged_name=inputs.get("tagged_name"),
            visual_header_lines=inputs.get("visual_header_lines"),
            odl_headings=inputs.get("odl_headings"),
            adjacent_lines=inputs.get("adjacent_lines"),
            text_lines=inputs.get("text_lines"),
            email=inputs.get("email"),
            phone=inputs.get("phone"),
        )

        # Track sources
        src = res.source.value
        source_counts[src] = source_counts.get(src, 0) + 1

        if res.display_name == expected["display_name"] and res.status.value == expected["status"]:
            exact_matches += 1
        else:
            failed_fixture_ids.append(cid)

        # Check for false names (emitted non-null when expected was null)
        if not expected["is_valid_name"] and res.display_name is not None:
            false_name_count += 1

        if res.status == IdentityStatus.UNRESOLVED:
            unresolved_count += 1

    report = {
        "total_cases": total_cases,
        "exact_matches": exact_matches,
        "match_rate": round(exact_matches / total_cases * 100.0, 1),
        "false_name_count": false_name_count,
        "false_name_rate": round(false_name_count / total_cases * 100.0, 1),
        "unresolved_count": unresolved_count,
        "unresolved_rate": round(unresolved_count / total_cases * 100.0, 1),
        "source_counts": source_counts,
        "failed_fixture_ids": failed_fixture_ids,
    }
    return report


if __name__ == "__main__":
    rep = run_identity_benchmark_report()
    print("\n" + "=" * 60)
    print("  Candidate Identity Resolver — Gold-Set Test Report")
    print("=" * 60)
    for k, v in rep.items():
        print(f"  {k:20s}: {v}")
    print("=" * 60 + "\n")
