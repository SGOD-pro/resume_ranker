import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# S3 mock for local testing
_current_pdf_path = [""]
def _s3_side_effect(service_name, *args, **kwargs):
    mock_s3 = MagicMock()
    def fake_download(Bucket, Key, Filename, **_kw):
        import shutil
        shutil.copy(_current_pdf_path[0], Filename)
    mock_s3.download_file.side_effect = fake_download
    return mock_s3

# Ensure boto3.client globally returns the mock
import boto3
boto3.client = _s3_side_effect

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.config.aws import get_settings

def run_diagnostic():
    pipeline = ExtractionPipeline()
    settings = get_settings()
    
    # We will just pull the first 30 PDFs from the local test directory or the repo
    pdf_files = list(Path(PROJECT_ROOT).rglob("*.pdf"))
    if not pdf_files:
        print("No PDFs found.")
        return
        
    print(f"Testing {min(30, len(pdf_files))} PDFs for contact failures...")
    
    failures = 0
    for pdf_path in pdf_files[:30]:
        _current_pdf_path[0] = str(pdf_path)
        doc_id = str(uuid.uuid4())
        
        try:
            # We intercept before Nova to see pure regex
            parse_result = pipeline.structural_service.parse_pdf(str(pdf_path), doc_id, settings.s3_bucket_name, "dummy-key")
            md_result = pipeline.markdown_service.extract(parse_result.markdown, parse_result.hyperlinks)
            fields = md_result["fields"]
            
            name = fields.get("name")
            email = fields.get("email")
            
            if not name or not email:
                failures += 1
                source = "ODL" if parse_result.quality_score < 0.9 else "PyMuPDF"
                print("\n" + "="*80)
                print(f"FAILURE #{failures}: {pdf_path.name}")
                print(f"Missing: {'Name ' if not name else ''}{'Email' if not email else ''}")
                print(f"Source: {source}")
                print("-" * 40)
                print("First 500 chars of Markdown/Text:")
                print(parse_result.markdown[:500])
                print("="*80)
                
                if failures >= 20:
                    break
        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")

if __name__ == "__main__":
    run_diagnostic()
