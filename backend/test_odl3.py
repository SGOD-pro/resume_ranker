import sys
sys.path.insert(0, '.')
from src.extraction.structural_parsing_service import StructuralParsingService
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

kids = res.elements.get('kids', [])
print('Keys of kids[7] (which is the list):', kids[7].keys())
import json
print('Full list element:', json.dumps(kids[7], indent=2)[:500])
