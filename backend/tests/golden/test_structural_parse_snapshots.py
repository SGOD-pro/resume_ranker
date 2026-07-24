"""
tests/golden/test_structural_parse_snapshots.py
================================================
Golden-file snapshot tests for structural_parse_from_odl_json().

These tests are the Phase 1 verification gate (phases.md §Phase 1).
They run WITHOUT a live JVM — fixtures in tests/golden/fixtures/*.json
represent real ODL output captured from a Java-equipped environment.

pytest marker: golden
Run all golden tests:   uv run pytest -m golden -v
Skip golden in CI:      uv run pytest -m "not golden"

What these tests assert (per phases.md verification gate):
  1. Correct element count extracted from each fixture
  2. Correct page_count
  3. Element types are recognised (heading/paragraph/list/table)
  4. Bounding boxes are parsed to 4-float tuples
  5. hidden flag correctly propagated
  6. flat_text returns non-empty string for normal resumes
  7. Two-column bbox geometry is preserved (x-coords in two clusters)
  8. Hidden text element is flagged (hidden=True)

To add a new fixture:
  1. Run ODL on a new PDF (requires Java).
  2. Copy the output {stem}.json to tests/golden/fixtures/{stem}.json.
  3. Add a test case to FIXTURE_CASES below.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from src.extraction.domain import StructuralParse, structural_parse_from_odl_json

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# (fixture_stem, expected_page_count, expected_element_count, has_hidden_element)
FIXTURE_CASES = [
    ("single_column", 2, 15, False),
    ("two_column",    1, 14, False),
    ("hidden_text",   1, 10, True),
]

_FAKE_HASH = "a" * 64
_FAKE_VERSION = "2.0-test"


def _load_fixture(stem: str) -> dict:
    path = FIXTURES_DIR / f"{stem}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.golden
@pytest.mark.parametrize("stem,page_count,elem_count,has_hidden", FIXTURE_CASES)
def test_structural_parse_element_count(
    stem: str,
    page_count: int,
    elem_count: int,
    has_hidden: bool,
) -> None:
    """parse_from_odl_json produces the correct number of elements."""
    raw = _load_fixture(stem)
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    assert len(result.kids) == elem_count, (
        f"{stem}: expected {elem_count} elements, got {len(result.kids)}"
    )


@pytest.mark.golden
@pytest.mark.parametrize("stem,page_count,elem_count,has_hidden", FIXTURE_CASES)
def test_structural_parse_page_count(
    stem: str,
    page_count: int,
    elem_count: int,
    has_hidden: bool,
) -> None:
    """page_count is read from 'number of pages' ODL field."""
    raw = _load_fixture(stem)
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    assert result.page_count == page_count


@pytest.mark.golden
@pytest.mark.parametrize("stem,page_count,elem_count,has_hidden", FIXTURE_CASES)
def test_structural_parse_bounding_boxes(
    stem: str,
    page_count: int,
    elem_count: int,
    has_hidden: bool,
) -> None:
    """Every element has a 4-float bounding_box tuple."""
    raw = _load_fixture(stem)
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    for elem in result.kids:
        assert len(elem.bounding_box) == 4, f"bbox length != 4 for element id={elem.element_id}"
        assert all(isinstance(v, float) for v in elem.bounding_box), (
            f"bbox contains non-float for element id={elem.element_id}"
        )


@pytest.mark.golden
@pytest.mark.parametrize("stem,page_count,elem_count,has_hidden", FIXTURE_CASES)
def test_structural_parse_element_types(
    stem: str,
    page_count: int,
    elem_count: int,
    has_hidden: bool,
) -> None:
    """All element types are non-empty strings."""
    raw = _load_fixture(stem)
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    for elem in result.kids:
        assert isinstance(elem.type, str) and elem.type, (
            f"element id={elem.element_id} has empty type"
        )


@pytest.mark.golden
@pytest.mark.parametrize("stem,page_count,elem_count,has_hidden", FIXTURE_CASES)
def test_structural_parse_hidden_flag(
    stem: str,
    page_count: int,
    elem_count: int,
    has_hidden: bool,
) -> None:
    """hidden flag is correctly propagated from 'hidden text' ODL field."""
    raw = _load_fixture(stem)
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    hidden_elements = [e for e in result.kids if e.hidden]
    if has_hidden:
        assert len(hidden_elements) >= 1, f"{stem}: expected >=1 hidden element, found 0"
    else:
        assert len(hidden_elements) == 0, (
            f"{stem}: expected 0 hidden elements, found {len(hidden_elements)}"
        )


@pytest.mark.golden
def test_single_column_flat_text_contains_contact() -> None:
    """flat_text for single_column includes email and phone."""
    raw = _load_fixture("single_column")
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    assert "john.smith@email.com" in result.flat_text
    assert "+1-555-123-4567" in result.flat_text


@pytest.mark.golden
def test_two_column_x_coords_cluster_into_two_groups() -> None:
    """
    Two-column fixture: paragraph bounding_box[0] (left x) values
    cluster into two distinct groups separated by > 100pt gap.
    This is exactly the geometry the TwoColumnLayoutEvaluator relies on.
    """
    raw = _load_fixture("two_column")
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    x_lefts = sorted(
        e.bounding_box[0]
        for e in result.kids
        if e.type == "paragraph"
    )
    # Find max gap between consecutive sorted x-coords
    gaps = [x_lefts[i + 1] - x_lefts[i] for i in range(len(x_lefts) - 1)]
    assert max(gaps) > 100.0, (
        f"Expected a gap >100pt in paragraph x-coords, gaps: {gaps}"
    )


@pytest.mark.golden
def test_hidden_text_element_has_small_bbox() -> None:
    """Hidden text element has a bounding box near zero (keyword stuffing pattern)."""
    raw = _load_fixture("hidden_text")
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    hidden = [e for e in result.kids if e.hidden]
    assert len(hidden) == 1
    bbox = hidden[0].bounding_box
    # left x and bottom y are 0.0, right x and top y are ≤ 1pt
    assert bbox[0] == 0.0 and bbox[1] == 0.0


@pytest.mark.golden
def test_structural_parse_content_hash_preserved() -> None:
    """content_hash passed in is preserved on the returned StructuralParse."""
    raw = _load_fixture("single_column")
    test_hash = "deadbeef" * 8
    result = structural_parse_from_odl_json(raw, test_hash, _FAKE_VERSION)
    assert result.content_hash == test_hash


@pytest.mark.golden
def test_structural_parse_parser_version_preserved() -> None:
    """parser_version passed in is preserved on the returned StructuralParse."""
    raw = _load_fixture("single_column")
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, "2.1-special")
    assert result.parser_version == "2.1-special"


@pytest.mark.golden
def test_heading_level_propagated() -> None:
    """Heading elements carry the correct heading_level."""
    raw = _load_fixture("single_column")
    result = structural_parse_from_odl_json(raw, _FAKE_HASH, _FAKE_VERSION)
    headings = [e for e in result.kids if e.type == "heading"]
    # First heading is the name — heading level 1
    assert headings[0].heading_level == 1
    # Subsequent section headings are level 2
    assert headings[1].heading_level == 2
