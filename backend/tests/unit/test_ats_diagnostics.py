"""
test_ats_diagnostics.py — Unit tests for ATS Diagnostics and Parseability Evaluation
===================================================================================
Tests:
1. Exact PDF Bounding Boxes: Real page number and coordinates, no fake len(line.text) * 5.
2. Missing Geometry Handling: Informational flag emitted without fake visual overlay.
3. Separation of Structural Risk from Extractor Confidence.
4. Layout penalties: Multi-column, table layout, section header coverage, font variance.
"""

import pytest
from src.ranking.ats_scorer import AtsScoringService, BoundingBox, AtsScoreResult
from src.extractors.layout.layout_extractor import DocumentStructure, ClassifiedLine


def test_exact_geometry_no_fake_approximations():
    """Verify exact bounding box coordinates and page numbers are preserved."""
    svc = AtsScoringService()

    # Create a two-column document structure with exact line coordinates on page 2
    left_line = ClassifiedLine(
        text="Experience & Skills",
        role="sidebar_header",
        column="left",
        top=145.5,
        x0=36.0,
        font_size=11.0,
        page=2,
        x1=180.2,
        bottom=160.0,
    )
    header_line = ClassifiedLine(
        text="PROFESSIONAL EXPERIENCE",
        role="section_header",
        column="right",
        top=145.5,
        x0=210.0,
        font_size=12.0,
        page=2,
        x1=450.0,
        bottom=162.0,
    )

    doc_struct = DocumentStructure(
        full_width_text="",
        sidebar_text=left_line.text,
        main_text=header_line.text,
        classified_lines=[left_line, header_line],
        extraction_metadata={"text_quality_score": 0.98, "semantic_quality_score": 0.96},
    )

    res = svc.score(doc_struct)

    assert len(res.bounding_boxes) == 1
    box = res.bounding_boxes[0]
    # Page must match line's actual page, NOT hardcoded page 1
    assert box.page == 2
    assert box.x0 == 36.0
    assert box.y0 == 145.5
    assert box.x1 == 180.2
    assert box.y1 == 160.0
    # Must NOT equal the old fake estimate: x0 + len(text) * 5 = 36 + 19 * 5 = 131.0
    assert box.x1 != 36.0 + len(left_line.text) * 5
    assert box.severity == "severe"


def test_missing_geometry_emits_flag_without_overlay():
    """If exact geometry is missing (e.g. x1=0, bottom=0), do NOT invent fake overlay boxes."""
    svc = AtsScoringService()

    left_line_no_geom = ClassifiedLine(
        text="Skills Sidebar",
        role="sidebar_header",
        column="left",
        top=100.0,
        x0=50.0,
        font_size=10.0,
        page=1,
        x1=0.0,      # missing right boundary
        bottom=0.0,  # missing bottom boundary
    )

    doc_struct = DocumentStructure(
        full_width_text="",
        sidebar_text=left_line_no_geom.text,
        main_text="",
        classified_lines=[left_line_no_geom],
        extraction_metadata={"text_quality_score": 1.0, "semantic_quality_score": 1.0},
    )

    res = svc.score(doc_struct)

    # Must NOT invent fake coordinates
    assert len(res.bounding_boxes) == 0
    assert any("Multi-column structure detected without exact bounding box geometry" in f for f in res.flags)


def test_separation_structural_score_and_extractor_confidence():
    """Verify structural layout risk is tracked separately from text extraction quality."""
    svc = AtsScoringService()

    # Document with clean single-column structure and standard section headers, but low OCR quality
    header_line = ClassifiedLine(
        text="EXPERIENCE",
        role="section_header",
        column="full",
        top=50.0,
        x0=50.0,
        font_size=12.0,
        page=1,
        x1=150.0,
        bottom=65.0,
    )

    doc_struct = DocumentStructure(
        full_width_text=header_line.text,
        sidebar_text="",
        main_text="Some scanned resume text",
        classified_lines=[header_line],
        extraction_metadata={"text_quality_score": 0.50, "semantic_quality_score": 0.40},
    )

    res = svc.score(doc_struct)

    # Structural score should remain high (no column penalty, no table penalty, has section header bonus)
    assert res.structural_score >= 100.0
    assert res.breakdown["structural_score"] >= 100.0

    # Extractor confidence should be (0.50 + 0.40) / 2 = 0.45
    assert res.extractor_confidence == 0.45
    assert res.breakdown["extractor_confidence"] == 0.45
    assert res.breakdown["extractability_penalty"] > 10.0
    assert any("Poor text extractability" in f for f in res.flags)


def test_table_layout_penalty():
    """Table-based layout incurs penalty and informative flag."""
    svc = AtsScoringService()

    table_lines = [
        ClassifiedLine(text="Company A | Software Engineer | 2020 - 2022", role="body", column="right", top=50.0, x0=50.0, font_size=10.0),
        ClassifiedLine(text="Company B | Senior Engineer   | 2022 - Present", role="body", column="right", top=70.0, x0=50.0, font_size=10.0),
    ]

    doc_struct = DocumentStructure(
        full_width_text="",
        sidebar_text="",
        main_text="Table resume",
        classified_lines=table_lines,
        extraction_metadata={},
    )

    assert doc_struct.layout == "table_based"
    res = svc.score(doc_struct)
    assert res.breakdown["table_penalty"] == 40.0
    assert any("Table layout detected" in f for f in res.flags)
