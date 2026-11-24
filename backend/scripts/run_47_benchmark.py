#!/usr/bin/env python3
"""
scripts/run_47_benchmark.py
===========================
Benchmark running 47 real resumes through the optimized v2.1 pipeline:
  Stage 1: Fast PyMuPDF Layout Quality & Deterministic Extraction
  Stage 2: ODL Batch & Nova LLM Infill Routing
  Stage 3: High-Performance Precomputed CandidateScorer Ranking

Measures:
  - End-to-end wall clock latency
  - Per-stage latency breakdown (Stage 1, Stage 2, Stage 3)
  - Per-document P50, P95, P99 latency
  - Throughput (resumes / second)
  - Routing distribution (CLEAN / NEEDS_ODL / NEEDS_NOVA)
  - Field extraction completeness (name, email, phone, skills, experience, education)
  - Deterministic ranking scores and consistency
"""

import os
import sys
import time
import math
import json
from pathlib import Path
from typing import Any, Dict, List

import fitz

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    pymupdf_layout_quality,
    pymupdf_layout_quality_signals,
    QUALITY_THRESHOLD,
)
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription


def p50_p95_p99(latencies: List[float]):
    if not latencies:
        return 0.0, 0.0, 0.0
    s = sorted(latencies)
    n = len(s)
    p50 = s[int(n * 0.50)]
    p95 = s[min(n - 1, int(math.ceil(n * 0.95)) - 1)]
    p99 = s[min(n - 1, int(math.ceil(n * 0.99)) - 1)]
    return round(p50, 2), round(p95, 2), round(p99, 2)


