#!/usr/bin/env python3
"""
scripts/run_1k_benchmark.py — 1,000 PDF Resumes High-Performance Benchmark
==========================================================================
Measures:
1. Stage 1 PyMuPDF In-Memory Extraction Latency (Mean, Median P50, P90, P95, P99, Throughput).
2. Field Extraction Coverage (Name, Skills, Experience, Education, Email, Phone, Location, etc.).
3. Structural Layout Quality Analysis & Routing Decisions (Clean Fast-Path vs Fallback Required).
4. Full-Pool Ranking Scorer Performance (BM25, TF-IDF, Composite scoring across 1,000 candidates).
5. Multithreaded Concurrent Throughput across 8 worker threads.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Suppress external noise
logging.basicConfig(level=logging.WARNING)
for noisy in ("botocore", "boto3", "urllib3", "fitz"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

import fitz
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    QUALITY_THRESHOLD,
    pymupdf_layout_quality_signals,
)
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription, ScoredCandidate


def process_single_resume(
    pdf_path: Path,
    extractor: MarkdownExtractionService,
) -> Dict[str, Any]:
    """Parse a single PDF in-memory and return timing + extracted metrics."""
    t0 = time.perf_counter()

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    read_time_ms = (time.perf_counter() - t0) * 1000.0

    t_parse_start = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts: List[str] = []
    page_signals: List[Dict[str, Any]] = []

    for page in doc:
        page_texts.append(page.get_text())
        try:
            page_signals.append(pymupdf_layout_quality_signals(page))
        except Exception:
            pass
    page_count = len(doc)
    doc.close()

    raw_text = "\n\n".join(page_texts)

    # Layout quality
    min_quality = min((p["score"] for p in page_signals), default=1.0) if page_signals else 1.0
    min_ro = min((p["reading_order"] for p in page_signals), default=1.0) if page_signals else 1.0
    looks_tabular = any(p.get("not_table_heavy") == 0.0 for p in page_signals)

    # Deterministic field extraction
    extracted = extractor.extract(raw_text, pymupdf_markdown=raw_text)
    fields = extracted.get("fields", {})
    candidate_name = fields.get("name")
    unresolved = extracted.get("unresolved_chunks", [])

    has_valid_name = (
        bool(candidate_name)
        and str(candidate_name).strip().lower() not in ("candidate", "unknown", "", "none")
    )
    has_skills = bool(fields.get("skills")) and len(fields.get("skills")) > 0
    has_experience = bool(fields.get("experience")) and len(fields.get("experience")) > 0
    has_education = bool(fields.get("education")) and len(fields.get("education")) > 0
    has_email = bool(fields.get("email"))
    has_phone = bool(fields.get("phone"))
    has_location = bool(fields.get("location"))
    has_linkedin = bool(fields.get("linkedin"))
    has_github = bool(fields.get("github"))

    skills_count = len(fields.get("skills") or [])
    exp_count = len(fields.get("experience") or [])
    edu_count = len(fields.get("education") or [])

    # Routing determination (matching Stage 1 worker)
    needs_fallback = (
        (min_quality < QUALITY_THRESHOLD)
        or bool(unresolved)
        or not has_valid_name
        or not has_experience
    )

    t_end = time.perf_counter()
    total_time_ms = (t_end - t0) * 1000.0
    parse_time_ms = (t_end - t_parse_start) * 1000.0

    return {
        "filename": pdf_path.name,
        "file_size_kb": len(pdf_bytes) / 1024.0,
        "page_count": page_count,
        "total_time_ms": total_time_ms,
        "parse_time_ms": parse_time_ms,
        "quality_score": min_quality,
        "reading_order_score": min_ro,
        "looks_tabular": looks_tabular,
        "candidate_name": candidate_name,
        "has_valid_name": has_valid_name,
        "has_skills": has_skills,
        "skills_count": skills_count,
        "has_experience": has_experience,
        "experience_count": exp_count,
        "has_education": has_education,
        "education_count": edu_count,
        "has_email": has_email,
        "has_phone": has_phone,
        "has_location": has_location,
        "has_linkedin": has_linkedin,
        "has_github": has_github,
        "needs_fallback": needs_fallback,
        "fields": fields,
    }


def main():
    corpus_dir = PROJECT_ROOT / "data" / "resumes"
    if not corpus_dir.exists():
        corpus_dir = BACKEND_DIR / "data" / "resumes"

    all_pdfs = sorted(list(corpus_dir.glob("*.pdf")))
    if not all_pdfs:
        print(f"Error: No PDFs found in {corpus_dir}")
        sys.exit(1)

    TOTAL_TARGET = 1000
    random.seed(42)  # Deterministic 1,000 resume sample
    if len(all_pdfs) >= TOTAL_TARGET:
        selected_pdfs = random.sample(all_pdfs, TOTAL_TARGET)
    else:
        print(f"Warning: Only {len(all_pdfs)} PDFs available, using all.")
        selected_pdfs = all_pdfs

    actual_count = len(selected_pdfs)

    extractor = MarkdownExtractionService()
    concurrency = min(16, os.cpu_count() or 8)

    print("=" * 80)
    print(f"  SWYRA SORTLIST V2 — 1,000 PDF RESUME EXTRACTION & SCORING BENCHMARK")
    print(f"  Target Sample: {actual_count} Resumes | Corpus Pool: {len(all_pdfs)} PDFs")
    print(f"  Concurrency: {concurrency} Worker Threads")
    print("=" * 80)
    print()
    cache_path = BACKEND_DIR / "_1k_extracted_cache.json"
    results: List[Dict[str, Any]] = []

    loaded_from_cache = False
    if cache_path.exists() and cache_path.stat().st_size > 10 and "--force" not in sys.argv:
        try:
            print(f"[*] Found existing cached extraction at {cache_path}, loading...")
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
                wall_clock_seconds = cached["wall_clock_seconds"]
                results = cached["results"]
            print(f"[+] Loaded {len(results)} parsed resumes from cache (Wall-clock: {wall_clock_seconds:.2f}s).")
            loaded_from_cache = True
        except Exception as e:
            print(f"[-] Could not load cache ({e}), re-running extraction...")

    if not loaded_from_cache:
        # Benchmark Execution with Multithreading
        start_wall_time = time.perf_counter()

        print(f"[*] Starting extraction of {actual_count} resumes across {concurrency} concurrent workers...")
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="bench-worker") as executor:
            future_map = {
                executor.submit(process_single_resume, pdf_path, extractor): pdf_path
                for pdf_path in selected_pdfs
            }

            completed_count = 0
            for future in as_completed(future_map):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    path = future_map[future]
                    print(f"[-] Error processing {path.name}: {exc}")

                completed_count += 1
                if completed_count % 100 == 0 or completed_count == actual_count:
                    now = time.perf_counter()
                    batch_sec = now - start_wall_time
                    rps = completed_count / batch_sec if batch_sec > 0 else 0
                    print(f"    Progress: {completed_count}/{actual_count} ({completed_count / actual_count * 100:.1f}%) | "
                          f"Elapsed: {batch_sec:.1f}s | Current Speed: {rps:.1f} resumes/sec")

        end_wall_time = time.perf_counter()
        wall_clock_seconds = end_wall_time - start_wall_time
        # Cache results
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"wall_clock_seconds": wall_clock_seconds, "results": results}, f)
        print(f"[+] Cached extraction results to: {cache_path}")


    # Compute Latency Metrics
    latencies = [r["total_time_ms"] for r in results]
    parse_latencies = [r["parse_time_ms"] for r in results]
    page_counts = [r["page_count"] for r in results]
    file_sizes = [r["file_size_kb"] for r in results]

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)

    mean_latency = statistics.mean(latencies)
    median_latency = statistics.median(latencies)
    stdev_latency = statistics.stdev(latencies) if n > 1 else 0.0
    p90_latency = latencies_sorted[int(0.90 * n)]
    p95_latency = latencies_sorted[int(0.95 * n)]
    p99_latency = latencies_sorted[int(0.99 * n)]
    min_latency = latencies_sorted[0]
    max_latency = latencies_sorted[-1]
    effective_rps = n / wall_clock_seconds if wall_clock_seconds > 0 else 0

    # Field Accuracy / Coverage Metrics
    valid_name_count = sum(1 for r in results if r["has_valid_name"])
    skills_count = sum(1 for r in results if r["has_skills"])
    exp_count = sum(1 for r in results if r["has_experience"])
    edu_count = sum(1 for r in results if r["has_education"])
    email_count = sum(1 for r in results if r["has_email"])
    phone_count = sum(1 for r in results if r["has_phone"])
    location_count = sum(1 for r in results if r["has_location"])
    linkedin_count = sum(1 for r in results if r["has_linkedin"])
    github_count = sum(1 for r in results if r["has_github"])

    avg_skills_per_resume = statistics.mean([r["skills_count"] for r in results])
    avg_exp_per_resume = statistics.mean([r["experience_count"] for r in results])
    avg_edu_per_resume = statistics.mean([r["education_count"] for r in results])

    # Routing Decisions
    clean_fastpath_count = sum(1 for r in results if not r["needs_fallback"])
    fallback_count = sum(1 for r in results if r["needs_fallback"])

    # High quality vs complex layout
    high_qual_count = sum(1 for r in results if r["quality_score"] >= QUALITY_THRESHOLD)
    tabular_count = sum(1 for r in results if r["looks_tabular"])

    # ── FULL-POOL CANDIDATE RANKING BENCHMARK ──────────────────────────────────
    print()
    print(f"[*] Running CandidateScorer across all {n} parsed resumes against standard Job Description...")
    jd = JobDescription(
        title="Senior Full Stack Software Engineer",
        must_have_skills=["Python", "React", "TypeScript", "SQL", "Docker"],
        nice_to_have_skills=["AWS", "FastAPI", "GraphQL", "Redis", "Kubernetes"],
        min_years=3,
        max_years=8,
        required_degree="bachelor",
        preferred_field="Computer Science",
        keywords=["REST", "CI/CD", "Agile", "Architecture", "Microservices"],
        weights={
            "skills": 40.0,
            "experience": 25.0,
            "keywords": 20.0,
            "education": 15.0,
        },
    )

    candidate_records = []
    for idx, r in enumerate(results):
        c_fields = r["fields"]
        candidate_records.append({
            "candidate_id": f"cand_{idx:04d}",
            "document_id": f"doc_{idx:04d}",
            "name": c_fields.get("name") or f"Candidate {idx+1}",
            "skills": c_fields.get("skills") or [],
            "experience": c_fields.get("experience") or [],
            "education": c_fields.get("education") or [],
            "projects": c_fields.get("projects") or [],
            "raw_text": f"{c_fields.get('name', '')} {' '.join(c_fields.get('skills') or [])}",
        })

    scorer = CandidateScorer()
    t_score_start = time.perf_counter()
    ranked_candidates: List[ScoredCandidate] = scorer.rank(
        jd=jd,
        candidates=candidate_records,
    )
    t_score_end = time.perf_counter()
    scoring_duration_ms = (t_score_end - t_score_start) * 1000.0

    scores = [c.final_score for c in ranked_candidates]
    avg_score = statistics.mean(scores)
    max_score = max(scores)
    min_score = min(scores)

    signals_count = {"strong": 0, "good": 0, "fair": 0, "knockout": 0}
    for c in ranked_candidates:
        if c.knocked_out:
            sig = "knockout"
        elif c.final_score >= 80.0:
            sig = "strong"
        elif c.final_score >= 60.0:
            sig = "good"
        else:
            sig = "fair"
        signals_count[sig] = signals_count.get(sig, 0) + 1

    # ── PRINT CONCISE BENCHMARK REPORT ─────────────────────────────────────────
    print()
    print("=" * 80)
    print("                      BENCHMARK RESULTS REPORT (1,000 RESUMES)")
    print("=" * 80)
    print()
    print("1. LATENCY & THROUGHPUT METRICS")
    print("─" * 80)
    print(f"  • Total Resumes Processed   : {n:,}")
    print(f"  • Total Wall-Clock Time     : {wall_clock_seconds:.2f} seconds ({wall_clock_seconds/60:.2f} minutes)")
    print(f"  • Effective Throughput      : {effective_rps:.2f} resumes / second ({effective_rps * 60:,.0f} resumes/minute)")
    print(f"  • Mean Latency per Document : {mean_latency:.2f} ms")
    print(f"  • Median (P50) Latency      : {median_latency:.2f} ms")
    print(f"  • P90 Latency               : {p90_latency:.2f} ms")
    print(f"  • P95 Latency               : {p95_latency:.2f} ms")
    print(f"  • P99 Latency               : {p99_latency:.2f} ms")
    print(f"  • Min / Max Latency         : {min_latency:.2f} ms / {max_latency:.2f} ms")
    print(f"  • Std Deviation             : {stdev_latency:.2f} ms")
    print()
    print("2. EXTRACTION QUALITY & COVERAGE (1,000 RESUMES)")
    print("─" * 80)
    print(f"  • Human Name Validated      : {valid_name_count:4d} / {n} ({valid_name_count / n * 100:5.1f}%)")
    print(f"  • Skills Extracted          : {skills_count:4d} / {n} ({skills_count / n * 100:5.1f}%) [Avg {avg_skills_per_resume:.1f} skills/resume]")
    print(f"  • Experience Extracted      : {exp_count:4d} / {n} ({exp_count / n * 100:5.1f}%) [Avg {avg_exp_per_resume:.1f} roles/resume]")
    print(f"  • Education Extracted       : {edu_count:4d} / {n} ({edu_count / n * 100:5.1f}%) [Avg {avg_edu_per_resume:.1f} degrees/resume]")
    print(f"  • Email Address Found       : {email_count:4d} / {n} ({email_count / n * 100:5.1f}%)")
    print(f"  • Phone Number Found        : {phone_count:4d} / {n} ({phone_count / n * 100:5.1f}%)")
    print(f"  • Location Detected         : {location_count:4d} / {n} ({location_count / n * 100:5.1f}%)")
    print(f"  • LinkedIn Profile Detected : {linkedin_count:4d} / {n} ({linkedin_count / n * 100:5.1f}%)")
    print(f"  • GitHub Profile Detected   : {github_count:4d} / {n} ({github_count / n * 100:5.1f}%)")
    print()
    print("3. PIPELINE ROUTING & ARCHITECTURAL GATING")
    print("─" * 80)
    print(f"  • Clean Fast-Path (S2_DONE) : {clean_fastpath_count:4d} / {n} ({clean_fastpath_count / n * 100:5.1f}%)")
    print(f"  • Stage 2 Fallback Required : {fallback_count:4d} / {n} ({fallback_count / n * 100:5.1f}%)")
    print(f"    - Multi-column / Tabular  : {tabular_count:4d} / {n} ({tabular_count / n * 100:5.1f}%)")
    print(f"    - High Layout Quality     : {high_qual_count:4d} / {n} ({high_qual_count / n * 100:5.1f}%)")
    print()
    print("4. RANKING SCORER BENCHMARK (1,000 CANDIDATES)")
    print("─" * 80)
    print(f"  • Total Scoring Duration    : {scoring_duration_ms:.2f} ms ({scoring_duration_ms / 1000.0:.3f} s)")
    print(f"  • Scoring Latency / Cand.   : {scoring_duration_ms / n:.3f} ms / candidate")
    print(f"  • Scoring Throughput        : {n / (scoring_duration_ms / 1000.0):,.0f} candidates / second")
    print(f"  • Score Range               : Min {min_score:.1f} | Avg {avg_score:.1f} | Max {max_score:.1f}")
    print(f"  • Signal Distribution       : Strong={signals_count.get('strong', 0)}, Good={signals_count.get('good', 0)}, Fair={signals_count.get('fair', 0)}, Knockout={signals_count.get('knockout', 0)}")
    print("=" * 80)

    # Save summary report to JSON
    summary_path = BACKEND_DIR / "benchmark_1k_results.json"
    summary_data = {
        "dataset": {
            "total_evaluated": n,
            "corpus_dir": str(corpus_dir),
            "seed": 42,
            "avg_page_count": statistics.mean(page_counts),
            "avg_file_size_kb": statistics.mean(file_sizes),
        },
        "latency_metrics": {
            "wall_clock_seconds": wall_clock_seconds,
            "throughput_resumes_per_sec": effective_rps,
            "mean_ms": mean_latency,
            "median_p50_ms": median_latency,
            "p90_ms": p90_latency,
            "p95_ms": p95_latency,
            "p99_ms": p99_latency,
            "min_ms": min_latency,
            "max_ms": max_latency,
            "stdev_ms": stdev_latency,
        },
        "extraction_coverage": {
            "valid_name_rate": valid_name_count / n,
            "skills_rate": skills_count / n,
            "avg_skills_count": avg_skills_per_resume,
            "experience_rate": exp_count / n,
            "avg_experience_count": avg_exp_per_resume,
            "education_rate": edu_count / n,
            "avg_education_count": avg_edu_per_resume,
            "email_rate": email_count / n,
            "phone_rate": phone_count / n,
            "location_rate": location_count / n,
            "linkedin_rate": linkedin_count / n,
            "github_rate": github_count / n,
        },
        "routing_breakdown": {
            "clean_fastpath_count": clean_fastpath_count,
            "clean_fastpath_rate": clean_fastpath_count / n,
            "fallback_required_count": fallback_count,
            "fallback_required_rate": fallback_count / n,
            "tabular_detected_count": tabular_count,
        },
        "scoring_benchmark": {
            "total_candidates": n,
            "duration_ms": scoring_duration_ms,
            "throughput_cands_per_sec": n / (scoring_duration_ms / 1000.0),
            "avg_score": avg_score,
            "signal_distribution": signals_count,
        },
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    print(f"\n[+] Detailed benchmark report saved to: {summary_path}")


if __name__ == "__main__":
    main()
