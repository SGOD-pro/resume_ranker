#!/usr/bin/env python3
"""
scripts/run_v2_benchmark.py
===========================
Phase 3 V2 Extraction Pipeline Benchmark — Full Field Report

Tracks ALL extraction fields and calculates composite_score matching the V1
formula: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email

Changes from the previous version:
  1. No boto3 mock for Nova — uses the real Bedrock converse API.
  2. Tracks: name, email, phone, skills, experience, education.
  3. Composite score matches V1 formula.
  4. Prints individual PyMuPDF quality signals for the first 10 resumes
     so we can diagnose which signal is dragging the gate score down.
  5. Full routing breakdown + LLM fallback rate.

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

def _s3_side_effect(service_name, *args, **kwargs):
    """Intercept only 's3'; let everything else (including bedrock-runtime) pass through."""
    if service_name == "s3":
        mock_s3 = MagicMock()
        def fake_download(Bucket, Key, Filename, **_kw):
            shutil.copy(_current_pdf_path[0], Filename)
        mock_s3.download_file.side_effect = fake_download
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
# Main benchmark
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark():
    settings   = get_settings()
    pipeline   = ExtractionPipeline()
    resumes_dir = BACKEND_DIR / "data" / "resumes"

    if not resumes_dir.exists():
        print(f"ERROR: {resumes_dir} not found.")
        return

    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    # Filter out known garbage / celebrity lists starting with "cv ("
    valid_pdfs = [p for p in all_pdfs if not p.name.startswith("cv (")]
    pdfs = valid_pdfs[:50]
    n    = len(pdfs)
    print(f"\n{'═'*70}")
    print("  PHASE 3 V2 EXTRACTION BENCHMARK — Full Field Report")
    print(f"{'═'*70}")
    print(f"  Resumes: {n}   |   Quality threshold: {QUALITY_THRESHOLD}")
    print(f"  Nova: real Bedrock converse API (no mock)")

    # ── Signal diagnostics BEFORE the main loop ────────────────────────────────
    print_signal_diagnostics(pdfs)

    # ── Counters ───────────────────────────────────────────────────────────────
    pymupdf_only_count = 0
    odl_fallback_count = 0
    nova_fallback_count = 0
    nova_success_count  = 0   # Nova was called AND returned at least one new field
    total_quality       = 0.0

    field_counts: Dict[str, int] = {
        "name": 0, "email": 0, "phone": 0,
        "skills": 0, "experience": 0, "education": 0,
    }
    skill_total = 0
    exp_total   = 0
    edu_total   = 0
    composite_total = 0.0

    latencies: Dict[str, List[float]] = {
        "pymupdf_ms": [], "odl_ms": [], "nova_ms": [], "total_ms": [],
    }

    errors: List[str] = []

    print(f"\n{'─'*70}")
    print("  Running 50-resume benchmark…")
    print(f"{'─'*70}")

    job_id = f"bench-{uuid.uuid4().hex[:8]}"

    for i, pdf_path in enumerate(pdfs, 1):
        _current_pdf_path[0] = str(pdf_path)
        doc_id = str(uuid.uuid4())
        t_start = time.time()

        try:
            # S3 upload (mocked — just copies the file locally)
            from src.infrastructure.storage.storage_service import StorageService
            storage = StorageService()
            with open(pdf_path, "rb") as f:
                content = f.read()
            s3_key = storage.upload_resume(job_id, doc_id, content, pdf_path.name)

            # ── Run the full pipeline ─────────────────────────────────────────
            result = pipeline.run_pipeline(
                str(pdf_path), doc_id, settings.s3_bucket_name, s3_key
            )

            t_end = time.time()

            fields      = result.get("fields", {})
            stage_times = result.get("stage_timings", [])

            # ── Latency & pathing ─────────────────────────────────────────────
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

            total_ms = (t_end - t_start) * 1000

            if used_odl:
                odl_fallback_count += 1
                latencies["odl_ms"].append(odl_ms)
            else:
                pymupdf_only_count += 1
            if used_nova:
                nova_fallback_count += 1
                latencies["nova_ms"].append(nova_ms)

            latencies["pymupdf_ms"].append(pymupdf_ms)
            latencies["total_ms"].append(total_ms)
            total_quality += result.get("extraction_quality", 0.0)

            # ── Field presence ────────────────────────────────────────────────
            f_name = _has(fields.get("name"))
            f_email = _has(fields.get("email"))
            f_phone = _has(fields.get("phone"))
            f_skills = _has(fields.get("skills"))
            f_exp    = _has(fields.get("experience"))
            f_edu    = _has(fields.get("education"))

            if f_name:    field_counts["name"]       += 1
            if f_email:   field_counts["email"]      += 1
            if f_phone:   field_counts["phone"]      += 1
            if f_skills:  field_counts["skills"]     += 1
            if f_exp:     field_counts["experience"] += 1
            if f_edu:     field_counts["education"]  += 1

            # Avg list lengths (when present)
            skills_list = fields.get("skills") or []
            exp_list    = fields.get("experience") or []
            edu_list    = fields.get("education") or []
            if isinstance(skills_list, list): skill_total += len(skills_list)
            if isinstance(exp_list, list):    exp_total   += len(exp_list)
            if isinstance(edu_list, list):    edu_total   += len(edu_list)

            composite_total += _composite(f_name, f_email, f_skills, f_exp, f_edu)

        except Exception as exc:
            errors.append(f"{pdf_path.name}: {exc}")
            latencies["total_ms"].append((time.time() - t_start) * 1000)

        if i % 10 == 0 or i == n:
            print(f"    [{i:3d}/{n}] ODL={odl_fallback_count}  "
                  f"Nova={nova_fallback_count}  Err={len(errors)}")

    # ── Report ─────────────────────────────────────────────────────────────────
    processed = n - len(errors)
    avg_q = round(total_quality / processed, 3) if processed else 0.0
    avg_composite = round(composite_total / processed * 100, 1) if processed else 0.0

    py_p50, py_p95   = _p50_p95(latencies["pymupdf_ms"])
    odl_p50, odl_p95 = _p50_p95(latencies["odl_ms"])
    nov_p50, nov_p95 = _p50_p95(latencies["nova_ms"])
    tot_p50, tot_p95 = _p50_p95(latencies["total_ms"])

    print(f"\n{'='*70}")
    print("  === Phase 3 V2 Extraction Benchmark — Final Report ===")
    print(f"{'='*70}")
    print(f"  Total resumes:      {n}")
    print(f"  Processed OK:       {processed}")
    print(f"  Errors:             {len(errors)}")
    print(f"  Avg quality score:  {avg_q:.3f}  (threshold={QUALITY_THRESHOLD})")
    print()

    print("  ── Routing Breakdown ──────────────────────────────────────────────")
    print(f"  PyMuPDF-only:   {pymupdf_only_count:3d}  ({_pct(pymupdf_only_count, n):5.1f}%)")
    print(f"  ODL fallback:   {odl_fallback_count:3d}  ({_pct(odl_fallback_count, n):5.1f}%)")
    print(f"  Nova fallback:  {nova_fallback_count:3d}  ({_pct(nova_fallback_count, n):5.1f}%)")
    print()

    print("  ── Field Extraction (V1-compatible report) ────────────────────────")
    print(f"  {'Field':<12} {'Present':>8} {'Rate %':>8}  {'Avg/doc':>8}")
    print(f"  {'─'*44}")
    for fname in ("name", "email", "phone", "skills", "experience", "education"):
        cnt  = field_counts[fname]
        rate = _pct(cnt, processed)
        if fname == "skills":
            avg_s = round(skill_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_s:>8.1f}")
        elif fname == "experience":
            avg_e = round(exp_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_e:>8.1f}")
        elif fname == "education":
            avg_d = round(edu_total / processed, 1) if processed else 0.0
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%  {avg_d:>8.1f}")
        else:
            print(f"  {fname:<12} {cnt:>8} {rate:>8.1f}%")
    print()
    print(f"  Composite score:  {avg_composite:.1f}%")
    print(f"  Formula: 0.20×name + 0.25×skills + 0.25×experience + 0.20×education + 0.10×email")
    print()

    print("  ── Latency (ms) p50 / p95 ─────────────────────────────────────────")
    print(f"  PyMuPDF parse:  {py_p50:7.1f}  / {py_p95:7.1f}")
    print(f"  ODL parse:      {odl_p50:7.1f}  / {odl_p95:7.1f}  (n={len(latencies['odl_ms'])})")
    print(f"  Nova converse:  {nov_p50:7.1f}  / {nov_p95:7.1f}  (n={len(latencies['nova_ms'])})")
    print(f"  Total E2E:      {tot_p50:7.1f}  / {tot_p95:7.1f}")
    print()

    if errors:
        print("  ── Errors (first 5) ───────────────────────────────────────────────")
        for e in errors[:5]:
            print(f"  ⚠  {e[:100]}")
        print()

    print(f"{'='*70}\n")


if __name__ == "__main__":
    run_benchmark()
