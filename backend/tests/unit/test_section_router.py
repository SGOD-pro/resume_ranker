"""
tests/unit/test_section_router.py
==================================
Unit tests for SectionRouter — verifies ODL elements are correctly
partitioned into canonical section slices.

No JVM required. Uses the golden fixtures from Phase 1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.extraction.domain import structural_parse_from_odl_json
from src.extraction.parsers.section_router import (
    SectionSlice,
    route,
    section_text,
)

FIXTURES = Path(__file__).parents[1] / "golden" / "fixtures"

_HASH = "a" * 64
_VER = "2.0-test"


def _load(stem: str):
    return structural_parse_from_odl_json(
        json.loads((FIXTURES / f"{stem}.json").read_text(encoding="utf-8")),
        _HASH, _VER,
    )


class TestSectionRouterSingleColumn:
    """single_column.json — 2-page, 15 elements, multiple canonical sections."""

    def setup_method(self):
        self.parse = _load("single_column")
        self.slices = route(self.parse)

    def test_produces_slices(self):
        assert len(self.slices) > 0

    def test_experience_section_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "experience" in canonicals

    def test_education_section_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "education" in canonicals

    def test_skills_section_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "skills" in canonicals

    def test_no_gaps_in_coverage(self):
        """Every ODL element index belongs to exactly one slice."""
        covered = []
        for sl in self.slices:
            covered.extend(range(sl.start, sl.end))
        assert sorted(covered) == list(range(len(self.parse.kids)))

    def test_slices_are_non_empty(self):
        for sl in self.slices:
            assert sl.end > sl.start

    def test_experience_text_contains_date(self):
        """Section text for experience must contain at least one year."""
        exp_slices = [sl for sl in self.slices if sl.canonical == "experience"]
        assert exp_slices, "No experience slice found"
        txt = section_text(self.parse, exp_slices[0])
        assert any(str(y) in txt for y in range(2010, 2026))

    def test_skills_text_contains_skill(self):
        skills_slices = [sl for sl in self.slices if sl.canonical == "skills"]
        assert skills_slices
        txt = section_text(self.parse, skills_slices[0])
        assert "Python" in txt or "python" in txt.lower()

    def test_certifications_or_unrecognised_for_certifications(self):
        """Certifications section should resolve to 'certifications' or be UNRECOGNISED."""
        canonicals = {sl.canonical for sl in self.slices}
        assert "certifications" in canonicals or "UNRECOGNISED" in canonicals


class TestSectionRouterTwoColumn:
    """two_column.json — 1 page, sections in two x-coord clusters."""

    def setup_method(self):
        self.parse = _load("two_column")
        self.slices = route(self.parse)

    def test_produces_slices(self):
        assert len(self.slices) > 0

    def test_experience_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "experience" in canonicals

    def test_skills_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "skills" in canonicals

    def test_no_overlap(self):
        seen: set[int] = set()
        for sl in self.slices:
            indices = set(range(sl.start, sl.end))
            assert not (indices & seen), "Overlapping slices detected"
            seen.update(indices)


class TestSectionRouterHiddenText:
    """hidden_text.json — has hidden element; routing must still work correctly."""

    def setup_method(self):
        self.parse = _load("hidden_text")
        self.slices = route(self.parse)

    def test_routing_unaffected_by_hidden_element(self):
        """Hidden text element (type=paragraph) must not appear as a section heading."""
        for sl in self.slices:
            # If this slice is UNRECOGNISED, its header_text should NOT be the
            # hidden element's keyword-stuffed content (hidden elements are paragraphs,
            # not headings — they can't create section boundaries)
            if sl.canonical == "UNRECOGNISED":
                assert "python java javascript" not in sl.header_text.lower(), (
                    "Hidden keyword-stuffed paragraph became a section header"
                )


    def test_experience_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "experience" in canonicals

    def test_skills_present(self):
        canonicals = {sl.canonical for sl in self.slices}
        assert "skills" in canonicals


class TestSectionTextHelper:
    """section_text() correctly excludes heading elements from output."""

    def test_heading_excluded_from_section_text(self):
        parse = _load("single_column")
        slices = route(parse)
        for sl in slices:
            txt = section_text(parse, sl)
            # The heading text for this slice should not appear as a leading line
            # (it's excluded from section_text output)
            if sl.header_text and sl.header_text in txt.splitlines()[:1]:
                pytest.fail(
                    f"Heading '{sl.header_text}' appeared in section_text output"
                )
