import fitz
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List

from src.extraction import odl_client
from src.extraction.odl_client import ODLParseError, DocDescriptor, parse_batch

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
        if x - curr[-1] < 50:
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

    # 4. Column penalty — strict; heavily penalizes any multi-column layout detected
    x_clusters = cluster_word_x_positions(page)
    n_cols = len(x_clusters)
    if n_cols <= 1:
        signals["col_penalty"] = 1.0        # true 1-col layout
    else:
        signals["col_penalty"] = 0.0        # 2+ columns (detected with 50px gap)

    return (
        signals["col_penalty"] * 0.35
        + signals["reading_order"]  * 0.30
        + signals["char_density"] * 0.20
        + signals["not_table_heavy"] * 0.15
    )


def pymupdf_layout_quality_signals(page: fitz.Page) -> dict:
    """Return all individual signal values (for diagnostic/benchmark logging)."""
    x_clusters = cluster_word_x_positions(page)
    n_cols = len(x_clusters)
    ro = reading_order_monotonicity(page)
    cd = min(1.0, len(page.get_text()) / EXPECTED_CHARS_PER_PAGE)
    nt = 0.0 if looks_tabular(page) else 1.0
    cp = 1.0 if n_cols <= 1 else 0.0
    score = cp * 0.35 + ro * 0.30 + cd * 0.20 + nt * 0.15
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


@dataclass
class BatchDoc:
    """Input descriptor for parse_pdf_batch."""
    document_id: str
    pdf_path: str
    s3_bucket: str
    s3_key: str
    save_images: bool = False


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

    def parse_pdf_batch(self, docs: List[BatchDoc]) -> List[ParseResult]:
        """
        Batch version of parse_pdf.

        Runs PyMuPDF quality gate on every document individually (fast), then
        calls odl_client.parse_batch() ONCE for all quality-failed documents —
        a single JVM boot amortised across N documents (ADR-10).

        Per-document ODL failures are caught and degraded to PyMuPDF text output
        with PARSE_FAILED error_reason, per ADR-09. No document silently disappears.
        Returns results in the same order as the input list.
        """
        if not docs:
            return []

        pymupdf_results: List[ParseResult] = []
        odl_needed: List[BatchDoc] = []
        odl_pymupdf_fallback: dict = {}  # doc_id -> raw PyMuPDF markdown (for degraded path)

        # ── Phase A: PyMuPDF quality gate for every document ─────────────────
        for doc in docs:
            timings: List[StageTiming] = []
            t0 = time.time()

            try:
                fitz_doc = fitz.open(doc.pdf_path)
                page_qualities: List[float] = []
                raw_pymupdf_text: List[str] = []
                hyperlinks: List[dict] = []

                for page in fitz_doc:
                    page_qualities.append(pymupdf_layout_quality(page))
                    raw_pymupdf_text.append(page.get_text())
                    for link in page.get_links():
                        if 'uri' in link:
                            hyperlinks.append({"uri": link['uri']})

                avg_quality = (
                    sum(page_qualities) / len(page_qualities) if page_qualities else 0.0
                )
                fitz_doc.close()
                t1 = time.time()
                raw_markdown = "\n".join(raw_pymupdf_text)
                triggered_fallback = avg_quality < QUALITY_THRESHOLD

                timings.append(StageTiming(
                    document_id=doc.document_id,
                    stage="quality_check",
                    method_used="pymupdf",
                    duration_ms=(t1 - t0) * 1000,
                    triggered_fallback=triggered_fallback,
                    quality_score=avg_quality,
                ))

                if triggered_fallback:
                    odl_needed.append(doc)
                    odl_pymupdf_fallback[doc.document_id] = (raw_markdown, hyperlinks, timings, avg_quality)
                    # Placeholder will be replaced after batch parse
                    pymupdf_results.append(None)  # type: ignore[arg-type]
                else:
                    pymupdf_results.append(ParseResult(
                        markdown=raw_markdown,
                        elements=[],
                        stage_timings=timings,
                        quality_score=avg_quality,
                        hyperlinks=hyperlinks,
                    ))

            except Exception as fitz_exc:
                logger.error("PyMuPDF failed for %s: %s", doc.document_id, fitz_exc)
                t1 = time.time()
                timings.append(StageTiming(
                    document_id=doc.document_id,
                    stage="quality_check",
                    method_used="pymupdf",
                    duration_ms=(t1 - t0) * 1000,
                    triggered_fallback=False,
                    error_reason=str(fitz_exc),
                ))
                pymupdf_results.append(ParseResult(
                    markdown="",
                    elements=[],
                    stage_timings=timings,
                    quality_score=0.0,
                    hyperlinks=[],
                    error_reason=str(fitz_exc),
                ))

        # ── Phase B: ONE batch ODL call for all quality-failed docs ──────────
        if odl_needed:
            batch_descriptors = [
                DocDescriptor(
                    document_id=d.document_id,
                    s3_bucket=d.s3_bucket,
                    s3_key=d.s3_key,
                    save_images=d.save_images,
                )
                for d in odl_needed
            ]

            t_batch_start = time.time()
            batch_result = parse_batch(batch_descriptors)
            t_batch_end = time.time()
            batch_duration_ms = (t_batch_end - t_batch_start) * 1000
            per_doc_ms = batch_duration_ms / len(odl_needed)

            # Fill in results for each ODL-needed doc
            for doc in odl_needed:
                raw_markdown, hyperlinks, timings, avg_quality = odl_pymupdf_fallback[doc.document_id]
                odl_idx = docs.index(doc)

                if doc.document_id in batch_result.results:
                    odl_out = batch_result.results[doc.document_id]
                    timings.append(StageTiming(
                        document_id=doc.document_id,
                        stage="odl_parse",
                        method_used="opendataloader",
                        duration_ms=per_doc_ms,
                        triggered_fallback=False,
                    ))
                    pymupdf_results[odl_idx] = ParseResult(
                        markdown=odl_out.markdown,
                        elements=odl_out.elements,
                        stage_timings=timings,
                        quality_score=avg_quality,
                        hyperlinks=hyperlinks,
                    )
                else:
                    # ODL failed for this specific doc — degrade to PyMuPDF text
                    err = batch_result.failed.get(doc.document_id)
                    error_reason = str(err) if err else f"ODL failed for {doc.document_id}"
                    logger.error("ODL batch partial failure for %s: %s", doc.document_id, error_reason)
                    timings.append(StageTiming(
                        document_id=doc.document_id,
                        stage="odl_parse",
                        method_used="opendataloader",
                        duration_ms=per_doc_ms,
                        triggered_fallback=False,
                        error_reason=error_reason,
                    ))
                    pymupdf_results[odl_idx] = ParseResult(
                        markdown=raw_markdown,
                        elements=[],
                        stage_timings=timings,
                        quality_score=avg_quality,
                        hyperlinks=hyperlinks,
                        error_reason=error_reason,
                    )

        return pymupdf_results
