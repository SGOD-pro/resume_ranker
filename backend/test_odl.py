import sys
sys.path.insert(0, '.')
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extractors.experience.experience_parser import ExperienceParser
import boto3
from unittest.mock import patch, MagicMock

def _s3(svc, *a, **kw):
    m = MagicMock()
    m.download_file.side_effect = lambda B,K,F,**_: __import__('shutil').copy('data/resumes/cv (3166).pdf', F)
    m.upload_file = MagicMock()
    return m
patch('boto3.client', side_effect=_s3).start()

svc = StructuralParsingService()
res = svc.parse_pdf('data/resumes/cv (3166).pdf', 'cv (3166).pdf', 'bucket', 'dummy')

for i, el in enumerate(res.elements):
    content = str(el.get('content')).replace('\n', ' ')[:50]
    print(f"Element {i}: type={el.get('type')} tag={el.get('pdfua_tag')} content={content}")