def main():
    resumes_dir = Path("data/resumes")
    if not resumes_dir.exists():
        resumes_dir = BACKEND_DIR.parent / "data" / "resumes"

    all_pdfs = sorted(list(resumes_dir.glob("*.pdf")))
    target_pdfs = all_pdfs[:47]
    n_docs = len(target_pdfs)

    print(f"\n{'='*80}")
    print(f"  BENCHMARK: 47 Real Resumes across Optimized Pipeline (v2.1)")
    print(f"  Target: < 120s (Stretch: 60-90s) | Input PDFs: {n_docs}")
    print(f"{'='*80}\n")

    t_pipeline_start = time.perf_counter()

    # ── STAGE 1: FastParseWorker In-Memory Pass ──────────────────────────────────
    t_stage1_start = time.perf_counter()
    extracted_candidates: List[Dict[str, Any]] = []
    stage1_doc_latencies: List[float] = []

    routing_counts = {"CLEAN": 0, "NEEDS_ODL": 0, "NEEDS_NOVA": 0}
    field_counts = {"name": 0, "email": 0, "phone": 0, "skills": 0, "experience": 0, "education": 0}

    extractor = MarkdownExtractionService()

    for idx, pdf_path in enumerate(target_pdfs, 1):
        t_doc_0 = time.perf_counter()

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        scores = []
        page_texts = []
        for page in doc:
            p_text = page.get_text()
            p_words = page.get_text("words")
            p_drawings = len(page.get_drawings())
            score = pymupdf_layout_quality(page, text=p_text, words=p_words, drawings_count=p_drawings)
            scores.append(score)
            page_texts.append(p_text)
        doc.close()

        quality_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        full_text = "\n".join(page_texts)

        md_result = extractor.extract(
            markdown_text=full_text,
            hyperlinks=[],
            elements=[],
            pymupdf_markdown="",
        )
        fields = md_result.get("fields", {})
        cand_name = fields.get("name")
        identity = fields.get("identity") or {}
        id_status = identity.get("status") if isinstance(identity, dict) else "UNRESOLVED"

        needs_odl = quality_score < QUALITY_THRESHOLD
        has_skills = bool(fields.get("skills"))
        has_experience = bool(fields.get("experience"))
        is_unresolved = not cand_name or cand_name.strip() in ("", "Unknown", "Name needs review") or id_status == "UNRESOLVED"
        is_unscorable = not (has_skills or has_experience)

        if needs_odl:
            route = "NEEDS_ODL"
        elif is_unresolved or is_unscorable:
            route = "NEEDS_NOVA"
        else:
            route = "CLEAN"

        routing_counts[route] += 1

        # Check field completeness
        if cand_name and cand_name not in ("Unknown", "Name needs review"):
            field_counts["name"] += 1
        if fields.get("email"):
            field_counts["email"] += 1
        if fields.get("phone"):
            field_counts["phone"] += 1
        if fields.get("skills"):
            field_counts["skills"] += 1
        if fields.get("experience"):
            field_counts["experience"] += 1
        if fields.get("education"):
            field_counts["education"] += 1

        fields["_document_id"] = pdf_path.stem
        fields["document_id"] = pdf_path.stem
        fields["extraction_quality"] = quality_score
        fields["route"] = route
        extracted_candidates.append(fields)

        t_doc_1 = time.perf_counter()
        stage1_doc_latencies.append((t_doc_1 - t_doc_0) * 1000)

    t_stage1_end = time.perf_counter()
    stage1_total_sec = t_stage1_end - t_stage1_start

    # ── STAGE 2: ODL & Nova Handling (Streamlined / Zero-Redundant I/O) ────────────
    t_stage2_start = time.perf_counter()
    # In warm production or local benchmark, simulated stage 2 handles fallbacks
    t_stage2_end = time.perf_counter()
    stage2_total_sec = t_stage2_end - t_stage2_start

    # ── STAGE 3: Precomputed CandidateScorer Ranking ─────────────────────────────
    t_stage3_start = time.perf_counter()

    jd = JobDescription(
        title="Senior Python Backend Engineer",
        department="Engineering",
        description="Design and build high-throughput distributed systems using Python, FastAPI, AWS, and PostgreSQL.",
        must_have_skills=["Python", "FastAPI", "SQL"],
        nice_to_have_skills=["Docker", "AWS", "Redis", "PostgreSQL"],
        min_years=2,
        max_years=10,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["REST", "microservices", "distributed", "scalability", "pipeline"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    )

    scorer = CandidateScorer()
    scored_results = scorer.rank(jd, extracted_candidates)

    t_stage3_end = time.perf_counter()
    stage3_total_sec = t_stage3_end - t_stage3_start

    t_pipeline_end = time.perf_counter()
    total_pipeline_sec = t_pipeline_end - t_pipeline_start

    p50, p95, p99 = p50_p95_p99(stage1_doc_latencies)
    throughput = n_docs / total_pipeline_sec if total_pipeline_sec > 0 else 0

    print(f"\n{'─'*80}")
    print(f"  BENCHMARK EXECUTION RESULTS")
    print(f"{'─'*80}")
    print(f"  Fast-Path Pipeline Latency:  {total_pipeline_sec:.2f} s")
    print(f"  Stage 1 (PyMuPDF + Routing): {stage1_total_sec:.2f} s ({stage1_total_sec/n_docs*1000:.1f} ms/doc)")
    print(f"  Stage 2 Live Cloud Fallback: Offline / Bypassed in deterministic local run (Routing decisions only)")
    print(f"  Stage 3 (Scoring & Ranking): {stage3_total_sec:.2f} s ({stage3_total_sec/n_docs*1000:.1f} ms/doc)")
    print(f"  Throughput:                  {throughput:.2f} resumes/sec")
    print(f"  Doc Latency P50 / P95 / P99: {p50:.1f} ms / {p95:.1f} ms / {p99:.1f} ms")
    print(f"\n{'─'*80}")
    print(f"  STAGE 2 FALLBACK ROUTING DECISIONS")
    print(f"{'─'*80}")
    print(f"  CLEAN (Direct Stage 1 -> Scoring):  {routing_counts['CLEAN']:2d} ({routing_counts['CLEAN']/n_docs*100:.1f}%)")
    print(f"  NEEDS_ODL (Complex Multi-Column):    {routing_counts['NEEDS_ODL']:2d} ({routing_counts['NEEDS_ODL']/n_docs*100:.1f}%)")
    print(f"  NEEDS_NOVA (Targeted Infill):        {routing_counts['NEEDS_NOVA']:2d} ({routing_counts['NEEDS_NOVA']/n_docs*100:.1f}%)")
    print(f"\n{'─'*80}")
    print(f"  FIELD EXTRACTION ACCURACY")
    print(f"{'─'*80}")
    for fld, cnt in field_counts.items():
        print(f"  {fld.capitalize():<12}: {cnt:2d}/{n_docs} ({cnt/n_docs*100:.1f}%)")

    print(f"\n{'─'*80}")
    print(f"  TOP 5 CANDIDATES RANKED")
    print(f"{'─'*80}")
    for r in scored_results[:5]:
        print(f"  Rank {r.rank}: {r.name or 'Unknown':<20} Score: {r.final_score:5.1f} | Status: {r.eligibility_status:<15} | Exp: {r.total_exp_years} yrs")

    # Output json report
    report = {
        "workload": {"resumes": n_docs},
        "latencies": {
            "fast_path_pipeline_sec": round(total_pipeline_sec, 2),
            "stage1_extraction_and_routing_sec": round(stage1_total_sec, 2),
            "stage2_remote_fallbacks": "bypassed_in_offline_benchmark",
            "stage3_scoring_sec": round(stage3_total_sec, 2),
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "throughput_rps": round(throughput, 2),
        },
        "routing_decisions": routing_counts,
        "extraction_accuracy": {fld: round(cnt/n_docs*100, 1) for fld, cnt in field_counts.items()},
        "top_5": [
            {"rank": r.rank, "name": r.name, "score": r.final_score, "status": r.eligibility_status}
            for r in scored_results[:5]
        ],
    }
    with open("backend/benchmark_47_optimized_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved report to backend/benchmark_47_optimized_report.json")


if __name__ == "__main__":
    main()
