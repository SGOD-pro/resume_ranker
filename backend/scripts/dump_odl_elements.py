import sys, json, shutil, uuid, random
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, '.')

_cur = ['']
def _s3(svc, *a, **kw):
    m = MagicMock()
    def dl(Bucket, Key, Filename, **_): shutil.copy(_cur[0], Filename)
    m.download_file.side_effect = dl
    m.upload_file = MagicMock()
    return m

_p = patch('boto3.client', side_effect=_s3)
_p.start()

from src.extraction.structural_parsing_service import StructuralParsingService, pymupdf_layout_quality_signals, QUALITY_THRESHOLD
from src.config.aws import get_settings
import fitz

svc = StructuralParsingService()
settings = get_settings()
resume_dir = Path('data/resumes')
pdfs = list(resume_dir.glob('*.pdf'))
random.seed(7)
random.shuffle(pdfs)

found = None
for p in pdfs[:60]:
    try:
        doc = fitz.open(str(p))
        sig = pymupdf_layout_quality_signals(doc[0])
        doc.close()
        if sig['score'] < QUALITY_THRESHOLD:
            found = p
            break
    except:
        pass

if not found:
    print('No ODL-eligible PDF found')
    sys.exit()

_cur[0] = str(found)
r = svc.parse_pdf(str(found), 'test-dump', settings.s3_bucket_name, 'dummy')
print('PDF:', found.name, ' quality=', round(r.quality_score,3), ' elements=', len(r.elements))
if r.elements:
    el = r.elements[0]
    print('KEYS:', sorted(el.keys()))
    print(json.dumps(el, indent=2, default=str)[:800])
    print('--- first 6 elements summary ---')
    for i, e in enumerate(r.elements[:6]):
        print('  [{}] keys={} bbox={} page={} type={} content={}'.format(
            i,
            sorted(e.keys()),
            e.get('bounding_box','MISSING'),
            e.get('page number', e.get('page_number','?')),
            e.get('type','?'),
            repr(str(e.get('content', e.get('text','?')))[:60])
        ))
else:
    print('NO ELEMENTS returned')
