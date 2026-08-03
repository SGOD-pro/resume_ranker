#!/usr/bin/env python3
import sys
import os
from pathlib import Path
import random
import time

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.extraction.structural_parsing_service import BatchDoc
from src.config.aws import get_settings

def run_classification():
    settings = get_settings()
    pipeline = ExtractionPipeline()
    resumes_dir = BACKEND_DIR / "data" / "resumes"
    
    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    random.seed(42)
    random.shuffle(all_pdfs)
    pdfs = all_pdfs[:200]
    
    batch_docs = []
    for doc_id, pdf_path in enumerate(pdfs):
        batch_docs.append(BatchDoc(
            document_id=str(doc_id),
            pdf_path=str(pdf_path),
            s3_bucket="mock",
            s3_key="mock",
        ))
        
    print(f"Running pipeline on {len(batch_docs)} docs...")
    
    # We will mock s3 using the same method as run_v2_benchmark
    from unittest.mock import patch, MagicMock
    import shutil
    
    _pdf_path_map = {str(i): str(p) for i, p in enumerate(pdfs)}
    
    def _s3_side_effect(service_name, *args, **kwargs):
        if service_name == "s3":
            mock_s3 = MagicMock()
            def fake_download(Bucket, Key, Filename, **_kw):
                stem = Path(Filename).stem
                if stem in _pdf_path_map:
                    shutil.copy(_pdf_path_map[stem], Filename)
            mock_s3.download_file.side_effect = fake_download
            return mock_s3
        import boto3
        return boto3.client(service_name, *args, **kwargs)
        
    with patch("boto3.client", side_effect=_s3_side_effect):
        results = []
        batch_size = 10
        for i in range(0, len(batch_docs), batch_size):
            batch = batch_docs[i:i+batch_size]
            print(f"Processing batch {i//batch_size + 1}...")
            batch_results = pipeline.run_pipeline_batch(batch)
            results.extend(batch_results)
            
    cat_A = []
    cat_B = []
    cat_C = [] # We'll just collect them in B and later inspect
    
    for doc, res in zip(batch_docs, results):
        timings = res.get("stage_timings", [])
        nova_triggered = any(t.get("stage") == "nova_fallback" for t in timings)
        if not nova_triggered:
            continue
            
        gate_score = res.get("extraction_quality", 0.0)
        
        if gate_score < 0.90:
            cat_A.append((doc, res))
        else:
            cat_B.append((doc, res))
            
    print("=" * 50)
    print("CLASSIFICATION RESULTS")
    print(f"Total Nova Fallbacks: {len(cat_A) + len(cat_B)}")
    print(f"Category A (Score < 0.90 -> ODL): {len(cat_A)}")
    print(f"Category B/C (Score >= 0.90 -> PyMuPDF): {len(cat_B)}")
    print("=" * 50)
    
    print("\nCategory B/C Samples (first 5):")
    for doc, res in cat_B[:5]:
        print(f"File: {Path(doc.pdf_path).name}, Score: {res.get('extraction_quality')}")
        unresolved = [u["field"] for u in res.get("fields", {}).get("elements", []) if not u.get("value")] # wait elements is not what unresolved is
        # actually unresolved is not in the output dict directly.
        # But we can just print the raw text snippet.
        import fitz
        fitz_doc = fitz.open(doc.pdf_path)
        raw_text = fitz_doc[0].get_text()[:300].replace('\n', ' ')
        print(f"Snippet: {raw_text}")
        fitz_doc.close()
        print("-" * 50)

if __name__ == "__main__":
    run_classification()
