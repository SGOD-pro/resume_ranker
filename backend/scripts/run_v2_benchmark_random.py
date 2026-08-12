#!/usr/bin/env python3
"""
scripts/run_v2_benchmark_random.py
==================================
Phase 3 V2 Extraction Benchmark — Random 60 resumes from full 3.8k corpus.
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

from unittest.mock import patch, MagicMock

_current_pdf_path: List[str] = [""]

# Removed S3 mock so we can use real AWS S3 for the benchmark.

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.config.aws import get_settings

def calc_composite(fields: Dict[str, Any]) -> float:
    # experience, name, phone, email, certificates, projects, skills
    # Let's give equal weighting to all 7: ~14.28% each for the report matrix
    score = 0.0
    if fields.get("name"): score += 1.0
    if fields.get("email"): score += 1.0
    if fields.get("phone"): score += 1.0
    if fields.get("experience"): score += 1.0
    if fields.get("skills"): score += 1.0
    if fields.get("certificates"): score += 1.0
    if fields.get("projects"): score += 1.0
    return (score / 7.0) * 100.0

def run_benchmark():
    settings = get_settings()
    pipeline = ExtractionPipeline()
    resumes_dir = BACKEND_DIR / "data" / "resumes"

    all_pdfs = list(resumes_dir.glob("*.pdf"))
    if not all_pdfs:
        print(f"ERROR: {resumes_dir} has no PDFs.")
        return

    random.seed(42)  # For reproducibility if desired
    pdfs = random.sample(all_pdfs, min(200, len(all_pdfs)))
    n = len(pdfs)

    print(f"\n{'═'*80}")
    print(f"  PHASE 3 V2 EXTRACTION BENCHMARK — Random Sample ({n} Resumes)")
    print(f"{'═'*80}")

    stats = {
        "pymupdf_only": {"count": 0, "scores": []},
        "odl": {"count": 0, "scores": []},
        "nova": {"count": 0, "scores": []},
    }

    field_counts = {
        "name": 0, "email": 0, "phone": 0,
        "skills": 0, "experience": 0, "certificates": 0, "projects": 0
    }
    
    total_ms = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    nova_calls_with_tokens = 0

    job_id = f"bench-{uuid.uuid4().hex[:8]}"

    import boto3
    session = boto3.Session(profile_name="aws", region_name="ap-south-1")
    s3_client = session.client("s3")

    for i, pdf_path in enumerate(pdfs, 1):
        _current_pdf_path[0] = str(pdf_path)
        doc_id = str(uuid.uuid4())
        
        t_start = time.time()
        try:
            s3_key = f"jobs/{job_id}/resumes/{doc_id}.pdf"
            s3_client.upload_file(
                str(pdf_path), 
                settings.s3_bucket_name, 
                s3_key,
                ExtraArgs={'ACL': 'bucket-owner-full-control'}
            )

            result = pipeline.run_pipeline(str(pdf_path), doc_id, settings.s3_bucket_name, s3_key)
            dur = (time.time() - t_start) * 1000
            total_ms += dur

            fields = result.get("fields", {})
            stage_times = result.get("stage_timings", [])
            
            used_odl = False
            used_nova = False
            for t in stage_times:
                if t.get("stage") == "odl_parse": used_odl = True
                if t.get("stage") == "nova_fallback": used_nova = True
                
            score = calc_composite(fields)
            
            if used_nova:
                stats["nova"]["count"] += 1
                stats["nova"]["scores"].append(score)
            elif used_odl:
                stats["odl"]["count"] += 1
                stats["odl"]["scores"].append(score)
            else:
                stats["pymupdf_only"]["count"] += 1
                stats["pymupdf_only"]["scores"].append(score)
                
            for k in field_counts:
                if fields.get(k):
                    field_counts[k] += 1
                    
            tokens = fields.get("_nova_tokens", {})
            if tokens:
                total_input_tokens += tokens.get("inputTokens", 0)
                total_output_tokens += tokens.get("outputTokens", 0)
                nova_calls_with_tokens += 1
                
            print(f"[{i:2}/{n}] {pdf_path.name[:25]:<25} | Score: {score:5.1f}% | ODL: {'Y' if used_odl else 'N'} | Nova: {'Y' if used_nova else 'N'} | {dur:4.0f}ms")

        except Exception as e:
            print(f"[{i:2}/{n}] {pdf_path.name[:25]:<25} | ERROR: {e}")

    print(f"\n{'═'*80}")
    print("  FINAL REPORT MATRIX")
    print(f"{'═'*80}")
    print(f"Total Resumes Sampled: {n}")
    print(f"Avg Processing Time / PDF: {total_ms / n:.0f} ms")
    
    print("\n── Route Quality Breakdown ──────────")
    for route in ["pymupdf_only", "odl", "nova"]:
        c = stats[route]["count"]
        pct = (c / n) * 100
        avg_score = sum(stats[route]["scores"]) / c if c > 0 else 0
        print(f"{route.upper():<14}: {c:>2} ({pct:>5.1f}%) | Avg Score: {avg_score:>5.1f}%")
        
    print("\n── Extraction Quality Matrix ────────")
    for f, count in field_counts.items():
        print(f"{f:<14}: {count:>2}/{n} ({count/n*100:>5.1f}%)")
        
    print("\n── LLM Token Usage ──────────────────")
    print(f"Total Input Tokens : {total_input_tokens}")
    print(f"Total Output Tokens: {total_output_tokens}")
    total_tokens = total_input_tokens + total_output_tokens
    print(f"Total Tokens       : {total_tokens}")
    avg_tokens = (total_tokens / nova_calls_with_tokens) if nova_calls_with_tokens > 0 else 0
    print(f"Avg Tokens / PDF   : {avg_tokens:.1f} (per LLM call)")

if __name__ == "__main__":
    run_benchmark()
