import sys
import os
import fitz
from pathlib import Path
import random
import time

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.extractors.contact.contact_parser import ContactParser, _EMAIL_RE
from src.extractors.experience.experience_parser import ExperienceParser, DATE_RANGE_RE
from src.extractors.skills.skills_parser import SkillsParser
from src.extraction.extraction_pipeline import ExtractionPipeline
from src.config.aws import get_settings

def print_failure(title, raw_text, missing):
    print(f"\n{'━' * 80}")
    print(f"  {title}")
    print(f"  MISSING: {', '.join(missing)}")
    print(f"{'━' * 80}")
    
    if "experience" in missing:
        print(f"\n  🔴 EXPERIENCE FAILED")
        print(f"  Regex Used: {DATE_RANGE_RE.pattern}")
        # Print a snippet, handle unicode errors
        snippet = raw_text[:500].encode('ascii', 'ignore').decode('ascii').replace('\n', '\\n')
        print(f"  First 500 chars of text: {snippet}")
        
    if "skills" in missing:
        print(f"\n  🔴 SKILLS FAILED")
        snippet = raw_text[:500].encode('ascii', 'ignore').decode('ascii').replace('\n', '\\n')
        print(f"  First 500 chars of text: {snippet}")

def main():
    data_dir = BACKEND_DIR / "data" / "resumes"
    pdfs = sorted(data_dir.glob("*.pdf"))
    random.seed(42)
    random.shuffle(pdfs)
    pdfs = pdfs[:200]

    pipeline = ExtractionPipeline()

    cat_a = []
    cat_b = []

    print("=" * 80)
    print("  REGEX FAILURE DIAGNOSTIC (Step 1)")
    print("=" * 80)
    
    # We will run just enough to get 10 of each
    from unittest.mock import patch, MagicMock
    import shutil
    import uuid
    
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
        for i, pdf_path in enumerate(pdfs):
            if len(cat_a) >= 10 and len(cat_b) >= 10:
                break
                
            doc_id = str(i)
            # Run structural parse
            parse_result = pipeline.structural_service.parse_pdf(
                str(pdf_path), doc_id, "mock-bucket", "mock-key"
            )
            
            # Check what's missing using markdown service (regex parsers)
            md_result = pipeline.markdown_service.extract(parse_result.markdown, parse_result.hyperlinks)
            fields = md_result["fields"]
            missing = []
            if not fields.get("experience"): missing.append("experience")
            if not fields.get("skills"): missing.append("skills")
            
            if not missing:
                continue
                
            gate_score = parse_result.quality_score
            
            if gate_score < 0.90 and len(cat_a) < 10:
                # Category A: ODL used, regex failed
                cat_a.append({
                    "file": pdf_path.name,
                    "markdown": parse_result.markdown,
                    "missing": missing
                })
            elif gate_score >= 0.90 and len(cat_b) < 10:
                # Category B: PyMuPDF used, regex failed
                cat_b.append({
                    "file": pdf_path.name,
                    "text": parse_result.markdown, # It's PyMuPDF raw text
                    "missing": missing
                })
                
    import json
    with open("diagnostic_output.json", "w", encoding="utf-8") as f:
        json.dump({"cat_a": cat_a, "cat_b": cat_b}, f, indent=2)
    print("Diagnostics written to diagnostic_output.json")

if __name__ == "__main__":
    main()
