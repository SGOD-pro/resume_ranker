#!/usr/bin/env python3
"""
scripts/run_v3_benchmark_e2e.py
==================================
E2E Benchmark for PDFPipelineV3 with LLM Fallback (Amazon Nova)
Generates comprehensive report: token usage, avg time/pdf, 3-layer extraction report, resource metrics, quality metrics.
"""

from __future__ import annotations

import os
import sys
import uuid
import random
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import resource

SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("src").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.ERROR)
logging.getLogger("boto3").setLevel(logging.ERROR)

from src.core.pipeline import PDFPipelineV3

def calc_composite(fields: Dict[str, Any]) -> float:
    # experience, name, phone, email, certifications, projects, skills
    score = 0.0
    personal = fields.get("personal_info", {})
    if personal.get("name") and personal.get("name") != "Unknown Candidate": score += 1.0
    if personal.get("email"): score += 1.0
    if personal.get("phone"): score += 1.0
    if fields.get("experience"): score += 1.0
    if fields.get("skills"): score += 1.0
    if fields.get("certifications"): score += 1.0
    if fields.get("projects"): score += 1.0
    return (score / 7.0) * 100.0

def run_benchmark():
    pipeline = PDFPipelineV3()
    resumes_dir = BACKEND_DIR / "data" / "resumes"

    all_pdfs = list(resumes_dir.glob("*.pdf"))
    if not all_pdfs:
        print(f"ERROR: {resumes_dir} has no PDFs.")
        return

    # Sample 200 PDFs for the benchmark
    random.seed(42)
    sample_size = min(200, len(all_pdfs))
    pdfs = random.sample(all_pdfs, sample_size)
    n = len(pdfs)
    
    print(f"\n{'═'*80}")
    print(f"  PHASE 4 V3 EXTRACTION E2E BENCHMARK (With LLM Fallback) — {sample_size} Resumes")
    print(f"{'═'*80}")

    stats = {
        "v3_only": {"count": 0, "scores": []},
        "nova_fallback": {"count": 0, "scores": []},
    }

    field_counts = {
        "name": 0, "email": 0, "phone": 0,
        "skills": 0, "experience": 0, "certifications": 0, "projects": 0
    }
    
    total_ms = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    nova_calls = 0

    max_rss_kb = 0

    for i, pdf_path in enumerate(pdfs, 1):
        t_start = time.time()
        try:
            result = pipeline.extract(str(pdf_path))
            dur = (time.time() - t_start) * 1000
            total_ms += dur

            fields = result.fields
            
            used_nova = fields.get("_nova_time_ms", 0) > 0
                
            score = calc_composite(fields)
            
            if used_nova:
                stats["nova_fallback"]["count"] += 1
                stats["nova_fallback"]["scores"].append(score)
            else:
                stats["v3_only"]["count"] += 1
                stats["v3_only"]["scores"].append(score)
                
            personal = fields.get("personal_info", {})
            for k in field_counts:
                if k in ["name", "email", "phone"]:
                    if personal.get(k) and personal.get(k) != "Unknown Candidate":
                        field_counts[k] += 1
                elif fields.get(k):
                    field_counts[k] += 1
                    
            tokens = fields.get("_nova_tokens", {})
            if tokens:
                total_input_tokens += tokens.get("inputTokens", 0)
                total_output_tokens += tokens.get("outputTokens", 0)
                nova_calls += 1
                
            print(f"[{i:2}/{n}] {pdf_path.name[:25]:<25} | Score: {score:5.1f}% | Nova: {'Y' if used_nova else 'N'} | {dur:4.0f}ms")

            # track max memory
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if usage > max_rss_kb:
                max_rss_kb = usage

        except Exception as e:
            print(f"[{i:2}/{n}] {pdf_path.name[:25]:<25} | ERROR: {e}")

    print(f"\n{'═'*80}")
    print("  FINAL REPORT MATRIX")
    print(f"{'═'*80}")
    print(f"Total Resumes Sampled: {n}")
    print(f"Avg Processing Time / PDF: {total_ms / n:.0f} ms")
    print(f"Peak Memory Usage (Max RSS): {max_rss_kb / 1024:.1f} MB")
    
    print("\n── Route Quality Breakdown ──────────")
    for route in ["v3_only", "nova_fallback"]:
        c = stats[route]["count"]
        pct = (c / n) * 100
        avg_score = sum(stats[route]["scores"]) / c if c > 0 else 0
        print(f"{route.upper():<14}: {c:>2} ({pct:>5.1f}%) | Avg Score: {avg_score:>5.1f}%")
        
    print("\n── 3-Layer PDF Extraction Quality Matrix ────────")
    for f, count in field_counts.items():
        print(f"{f:<14}: {count:>2}/{n} ({count/n*100:>5.1f}%)")
        
    print("\n── LLM Token Usage ──────────────────")
    print(f"Total Input Tokens : {total_input_tokens}")
    print(f"Total Output Tokens: {total_output_tokens}")
    total_tokens = total_input_tokens + total_output_tokens
    print(f"Total Tokens       : {total_tokens}")
    avg_tokens = (total_tokens / nova_calls) if nova_calls > 0 else 0
    print(f"Avg Tokens / PDF   : {avg_tokens:.1f} (per LLM call)")
    print(f"Total LLM Fallbacks: {nova_calls}")
    
    overall_score = sum(stats["v3_only"]["scores"] + stats["nova_fallback"]["scores"]) / n if n > 0 else 0
    print(f"\nOVERALL COMPOSITE SCORE: {overall_score:.1f}%")

if __name__ == "__main__":
    run_benchmark()
