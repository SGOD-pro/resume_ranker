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
def _flatten(node_list):
    flat = []
    for node in node_list:
        if not isinstance(node, dict): continue
        flat.append(node)
        if 'kids' in node and isinstance(node['kids'], list):
            flat.extend(_flatten(node['kids']))
    return flat

flat_kids = _flatten(kids)
for i, el in enumerate(flat_kids):
    c = str(el.get('content', el.get('text', ''))).strip().replace('\n', ' ')
    print(i, el.get('type'), c[:50])
