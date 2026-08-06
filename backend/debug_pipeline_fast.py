import sys
sys.path.insert(0, '.')
from pathlib import Path
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from unittest.mock import patch, MagicMock

def _s3(svc, *a, **kw):
    m = MagicMock()
    m.download_file = MagicMock()
    m.upload_file = MagicMock()
    return m
patch('boto3.client', side_effect=_s3).start()

resumes_dir = Path('data/resumes')
pdfs = sorted(resumes_dir.glob("*.pdf"))[:50]

svc = StructuralParsingService()
md_svc = MarkdownExtractionService()

for pdf in pdfs:
    try:
        res = svc.parse_pdf(str(pdf), pdf.name, 'bucket', 'dummy')
        md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
        fields = md_result['fields']
        
        has_name = bool(fields.get('name'))
        has_email = bool(fields.get('email'))
        
        if not has_name or not has_email:
            print(f"{pdf.name}: Name={has_name}, Email={has_email}")
            if not has_name:
                print("--- START ---")
                print(res.markdown[:300])
                print("--- END ---")
    except Exception as e:
        print(f"Error on {pdf.name}: {e}")
