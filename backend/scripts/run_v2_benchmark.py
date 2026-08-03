#!/usr/bin/env python3
"""
scripts/run_v2_benchmark.py
===========================
Phase 3 V2 Extraction Pipeline Benchmark — Full Field Report
           + ODL Batch vs Serial Latency Comparison

Tracks ALL extraction fields and calculates composite_score matching the V1
formula: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email

Changes from the previous version:
  1. No boto3 mock for Nova — uses the real Bedrock converse API.
  2. Tracks: name, email, phone, skills, experience, education.
  3. Composite score matches V1 formula.
  4. Prints individual PyMuPDF quality signals for the first 10 resumes
     so we can diagnose which signal is dragging the gate score down.
  5. Full routing breakdown + LLM fallback rate.
  6. NEW: Runs SERIAL mode first (baseline = old one-by-one ODL) then
     BATCH mode (new = single JVM boot amortised).  Prints side-by-side
     latency comparison table at the end.

Usage:
    cd backend && uv run python scripts/run_v2_benchmark.py
"""

from __future__ import annotations

import os
import sys
import uuid
import shutil
import json
import time
import math
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sys.path setup ─────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Logging: suppress noisy library logs, keep our own ─────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logging.getLogger("src").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.ERROR)
logging.getLogger("boto3").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

# ── S3 mock (local-only): fake download by copying the local file ─────────────
# We mock S3 so the benchmark can run without a live LocalStack instance.
# Nova / Bedrock is NOT mocked — it uses real credentials from .env.
from unittest.mock import patch, MagicMock

_current_pdf_path: List[str] = [""]   # mutable container so inner fn can update it
# Map doc_id -> actual pdf_path (used by batch mode where multiple files are active)
_pdf_path_map: Dict[str, str] = {}

def _s3_side_effect(service_name, *args, **kwargs):
    """Intercept only 's3'; let everything else (including bedrock-runtime) pass through."""
    if service_name == "s3":
        mock_s3 = MagicMock()
        def fake_download(Bucket, Key, Filename, **_kw):
            # Batch mode: look up by filename stem (document_id)
            stem = Path(Filename).stem
            if stem in _pdf_path_map:
                shutil.copy(_pdf_path_map[stem], Filename)
            else:
                # Fall back to single-doc path
                shutil.copy(_current_pdf_path[0], Filename)
        mock_s3.download_file.side_effect = fake_download
        mock_s3.upload_file = MagicMock()  # no-op image uploads
        return mock_s3
    # For bedrock-runtime and any other service: create a REAL boto3 client
    _s3_patch.stop()
    try:
        import boto3 as _boto3
        client = _boto3.client(service_name, *args, **kwargs)
    finally:
        _s3_patch.start()
    return client

_s3_patch = patch("boto3.client", side_effect=_s3_side_effect)
_s3_patch.start()

# ── Now import pipeline (after the patch is in place) ─────────────────────────
from src.extraction.extraction_pipeline import ExtractionPipeline
from src.extraction.structural_parsing_service import (
    pymupdf_layout_quality_signals,
    QUALITY_THRESHOLD,
    BatchDoc,
)
from src.config.aws import get_settings

try:
    import fitz
    _fitz_ok = True
except ImportError:
    _fitz_ok = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> float:
    return round(n / total * 100, 1) if total else 0.0

def _p50_p95(data: List[float]):
    if not data:
        return 0.0, 0.0
    s = sorted(data)
    p50 = s[max(0, int(len(s) * 0.50) - 1)]
    p95 = s[max(0, min(len(s) - 1, int(math.ceil(len(s) * 0.95)) - 1))]
    return round(p50, 1), round(p95, 1)

def _has(value: Any) -> bool:
    """True when a field is non-null and non-empty."""
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(str(value).strip())

