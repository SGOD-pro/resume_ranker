import fitz
import time
import logging
from dataclasses import dataclass
from typing import Optional, List

from src.extraction import odl_client
from src.extraction.odl_client import ODLParseError

logger = logging.getLogger(__name__)

# ── Quality-gate constants ─────────────────────────────────────────────────────
# Raised from 3 000 → 1 500: resumes typically have 1 000–3 000 chars per page.
# A dense page of text scores 1.0 at 1 500 chars; sparser pages scale linearly.
EXPECTED_CHARS_PER_PAGE = 1500

# ODL fallback threshold: quality below this triggers the slow path.
# 0.70 is more permissive than 0.90 so normal column layouts don't misfire.
QUALITY_THRESHOLD = 0.70


def cluster_word_x_positions(page: fitz.Page) -> list:
    """Cluster word left-edge x-positions to detect distinct text columns."""
    words = page.get_text("words")
    if not words:
        return []
    xs = sorted(w[0] for w in words)
    clusters: list = []
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
    """
    Fraction of consecutive word-pairs whose y-coordinates are non-decreasing
    (i.e. the text flows top-to-bottom in reading order).
    """
    words = page.get_text("words")
    if len(words) < 2:
        return 1.0
    y_diffs = [words[i][1] - words[i - 1][1] for i in range(1, len(words))]
    non_negative = sum(1 for d in y_diffs if d >= -5)
    return non_negative / len(y_diffs)


def looks_tabular(page: fitz.Page) -> bool:
    """
    Returns True only when the page is dominated by heavy table/grid graphics.

    Threshold raised from 10 → 30: standard resume rules/separators produce
    ~5–15 drawings; genuine table-heavy PDFs (scanned forms, spreadsheets)
    produce 30+.
    """
    drawings = page.get_drawings()
    return len(drawings) > 30


def pymupdf_layout_quality(page: fitz.Page) -> float:
    """
    Scores a page 0.0–1.0 for how reliably PyMuPDF can extract its text in
    reading order.  Answers: 'is the text extractable as-is?' — not 'did regex
    find a name?'.

    Weight rationale (must sum to 1.0):
      reading_order (0.40) — the strongest signal for extraction quality.
          Garbled or scanned PDFs have non-monotone y-coordinates.
      char_density   (0.35) — low char count → PDF is image-heavy / encrypted.
      not_table_heavy (0.15) — heavy table grids fragment text into tiny cells.
      col_penalty    (0.10) — a soft deduction for extreme multi-column layouts
          (≥4 distinct x-clusters).  Normal 2-column resume layouts lose only ~5 pts.

    Previous weights (single_column 0.35, not_table_heavy 0.15) were too harsh:
      - single_column=0 for any resume with a sidebar → 35 pts lost unconditionally.
      - looks_tabular threshold of 10 drawings caught all resumes with HR lines.
    Result: 90 % of resumes scored <0.60, causing spurious ODL fallback.
    """
    signals: dict = {}

    # 1. Reading order — primary signal
    signals["reading_order"] = reading_order_monotonicity(page)

    # 2. Character density vs expected chars per page
    signals["char_density"] = min(1.0, len(page.get_text()) / EXPECTED_CHARS_PER_PAGE)

    # 3. Table detection (soft: 0.0 only when truly table-heavy)
    signals["not_table_heavy"] = 0.0 if looks_tabular(page) else 1.0

    # 4. Column penalty — soft; only penalises extreme multi-column (≥4 clusters)
    x_clusters = cluster_word_x_positions(page)
    n_cols = len(x_clusters)
    if n_cols <= 2:
        signals["col_penalty"] = 1.0        # normal 1- or 2-col layout
    elif n_cols == 3:
        signals["col_penalty"] = 0.5        # mild deduction
    else:
        signals["col_penalty"] = 0.0        # very fragmented layout

    return (
        signals["reading_order"]  * 0.40
        + signals["char_density"] * 0.35
        + signals["not_table_heavy"] * 0.15
        + signals["col_penalty"] * 0.10
    )


def pymupdf_layout_quality_signals(page: fitz.Page) -> dict:
    """Return all individual signal values (for diagnostic/benchmark logging)."""
    x_clusters = cluster_word_x_positions(page)
    n_cols = len(x_clusters)
    ro = reading_order_monotonicity(page)
    cd = min(1.0, len(page.get_text()) / EXPECTED_CHARS_PER_PAGE)
    nt = 0.0 if looks_tabular(page) else 1.0
    cp = 1.0 if n_cols <= 2 else (0.5 if n_cols == 3 else 0.0)
    score = ro * 0.40 + cd * 0.35 + nt * 0.15 + cp * 0.10
    return {
        "reading_order": round(ro, 3),
        "char_density":  round(cd, 3),
        "not_table_heavy": round(nt, 3),
        "col_penalty":   round(cp, 3),
        "n_x_clusters":  n_cols,
        "text_len":      len(page.get_text()),
        "n_drawings":    len(page.get_drawings()),
        "score":         round(score, 3),
    }


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
    hyperlinks: list
    error_reason: Optional[str] = None


class StructuralParsingService:
    def parse_pdf(
        self,
        pdf_path: str,
        doc_id: str,
        s3_bucket: str,
        s3_key: str,
    ) -> ParseResult:
        timings: List[StageTiming] = []

        # ── PyMuPDF fast-path + quality gate ──────────────────────────────────
        t0 = time.time()
        doc = fitz.open(pdf_path)
        page_qualities: List[float] = []
        raw_pymupdf_text: List[str] = []
        hyperlinks: List[dict] = []

        for page in doc:
            page_qualities.append(pymupdf_layout_quality(page))
            raw_pymupdf_text.append(page.get_text())
            for link in page.get_links():
                if 'uri' in link:
                    hyperlinks.append({"uri": link['uri']})

        avg_quality = (
            sum(page_qualities) / len(page_qualities) if page_qualities else 0.0
        )
        t1 = time.time()

        raw_markdown = "\n".join(raw_pymupdf_text)
        triggered_fallback = avg_quality < QUALITY_THRESHOLD

        timings.append(
            StageTiming(
                document_id=doc_id,
                stage="quality_check",
                method_used="pymupdf",
                duration_ms=(t1 - t0) * 1000,
                triggered_fallback=triggered_fallback,
                quality_score=avg_quality,
            )
        )

        # ── Slow-path: ODL ─────────────────────────────────────────────────────
        markdown = raw_markdown
        elements: list = []
        error_reason: Optional[str] = None

        if triggered_fallback:
            t2 = time.time()
            try:
                odl_result = odl_client.parse(s3_bucket, s3_key)
                markdown = odl_result.markdown
                elements = odl_result.elements
                t3 = time.time()
                timings.append(
                    StageTiming(
                        document_id=doc_id,
                        stage="odl_parse",
                        method_used="opendataloader",
                        duration_ms=(t3 - t2) * 1000,
                        triggered_fallback=False,
                    )
                )
            except ODLParseError as e:
                logger.error("ODL parse error, falling back to PyMuPDF text: %s", e)
                t3 = time.time()
                error_reason = str(e)
                timings.append(
                    StageTiming(
                        document_id=doc_id,
                        stage="odl_parse",
                        method_used="opendataloader",
                        duration_ms=(t3 - t2) * 1000,
                        triggered_fallback=False,
                        error_reason=error_reason,
                    )
                )

        return ParseResult(
            markdown=markdown,
            elements=elements,
            stage_timings=timings,
            quality_score=avg_quality,
            hyperlinks=hyperlinks,
            error_reason=error_reason,
        )
