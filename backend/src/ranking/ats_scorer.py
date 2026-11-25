"""
ats_scorer.py — ATS Diagnostics and Parseability Evaluation
===========================================================
Evaluates how ATS-friendly a document is based on layout and structure,
without relying on black-box LLMs.

Key principles (v2.2):
1. Exact Geometry: Remove fake len(line.text) * 5 estimates and hardcoded page=1.
   Only emit bounding boxes when exact coordinates (x0, y0, x1, y1) and 1-based page
   are verified from layout extraction.
2. Graceful Fallback: If exact geometry is missing, emit an informational flag
   without a misleading visual overlay.
3. Metric Separation: Structural ATS-risk (column scrambling, tables, fonts)
   is strictly separated from Extractor Confidence (OCR/character extractability).
"""

import logging
from typing import Dict, List, Any
from dataclasses import dataclass, field

from src.extractors.layout.layout_extractor import DocumentStructure

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    severity: str  # 'warning' or 'severe'
    reason: str


@dataclass
class AtsScoreResult:
    score: float
    breakdown: Dict[str, float]
    flags: List[str]
    bounding_boxes: List[BoundingBox] = field(default_factory=list)
    structural_score: float = 100.0
    extractor_confidence: float = 1.0


class AtsScoringService:
    """
    Evaluates how ATS-friendly a document is based on layout, structure,
    and text extractability, without relying on black-box LLMs.
    Separates structural ATS-risk from extractor confidence.
    Uses exact PDF coordinates without geometric approximations.
    """

    def score(self, doc_struct: DocumentStructure) -> AtsScoreResult:
        flags: List[str] = []
        bounding_boxes: List[BoundingBox] = []

        base_structural = 100.0

        # 1. Column penalty
        column_penalty = 0.0
        if doc_struct.layout in ("two_column", "header_sidebar_main"):
            column_penalty = 30.0
            flags.append("Two-column layout detected — most ATS systems read left-to-right and may scramble column content")

            # Collect actual bounding boxes from lines in the secondary/left column
            for line in doc_struct.classified_lines:
                if line.column == "left":
                    # Only emit bounding box if exact geometry is known
                    if line.x1 > line.x0 and line.bottom > line.top and line.page >= 1:
                        bounding_boxes.append(BoundingBox(
                            page=line.page,
                            x0=round(line.x0, 1),
                            y0=round(line.top, 1),
                            x1=round(line.x1, 1),
                            y1=round(line.bottom, 1),
                            severity="severe",
                            reason="Multi-column layout element",
                        ))
            if not bounding_boxes:
                flags.append("Multi-column structure detected without exact bounding box geometry (no visual overlay)")

        # 2. Table penalty
        table_penalty = 0.0
        if doc_struct.layout == "table_based":
            table_penalty = 40.0
            flags.append("Table layout detected — ATS parsers cannot reliably extract tables")

        # 3. Section header coverage
        section_headers = [l for l in doc_struct.classified_lines if l.role == "section_header"]
        section_bonus = min(20.0, len(section_headers) * 5.0)

        if len(section_headers) == 0:
            flags.append("Missing standard section headers — ATS parsers rely on headers to segment data")

        # 4. Font consistency (variance in body text)
        body_lines = [l for l in doc_struct.classified_lines if l.role == "body"]
        font_variance_penalty = 0.0
        if len(body_lines) > 5:
            sizes = [l.font_size for l in body_lines if l.font_size > 0]
            if sizes:
                avg_size = sum(sizes) / len(sizes)
                variance = sum((s - avg_size) ** 2 for s in sizes) / len(sizes)
                if variance > 2.0:
                    font_variance_penalty = 15.0
                    flags.append("High font size variance in body text — may signal graphics-heavy templates")

        # Structural ATS score (0-100)
        structural_score = max(0.0, min(100.0, base_structural - column_penalty - table_penalty - font_variance_penalty + section_bonus))

        # 5. Text extractability (extractor confidence)
        meta = getattr(doc_struct, "extraction_metadata", {}) or {}
        text_quality = float(meta.get("text_quality_score", 1.0))
        semantic_quality = float(meta.get("semantic_quality_score", 1.0))

        extractor_confidence = round((text_quality + semantic_quality) / 2.0, 3)
        extractability_penalty = round((1.0 - extractor_confidence) * 50.0, 1)
        if extractability_penalty > 10.0:
            flags.append("Poor text extractability — PDF may be an image or contain corrupted font encodings")

        breakdown = {
            "column_penalty": column_penalty,
            "table_penalty": table_penalty,
            "section_bonus": section_bonus,
            "font_variance_penalty": font_variance_penalty,
            "structural_score": round(structural_score, 1),
            "extractability_penalty": extractability_penalty,
            "extractor_confidence": extractor_confidence,
        }

        final_score = max(0.0, min(100.0, structural_score - extractability_penalty))

        return AtsScoreResult(
            score=round(final_score, 1),
            breakdown=breakdown,
            flags=flags,
            bounding_boxes=bounding_boxes,
            structural_score=round(structural_score, 1),
            extractor_confidence=extractor_confidence,
        )
