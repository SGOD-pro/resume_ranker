import sys
sys.path.insert(0, '.')
from pathlib import Path
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from unittest.mock import patch, MagicMock

def _s3(svc, *a, **kw):
    m = MagicMock()
    return m
patch('boto3.client', side_effect=_s3).start()

resumes_dir = Path('data/resumes')
pdfs = sorted(resumes_dir.glob('*.pdf'))

svc = StructuralParsingService()
md_svc = MarkdownExtractionService()

missing_both = []

for pdf in pdfs:
    try:
        res = svc.parse_pdf(str(pdf), pdf.name, 'bucket', 'dummy')
        md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
        if not md_result['fields'].get('email') and not md_result['fields'].get('phone'):
            missing_both.append(pdf.name)
    except Exception as e:
        pass

print(f"Missing BOTH Email AND Phone ({len(missing_both)}): {missing_both[:5]}")
