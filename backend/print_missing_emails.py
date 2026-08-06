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
pdfs = sorted(resumes_dir.glob("*.pdf"))

svc = StructuralParsingService()
md_svc = MarkdownExtractionService()

for pdf in pdfs[:50]:
    try:
        res = svc.parse_pdf(str(pdf), pdf.name, 'bucket', 'dummy')
        md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
        if not md_result['fields'].get('email'):
            print(f"--- {pdf.name} ---")
            print(res.markdown[:500])
    except Exception as e:
        pass
