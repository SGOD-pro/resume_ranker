import sys
sys.path.insert(0, '.')
from src.extraction.structural_parsing_service import StructuralParsingService

svc = StructuralParsingService()
res = svc.parse_pdf('data/resumes/cv (10).pdf', 'cv (10).pdf', 'resume-ranker-lambda-bucket', 'data/resumes/cv (10).pdf')

def _flatten(node_list):
    flat = []
    for node in node_list:
        if not isinstance(node, dict): continue
        flat.append(node)
        if 'kids' in node and isinstance(node['kids'], list):
            flat.extend(_flatten(node['kids']))
    return flat

kids = res.elements.get('kids', []) if isinstance(res.elements, dict) else res.elements
flat = _flatten(kids)

for el in flat[:15]:
    bb = el.get('bounding_box') or el.get('bounding box')
    text = el.get('text') or el.get('content')
    print(f"BB: {bb}, Text: {text}")
