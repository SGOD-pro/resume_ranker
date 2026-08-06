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

missing_exp = []
missing_name = []
missing_edu = []

for pdf in pdfs:
    try:
        res = svc.parse_pdf(str(pdf), pdf.name, 'bucket', 'dummy')
        md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
        if not md_result['fields'].get('experience'):
            missing_exp.append(pdf.name)
        if not md_result['fields'].get('name'):
            missing_name.append(pdf.name)
        if not md_result['fields'].get('education'):
            missing_edu.append(pdf.name)
    except Exception as e:
        pass

print(f"Missing Experience ({len(missing_exp)}): {missing_exp[:5]}")
print(f"Missing Name ({len(missing_name)}): {missing_name[:5]}")
print(f"Missing Education ({len(missing_edu)}): {missing_edu[:5]}")
