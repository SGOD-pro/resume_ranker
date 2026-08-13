#!/usr/bin/env python3
import os
import sys
import random
import time
from pathlib import Path
import logging

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.getLogger().setLevel(logging.ERROR)

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.core.pipeline import PDFPipelineV3

def calc_composite_v2(fields):
    score = 0.0
    if fields.get("name"): score += 1.0
    if fields.get("email"): score += 1.0
    if fields.get("phone"): score += 1.0
    if fields.get("experience"): score += 1.0
    if fields.get("skills"): score += 1.0
    if fields.get("certificates"): score += 1.0
    if fields.get("projects"): score += 1.0
    return (score / 7.0) * 100.0

def calc_composite_v3(fields):
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

def run_comparison():
    v2_pipeline = ExtractionPipeline()
    v3_pipeline = PDFPipelineV3()

    resumes_dir = BACKEND_DIR / "data" / "resumes"
    all_pdfs = list(resumes_dir.glob("*.pdf"))
    random.seed(42)
    pdfs = random.sample(all_pdfs, min(20, len(all_pdfs)))
    
    print(f"Comparing V2 vs V3 on {len(pdfs)} PDFs...")
    
    # We will bypass S3 by using StructuralParsingService parse_pdf locally 
    # Actually ExtractionPipeline.run_pipeline expects s3_bucket and s3_key, but if we don't have it, PyMuPDF fallback triggers!
    # Wait, PyMuPDF Quality Gate runs locally first. If it passes, it returns. If it fails, it calls ODL (which needs S3).
    # Since we removed AWS endpoint stuff, ODL might fail if it tries to hit S3. But let's try it.
    
    v2_scores = []
    v3_scores = []
    
    from src.config.aws import get_settings
    settings = get_settings()

    for idx, pdf in enumerate(pdfs):
        doc_id = pdf.stem
        # Run V3
        res3 = v3_pipeline.extract(str(pdf)).fields
        sc3 = calc_composite_v3(res3)
        v3_scores.append(sc3)
        
        # Run V2
        try:
            res2 = v2_pipeline.run_pipeline(str(pdf), doc_id, settings.s3_bucket_name, f"jobs/test/{doc_id}.pdf")
            sc2 = calc_composite_v2(res2["fields"])
            v2_scores.append(sc2)
            
            print(f"[{idx+1:2}] {pdf.name[:20]:<20} | V2: {sc2:5.1f}% | V3: {sc3:5.1f}% | Diff: {sc3 - sc2:+5.1f}%")
        except Exception as e:
            print(f"[{idx+1:2}] {pdf.name[:20]:<20} | V2 FAILED: {e}")
            
    if v2_scores and v3_scores:
        avg_v2 = sum(v2_scores) / len(v2_scores)
        avg_v3 = sum(v3_scores) / len(v3_scores)
        print(f"\nAverage V2: {avg_v2:.1f}%")
        print(f"Average V3: {avg_v3:.1f}%")

if __name__ == "__main__":
    run_comparison()
