import fitz
import time
import logging
from dataclasses import dataclass
from typing import Optional, List

from src.extraction import odl_client
from src.extraction.odl_client import ODLParseError

logger = logging.getLogger(__name__)

EXPECTED_CHARS_PER_PAGE = 3000

def cluster_word_x_positions(page: fitz.Page) -> list:
    words = page.get_text("words")
    if not words: return []
    xs = [w[0] for w in words]
    xs.sort()
    clusters = []
    curr = [xs[0]]
    for x in xs[1:]:
        if x - curr[-1] < 20:
            curr.append(x)
        else:
            clusters.append(curr)
            curr = [x]
    clusters.append(curr)
    return clusters

def reading_order_monotonicity(page: fitz.Page) -> float:
    words = page.get_text("words")
    if len(words) < 2: return 1.0
    y_diffs = [words[i][1] - words[i-1][1] for i in range(1, len(words))]
    non_negative = sum(1 for d in y_diffs if d >= -5)
    return non_negative / len(y_diffs)

def looks_tabular(page: fitz.Page) -> bool:
    drawings = page.get_drawings()
    return len(drawings) > 10

def pymupdf_layout_quality(page: fitz.Page) -> float:
    """
    Computed BEFORE field parsing. Answers: 'is this text extractable
    in reading order at all', not 'did we successfully parse a name'.
    """
    signals = {}
    
    # 1. Column consistency
    x_clusters = cluster_word_x_positions(page)
    signals["single_column"] = 1.0 if len(x_clusters) <= 1 else 0.0

    # 2. Reading-order sanity
    signals["reading_order_score"] = reading_order_monotonicity(page)

    # 3. Char density vs page area
    signals["char_density"] = min(1.0, len(page.get_text()) / EXPECTED_CHARS_PER_PAGE)

    # 4. Table detection
    signals["not_table_heavy"] = 1.0 if not looks_tabular(page) else 0.0

    return (
        signals["single_column"] * 0.35 +
        signals["reading_order_score"] * 0.30 +
        signals["char_density"] * 0.20 +
        signals["not_table_heavy"] * 0.15
    )

@dataclass
class StageTiming:
    document_id: str
    stage: str
    method_used: str
    duration_ms: float
    triggered_fallback: bool
    quality_score: Optional[float] = None
    error_reason: Optional[str] = None

@dataclass
class ParseResult:
    markdown: str
    elements: list
    stage_timings: List[StageTiming]
    quality_score: float
    error_reason: Optional[str] = None

class StructuralParsingService:
    def parse_pdf(self, pdf_path: str, doc_id: str, s3_bucket: str, s3_key: str) -> ParseResult:
        timings = []
        
        # PyMuPDF fast-path + Quality Gate
        t0 = time.time()
        doc = fitz.open(pdf_path)
        page_qualities = []
        raw_pymupdf_text = []
        
        for page in doc:
            page_qualities.append(pymupdf_layout_quality(page))
            raw_pymupdf_text.append(page.get_text())
            
        avg_quality = sum(page_qualities) / len(page_qualities) if page_qualities else 0.0
        t1 = time.time()
        
        raw_markdown = "\n".join(raw_pymupdf_text)
        triggered_fallback = avg_quality < 0.90
        
        timings.append(StageTiming(
            document_id=doc_id,
            stage="quality_check",
            method_used="pymupdf",
            duration_ms=(t1 - t0) * 1000,
            triggered_fallback=triggered_fallback,
            quality_score=avg_quality
        ))

        # Slow-Path (ODL)
        markdown = raw_markdown
        elements = []
        error_reason = None
        
        if triggered_fallback:
            t2 = time.time()
            try:
                odl_result = odl_client.parse(s3_bucket, s3_key)
                markdown = odl_result.markdown
                elements = odl_result.elements
                
                t3 = time.time()
                timings.append(StageTiming(
                    document_id=doc_id,
                    stage="odl_parse",
                    method_used="opendataloader",
                    duration_ms=(t3 - t2) * 1000,
                    triggered_fallback=False
                ))
            except ODLParseError as e:
                logger.error("ODL parse error, falling back to PyMuPDF text: %s", e)
                t3 = time.time()
                error_reason = str(e)
                timings.append(StageTiming(
                    document_id=doc_id,
                    stage="odl_parse",
                    method_used="opendataloader",
                    duration_ms=(t3 - t2) * 1000,
                    triggered_fallback=False,
                    error_reason=error_reason
                ))
                
        return ParseResult(
            markdown=markdown,
            elements=elements,
            stage_timings=timings,
            quality_score=avg_quality,
            error_reason=error_reason
        )