def _composite(name: bool, email: bool, skills: bool,
               experience: bool, education: bool) -> float:
    """V1 formula: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email"""
    return (
        0.20 * (1 if name      else 0)
        + 0.10 * (1 if email   else 0)
        + 0.25 * (1 if skills  else 0)
        + 0.25 * (1 if experience else 0)
        + 0.20 * (1 if education  else 0)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Signal diagnostics for first 10 PDFs
# ─────────────────────────────────────────────────────────────────────────────

def print_signal_diagnostics(pdfs: List[Path], n: int = 10) -> None:
    if not _fitz_ok:
        print("  [fitz not available — skipping signal diagnostics]")
        return

    print(f"\n{'─'*90}")
    print("  QUALITY SIGNAL DIAGNOSTICS (first 10 resumes, page 1)")
    print(f"  Threshold: {QUALITY_THRESHOLD}   |   Weights: read_ord=0.40  char_dens=0.35  not_table=0.15  col_pen=0.10")
    print(f"{'─'*90}")
    hdr = (f"{'File':<20} {'Score':>6} {'ReadOrd':>8} {'CharDens':>9} "
           f"{'NoTable':>8} {'ColPen':>8} {'nCols':>6} {'nDraw':>6} {'TextLen':>8} {'ODL?':>5}")
    print(hdr)
    print("─" * 90)

    for pdf in pdfs[:n]:
        doc = fitz.open(str(pdf))
        page = doc[0]
        sig = pymupdf_layout_quality_signals(page)
        doc.close()
        odl = "YES" if sig["score"] < QUALITY_THRESHOLD else "no"
        print(
            f"{pdf.name:<20} {sig['score']:>6.3f} "
            f"{sig['reading_order']:>8.3f} {sig['char_density']:>9.3f} "
            f"{sig['not_table_heavy']:>8.2f} {sig['col_penalty']:>8.2f} "
            f"{sig['n_x_clusters']:>6} {sig['n_drawings']:>6} "
            f"{sig['text_len']:>8} {odl:>5}"
        )
    print("─" * 90)


# ─────────────────────────────────────────────────────────────────────────────
# Single-doc field accumulation helper
# ─────────────────────────────────────────────────────────────────────────────

class Stats:
    """Accumulates per-run statistics."""
    def __init__(self):
        self.pymupdf_only_count = 0
        self.odl_fallback_count = 0
        self.nova_fallback_count = 0
        self.nova_category_a = 0
        self.nova_category_b = 0
        self.pymupdf_fields = {"name": 0, "email": 0, "phone": 0}
        self.pymupdf_docs = 0
        self.odl_fields = {"name": 0, "email": 0, "phone": 0}
        self.odl_docs = 0
        
        self.total_quality = 0.0
        self.field_counts: Dict[str, int] = {
            "name": 0, "email": 0, "phone": 0,
            "skills": 0, "experience": 0, "education": 0,
        }
        self.skill_total = 0
        self.exp_total   = 0
        self.edu_total   = 0
        self.composite_total = 0.0
        self.latencies: Dict[str, List[float]] = {
            "pymupdf_ms": [], "odl_ms": [], "nova_ms": [], "total_ms": [],
        }
        self.errors: List[str] = []
        self.odl_call_count = 0  # number of actual odl_client invocations

        # Per-layer quality + composite tracking
        # pymupdf_only: docs that stayed on PyMuPDF fast-path
        # odl_only: docs that went through ODL (no Nova)
        # nova: docs that also used Nova (may or may not have used ODL first)
        self._pymupdf_only_quality: List[float] = []
        self._pymupdf_only_composite: List[float] = []
        self._odl_quality: List[float] = []
        self._odl_composite: List[float] = []
        self._nova_quality: List[float] = []
        self._nova_composite: List[float] = []

        self.input_tokens: List[int] = []
        self.output_tokens: List[int] = []

    def accumulate(self, result: Dict[str, Any], t_total_ms: float) -> None:
        fields      = result.get("fields", {})
        stage_times = result.get("stage_timings", [])
        q           = result.get("extraction_quality", 0.0)

        pymupdf_ms = odl_ms = nova_ms = 0.0
        used_odl = used_nova = False

        for t in stage_times:
            stage  = t.get("stage", "")
            dur    = t.get("duration_ms", 0.0)
            if stage == "quality_check":
                pymupdf_ms = dur
            elif stage == "odl_parse":
                odl_ms  = dur
                used_odl = True
            elif stage == "nova_fallback":
                nova_ms  = dur
                used_nova = True

        f_name  = _has(fields.get("name"))
        f_email = _has(fields.get("email"))
        f_phone = _has(fields.get("phone"))
        f_skills = _has(fields.get("skills"))
        f_exp    = _has(fields.get("experience"))
        f_edu    = _has(fields.get("education"))

        if used_odl:
            self.odl_docs += 1
            if f_name: self.odl_fields["name"] += 1
            if f_email: self.odl_fields["email"] += 1
            if f_phone: self.odl_fields["phone"] += 1
        else:
            self.pymupdf_docs += 1
            if f_name: self.pymupdf_fields["name"] += 1
            if f_email: self.pymupdf_fields["email"] += 1
            if f_phone: self.pymupdf_fields["phone"] += 1

        nova_t = fields.get("_nova_tokens", {})
        if nova_t:
            self.input_tokens.append(nova_t.get("inputTokens", 0))
            self.output_tokens.append(nova_t.get("outputTokens", 0))

        comp = _composite(f_name, f_email, f_skills, f_exp, f_edu)

        if used_odl:
            self.odl_fallback_count += 1
            self.latencies["odl_ms"].append(odl_ms)
            if not used_nova:
                self._odl_quality.append(q)
                self._odl_composite.append(comp)
        else:
            self.pymupdf_only_count += 1
            if not used_nova:
                self._pymupdf_only_quality.append(q)
                self._pymupdf_only_composite.append(comp)

        if used_nova:
            self.nova_fallback_count += 1
            if used_odl:
                self.nova_category_a += 1
            else:
                self.nova_category_b += 1
            self.latencies["nova_ms"].append(nova_ms)
            self._nova_quality.append(q)
            self._nova_composite.append(comp)

        self.latencies["pymupdf_ms"].append(pymupdf_ms)
        self.latencies["total_ms"].append(t_total_ms)
        self.total_quality += q

        if f_name:    self.field_counts["name"]       += 1
        if f_email:   self.field_counts["email"]      += 1
        if f_phone:   self.field_counts["phone"]      += 1
        if f_skills:  self.field_counts["skills"]     += 1
        if f_exp:     self.field_counts["experience"] += 1
        if f_edu:     self.field_counts["education"]  += 1

        skills_list = fields.get("skills") or []
        exp_list    = fields.get("experience") or []
        edu_list    = fields.get("education") or []
        if isinstance(skills_list, list): self.skill_total += len(skills_list)
        if isinstance(exp_list, list):    self.exp_total   += len(exp_list)
        if isinstance(edu_list, list):    self.edu_total   += len(edu_list)

        self.composite_total += comp


# ─────────────────────────────────────────────────────────────────────────────
# Serial (old) run
# ─────────────────────────────────────────────────────────────────────────────

def run_serial(pipeline: ExtractionPipeline, pdfs: List[Path],
               job_id: str, settings) -> Stats:
    """Old one-by-one run — establishes the baseline."""
    stats = Stats()
    n = len(pdfs)

    print(f"\n{'─'*70}")
    print(f"  [SERIAL MODE] Running {n} PDFs one-by-one (baseline)…")
    print(f"{'─'*70}")

    for i, pdf_path in enumerate(pdfs, 1):
        _current_pdf_path[0] = str(pdf_path)
        doc_id = str(uuid.uuid4())
        t_start = time.time()

        try:
            from src.infrastructure.storage.storage_service import StorageService
            storage = StorageService()
            with open(pdf_path, "rb") as f:
                content = f.read()
            s3_key = storage.upload_resume(job_id, doc_id, content, pdf_path.name)

            result = pipeline.run_pipeline(
                str(pdf_path), doc_id, settings.s3_bucket_name, s3_key
            )
            t_total_ms = (time.time() - t_start) * 1000
            stats.accumulate(result, t_total_ms)

        except Exception as exc:
            stats.errors.append(f"{pdf_path.name}: {exc}")
            stats.latencies["total_ms"].append((time.time() - t_start) * 1000)

        if i % 10 == 0 or i == n:
            print(f"    [{i:3d}/{n}] ODL={stats.odl_fallback_count}  "
                  f"Nova={stats.nova_fallback_count}  Err={len(stats.errors)}")

    # In serial mode, each ODL-failing doc triggers one lambda invoke
    stats.odl_call_count = stats.odl_fallback_count
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Batch (new) run
# ─────────────────────────────────────────────────────────────────────────────

BATCH_SIZE = 25  # Tuned up from 10 to amortize JVM boot; paired with a larger MaximumBatchingWindowInSeconds in prod

def run_batch(pipeline: ExtractionPipeline, pdfs: List[Path],
              job_id: str, settings) -> Stats:
    """New batched run — groups docs into windows, calls parse_batch() once per window."""
    stats = Stats()
    n = len(pdfs)

    print(f"\n{'─'*70}")
    print(f"  [BATCH MODE] Running {n} PDFs in groups of {BATCH_SIZE}…")
    print(f"{'─'*70}")

    from src.infrastructure.storage.storage_service import StorageService
    storage = StorageService()

    # Prepare all docs
    batch_docs: List[BatchDoc] = []
    doc_pdf_map: Dict[str, Path] = {}

    for pdf_path in pdfs:
        doc_id = str(uuid.uuid4())
        with open(pdf_path, "rb") as f:
            content = f.read()
        s3_key = storage.upload_resume(job_id, doc_id, content, pdf_path.name)
        _pdf_path_map[doc_id] = str(pdf_path)
        batch_docs.append(BatchDoc(
            document_id=doc_id,
            pdf_path=str(pdf_path),
            s3_bucket=settings.s3_bucket_name,
            s3_key=s3_key,
        ))
        doc_pdf_map[doc_id] = pdf_path

    # Process in batches
    processed = 0
    for batch_start in range(0, len(batch_docs), BATCH_SIZE):
        batch = batch_docs[batch_start:batch_start + BATCH_SIZE]
        t_batch_start = time.time()

        try:
            results = pipeline.run_pipeline_batch(batch)
            t_batch_end = time.time()

            # Attribute E2E time equally across batch members
            per_doc_total_ms = (t_batch_end - t_batch_start) * 1000 / len(batch)

            for result in results:
                stats.accumulate(result, per_doc_total_ms)

            # Count batch invocations (1 call covers the whole batch)
            has_odl_in_batch = any(
                any(t.get("stage") == "odl_parse" for t in r.get("stage_timings", []))
                for r in results
            )
            if has_odl_in_batch:
                stats.odl_call_count += 1

        except Exception as exc:
            for bd in batch:
                stats.errors.append(f"{doc_pdf_map[bd.document_id].name}: {exc}")
                stats.latencies["total_ms"].append(0.0)

        processed += len(batch)
        if processed % 10 == 0 or processed == n:
            print(f"    [{processed:3d}/{n}] ODL-docs={stats.odl_fallback_count}  "
                  f"ODL-calls={stats.odl_call_count}  Nova={stats.nova_fallback_count}  "
                  f"Err={len(stats.errors)}")

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Report printers
# ─────────────────────────────────────────────────────────────────────────────

def print_report(label: str, stats: Stats, n: int) -> None:
    processed = n - len(stats.errors)
    avg_q = round(stats.total_quality / processed, 3) if processed else 0.0
    avg_composite = round(stats.composite_total / processed * 100, 1) if processed else 0.0

    py_p50, py_p95   = _p50_p95(stats.latencies["pymupdf_ms"])
    odl_p50, odl_p95 = _p50_p95(stats.latencies["odl_ms"])
    nov_p50, nov_p95 = _p50_p95(stats.latencies["nova_ms"])
    tot_p50, tot_p95 = _p50_p95(stats.latencies["total_ms"])

    def _avg(lst): return round(sum(lst) / len(lst), 3) if lst else 0.0
    def _avg_pct(lst): return round(sum(lst) / len(lst) * 100, 1) if lst else 0.0

    print(f"\n{'='*80}")
    print(f"  === {label} — Final Report ===")
    print(f"{'='*80}")
    print(f"  Total resumes:      {n}")
    print(f"  Processed OK:       {processed}")
    print(f"  Errors:             {len(stats.errors)}")
    print(f"  Avg quality score:  {avg_q:.3f}  (threshold={QUALITY_THRESHOLD})")
    print(f"  Avg composite:      {avg_composite:.1f}%")

    print("\n  ┌── Nova Fallback Categories ──────────────────────────────────────────")
    print(f"  Category A (ODL -> Nova):        {stats.nova_category_a} docs")
    print(f"  Category B/C (PyMuPDF -> Nova):  {stats.nova_category_b} docs")
    print(f"  Total Nova Fallbacks:            {stats.nova_fallback_count} docs")

    print("\n  ┌── Field Extraction Split (Name / Email / Phone) ───────────────────")
    p_name = stats.pymupdf_fields['name']/stats.pymupdf_docs*100 if stats.pymupdf_docs else 0
    p_email = stats.pymupdf_fields['email']/stats.pymupdf_docs*100 if stats.pymupdf_docs else 0
    p_phone = stats.pymupdf_fields['phone']/stats.pymupdf_docs*100 if stats.pymupdf_docs else 0
    print(f"  PyMuPDF Docs ({stats.pymupdf_docs}): Name {p_name:.1f}%, Email {p_email:.1f}%, Phone {p_phone:.1f}%")
    o_name = stats.odl_fields['name']/stats.odl_docs*100 if stats.odl_docs else 0
    o_email = stats.odl_fields['email']/stats.odl_docs*100 if stats.odl_docs else 0
    o_phone = stats.odl_fields['phone']/stats.odl_docs*100 if stats.odl_docs else 0
    print(f"  ODL Docs ({stats.odl_docs}):     Name {o_name:.1f}%, Email {o_email:.1f}%, Phone {o_phone:.1f}%")
    print()

    # ── Per-layer breakdown ────────────────────────────────────────────────────
    py_only_n  = stats.pymupdf_only_count
    odl_n      = stats.odl_fallback_count
    nova_n     = stats.nova_fallback_count
    # Nova fires on top of either PyMuPDF-only or ODL — bucket them
    nova_on_py = nova_n - sum(1 for _ in stats._nova_quality)  # placeholder (actual counting done in accumulate)

    py_avg_q   = _avg(stats._pymupdf_only_quality)
    odl_avg_q  = _avg(stats._odl_quality)
    nov_avg_q  = _avg(stats._nova_quality)
    py_avg_c   = _avg_pct(stats._pymupdf_only_composite)
    odl_avg_c  = _avg_pct(stats._odl_composite)
    nov_avg_c  = _avg_pct(stats._nova_composite)

    print("  ── Per-Layer Breakdown ────────────────────────────────────────────────────────")
    print(f"  {'Layer':<28} {'PDFs':>6} {'%':>6}  {'AvgTime p50ms':>14}  {'AvgQuality':>11}  {'AvgComposite':>12}")
    print(f"  {'─'*80}")
    # PyMuPDF-only (no ODL, no Nova)
    print(f"  {'PyMuPDF-only (fast path)':<28} {len(stats._pymupdf_only_quality):>6} {_pct(len(stats._pymupdf_only_quality),n):>6.1f}%"
          f"  {py_p50:>13.1f}ms  {py_avg_q:>11.3f}  {py_avg_c:>11.1f}%")
    # ODL fallback (quality gate fired, no Nova)
    print(f"  {'ODL fallback (JVM parse)':<28} {len(stats._odl_quality):>6} {_pct(len(stats._odl_quality),n):>6.1f}%"
          f"  {odl_p50:>13.1f}ms  {odl_avg_q:>11.3f}  {odl_avg_c:>11.1f}%")
    # Nova fallback (LLM infill, may fire after PyMuPDF or ODL)
    print(f"  {'Nova fallback (LLM infill)':<28} {nova_n:>6} {_pct(nova_n,n):>6.1f}%"
          f"  {nov_p50:>13.1f}ms  {nov_avg_q:>11.3f}  {nov_avg_c:>11.1f}%")
    print(f"  {'─'*80}")
    print(f"  {'Total processed':<28} {processed:>6} {'100.0':>6}%"
          f"  {tot_p50:>13.1f}ms  {avg_q:>11.3f}  {avg_composite:>11.1f}%")
    print()
    print(f"  Lambda invocations — ODL: {stats.odl_call_count}  "
          f"(saved {max(0, odl_n - stats.odl_call_count)} JVM boots vs serial)")
    print()

    print("  ── Latency (ms) p50 / p95 ─────────────────────────────────────────")
    print(f"  PyMuPDF (quality gate):  {py_p50:7.1f}  / {py_p95:7.1f}  (all {len(stats.latencies['pymupdf_ms'])} docs)")
    print(f"  ODL parse:               {odl_p50:7.1f}  / {odl_p95:7.1f}  ({len(stats.latencies['odl_ms'])} docs, {stats.odl_call_count} Lambda call(s))")
    print(f"  Nova converse:           {nov_p50:7.1f}  / {nov_p95:7.1f}  ({len(stats.latencies['nova_ms'])} docs)")
    print(f"  Total E2E:               {tot_p50:7.1f}  / {tot_p95:7.1f}")
    print()

    if stats.input_tokens or stats.output_tokens:
        tot_in = sum(stats.input_tokens)
        tot_out = sum(stats.output_tokens)
        min_in = min(stats.input_tokens) if stats.input_tokens else 0
        max_in = max(stats.input_tokens) if stats.input_tokens else 0
        min_out = min(stats.output_tokens) if stats.output_tokens else 0
        max_out = max(stats.output_tokens) if stats.output_tokens else 0
        print("  ── Token Usage (Nova LLM) ─────────────────────────────────────────────────")
        print(f"  Input Tokens:  Total: {tot_in:>6}  |  Min/doc: {min_in:>4}  |  Max/doc: {max_in:>4}")
        print(f"  Output Tokens: Total: {tot_out:>6}  |  Min/doc: {min_out:>4}  |  Max/doc: {max_out:>4}")
        print()

    print("  ── Field Extraction (V1-compatible report) ────────────────────────")
    print(f"  {'Field':<12} {'Present':>8} {'Rate %':>8}  {'Avg/doc':>8}")
    print(f"  {'─'*44}")
    for fname in ("name", "email", "phone", "skills", "experience", "education"):
        cnt  = stats.field_counts[fname]
        rate = _pct(cnt, processed)
        if fname == "skills":
            avg_s = round(stats.skill_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_s:>8.1f}")
        elif fname == "experience":
            avg_e = round(stats.exp_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_e:>8.1f}")
        elif fname == "education":
            avg_d = round(stats.edu_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_d:>8.1f}")
        else:
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%")
    print()
    print(f"  Composite score:  {avg_composite:.1f}%")
    print(f"  Formula: 0.20×name + 0.25×skills + 0.25×experience + 0.20×education + 0.10×email")
    print()

    if stats.errors:
        print("  ── Errors (first 5) ───────────────────────────────────────────────")
        for e in stats.errors[:5]:
            print(f"  ⚠  {e[:100]}")
        print()

    print(f"{'='*80}\n")


def print_comparison(serial: Stats, batch: Stats, n: int) -> None:
    s_tot_p50, s_tot_p95 = _p50_p95(serial.latencies["total_ms"])
    b_tot_p50, b_tot_p95 = _p50_p95(batch.latencies["total_ms"])
    s_odl_p50, s_odl_p95 = _p50_p95(serial.latencies["odl_ms"])
    b_odl_p50, b_odl_p95 = _p50_p95(batch.latencies["odl_ms"])

    odl_docs = serial.odl_fallback_count
    jvm_savings = max(0, serial.odl_call_count - batch.odl_call_count)
    time_saved_s = round(jvm_savings * 0.74, 1)  # 0.74s = measured JVM boot

    print(f"\n{'█'*70}")
    print("  ███  ODL BATCH vs SERIAL — COMPARISON  ███")
    print(f"{'█'*70}")
    print(f"  {'Metric':<35} {'Serial (old)':>14} {'Batch (new)':>14}")
    print(f"  {'─'*65}")
    print(f"  {'ODL-failing docs':<35} {odl_docs:>14} {batch.odl_fallback_count:>14}")
    print(f"  {'Lambda invocations (ODL)':<35} {serial.odl_call_count:>14} {batch.odl_call_count:>14}")
    print(f"  {'JVM boots saved':<35} {'':>14} {jvm_savings:>14}")
    print(f"  {'Est. JVM-boot time saved (s)':<35} {'':>14} {time_saved_s:>14}")
    print(f"  {'ODL p50 ms (per-doc)':<35} {s_odl_p50:>14.1f} {b_odl_p50:>14.1f}")
    print(f"  {'ODL p95 ms (per-doc)':<35} {s_odl_p95:>14.1f} {b_odl_p95:>14.1f}")
    print(f"  {'Total E2E p50 ms':<35} {s_tot_p50:>14.1f} {b_tot_p50:>14.1f}")
    print(f"  {'Total E2E p95 ms':<35} {s_tot_p95:>14.1f} {b_tot_p95:>14.1f}")
    s_comp = round(serial.composite_total / max(1, n - len(serial.errors)) * 100, 1)
    b_comp = round(batch.composite_total / max(1, n - len(batch.errors)) * 100, 1)
    print(f"  {'Composite extraction score':<35} {s_comp:>13.1f}% {b_comp:>13.1f}%")
    print(f"{'█'*70}\n")
    print("  NOTE: Composite scores must be equal (or very close) — any divergence")
    print("        indicates doc_id attribution or ordering bug in batch mode.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark():
    settings   = get_settings()
    pipeline   = ExtractionPipeline()
    resumes_dir = BACKEND_DIR / "data" / "resumes"

    if not resumes_dir.exists():
        print(f"ERROR: {resumes_dir} not found.")
        return

    import random
    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    valid_pdfs = list(all_pdfs)
    random.seed(42)
    random.shuffle(valid_pdfs)
    pdfs = valid_pdfs[:200]
    n    = len(pdfs)

    print(f"\n{'═'*70}")
    print("  PHASE 3 V2 EXTRACTION BENCHMARK — Full Field Report")
    print(f"{'═'*70}")
    print(f"  Resumes: {n}   |   Quality threshold: {QUALITY_THRESHOLD}")
    print(f"  Nova: real Bedrock converse API (no mock)")
    print(f"  Batch size: {BATCH_SIZE}")

    print_signal_diagnostics(pdfs)

    job_id_serial = f"bench-serial-{uuid.uuid4().hex[:8]}"
    job_id_batch  = f"bench-batch-{uuid.uuid4().hex[:8]}"

    # ── Run 1: Serial baseline ─────────────────────────────────────────────────
    serial_stats = run_serial(pipeline, pdfs, job_id_serial, settings)
    print_report("SERIAL MODE (baseline — old one-by-one ODL)", serial_stats, n)

    # ── Run 2: Batch mode ──────────────────────────────────────────────────────
    _pdf_path_map.clear()  # reset before batch run
    batch_stats = run_batch(pipeline, pdfs, job_id_batch, settings)
    print_report("BATCH MODE (new — single JVM boot per batch)", batch_stats, n)

    # ── Comparison table ───────────────────────────────────────────────────────
    print_comparison(serial_stats, batch_stats, n)


if __name__ == "__main__":
    run_benchmark()
