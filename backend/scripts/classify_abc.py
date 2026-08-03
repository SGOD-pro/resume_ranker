#!/usr/bin/env python3
import sys
import os
import fitz
import json
import random
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.extraction.structural_parsing_service import BatchDoc
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.skills.skills_parser import SkillsParser

def is_scrambled(raw_text: str) -> bool:
    """Heuristic for scrambled text (Category C).
    Often has lots of newlines with very few words per line, or 
    just very chaotic text. For this classification, we'll check if 
    the text is mostly fragmented lines (avg length < 15 chars) OR
    if experience parser fails to find ANY date ranges at all despite
    the resume having words like 'Experience'."""
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    if not lines: return True
    avg_len = sum(len(l) for l in lines) / len(lines)
    if avg_len < 20: # Heavily fragmented
        return True
    
    # Check if 'Experience' exists but is fragmented like E x p e r i e n c e
    if re.search(r'E\s*x\s*p\s*e\s*r\s*i\s*e\s*n\s*c\s*e', raw_text, re.I) and 'Experience' not in raw_text:
        return True
        
    return False

import re
def main():
    resumes_dir = BACKEND_DIR / "data" / "resumes"
    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    random.seed(42)
    random.shuffle(all_pdfs)
    pdfs = all_pdfs[:200]
    
    pipeline = ExtractionPipeline()
    
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
        
    results = []
    with patch("boto3.client", side_effect=_s3_side_effect):
        batch_docs = [BatchDoc(str(i), str(p), 'm','m') for i,p in enumerate(pdfs)]
        for i in range(0, 200, 10):
            batch = batch_docs[i:i+10]
            print(f"Processing batch {i//10 + 1}/20")
            results.extend(pipeline.run_pipeline_batch(batch))
            
    cat_A, cat_B, cat_C = 0, 0, 0
    total_nova = 0
    
    b_examples = []
    
    for doc, res in zip(batch_docs, results):
        timings = res.get("stage_timings", [])
        nova_triggered = any(t.get("stage") == "nova_fallback" for t in timings)
        if not nova_triggered:
            continue
            
        total_nova += 1
        gate_score = res.get("extraction_quality", 0.0)
        
        if gate_score < 0.90:
            cat_A += 1
        else:
            # Score >= 0.90 but still failed regex. Is it B or C?
            # Let's use fitz to get raw text
            import fitz
            doc_fitz = fitz.open(doc.pdf_path)
            raw_text = "".join([page.get_text() for page in doc_fitz])
            doc_fitz.close()
            
            if is_scrambled(raw_text):
                cat_C += 1
            else:
                cat_B += 1
                if len(b_examples) < 2:
                    b_examples.append((doc.pdf_path, raw_text))
                    
    print("\n===============================")
    print(f"Total Nova Fallbacks: {total_nova}")
    print(f"Category A (< 0.90): {cat_A}")
    print(f"Category B (>= 0.90, Clean text): {cat_B}")
    print(f"Category C (>= 0.90, Scrambled/False Negative): {cat_C}")
    print("===============================\n")

if __name__ == "__main__":
    main()
