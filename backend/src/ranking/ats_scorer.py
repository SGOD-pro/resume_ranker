import logging
from typing import Dict, List, Any, Tuple
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


class AtsScoringService:
    """
    Evaluates how ATS-friendly a document is based purely on layout and structure,
    without relying on LLMs.
    """

    def score(self, doc_struct: DocumentStructure) -> AtsScoreResult:
        flags = []
        bounding_boxes = []

        score = 100.0
        
        # 1. Column penalty
        column_penalty = 0.0
        if doc_struct.layout in ("two_column", "header_sidebar_main"):
            column_penalty = 30.0
            flags.append("Two-column layout detected — most ATS systems read left-to-right and may scramble your content")
            
            # Find bounding boxes for left column
            for line in doc_struct.classified_lines:
                if line.column == "left":
                    # Estimate bounding box since ClassifiedLine doesn't store full bb
                    bounding_boxes.append(BoundingBox(
                        page=1, # simplified
                        x0=line.x0,
                        y0=line.top,
                        x1=line.x0 + len(line.text) * 5, # estimate width
                        y1=line.top + line.font_size,
                        severity="severe",
                        reason="Multi-column layout element"
                    ))

        # 2. Table penalty
        table_penalty = 0.0
        if doc_struct.layout == "table_based":
            table_penalty = 40.0
            flags.append("Table layout detected — ATS parsers cannot reliably extract tables")

        # 3. Section header coverage
        # Instead of calling registry, we count 'section_header' roles
        section_headers = [l for l in doc_struct.classified_lines if l.role == "section_header"]
        section_bonus = min(20.0, len(section_headers) * 5.0)
        
        if len(section_headers) == 0:
            flags.append("Missing standard section headers — ATS parsers rely on headers to segment data")

        # 4. Font consistency (variance in body text)
        body_lines = [l for l in doc_struct.classified_lines if l.role == "body"]
        font_variance_penalty = 0.0
        if len(body_lines) > 5:
            sizes = [l.font_size for l in body_lines]
            avg_size = sum(sizes) / len(sizes)
            variance = sum((s - avg_size)**2 for s in sizes) / len(sizes)
            if variance > 2.0:
                font_variance_penalty = 15.0
                flags.append("High font size variance in body text — may signal graphics-heavy templates")

        # 5. Text extractability (from metadata)
        text_quality = doc_struct.extraction_metadata.get("text_quality_score", 1.0)
        semantic_quality = doc_struct.extraction_metadata.get("semantic_quality_score", 1.0)
        
        extractability_score = (text_quality + semantic_quality) / 2.0
        extractability_penalty = (1.0 - extractability_score) * 50.0
        if extractability_penalty > 10.0:
            flags.append("Poor text extractability — PDF may be an image or contain corrupted fonts")
            
        breakdown = {
            "column_penalty": column_penalty,
            "table_penalty": table_penalty,
            "section_bonus": section_bonus,
            "font_variance_penalty": font_variance_penalty,
            "extractability_penalty": extractability_penalty
        }
        
        final_score = max(0.0, min(100.0, score - column_penalty - table_penalty - font_variance_penalty - extractability_penalty + section_bonus))
        
        return AtsScoreResult(
            score=round(final_score, 1),
            breakdown=breakdown,
            flags=flags,
            bounding_boxes=bounding_boxes
        )
