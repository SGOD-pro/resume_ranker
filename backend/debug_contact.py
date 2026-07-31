import sys
import os
import json
import fitz
from pathlib import Path
from src.extractors.contact.contact_parser import ContactParser

pdfs = list(Path('data/resumes').glob('*.pdf'))
cp = ContactParser()

missing = []
for p in pdfs:
    try:
        doc = fitz.open(str(p))
        text = '\n'.join(page.get_text() for page in doc)
        res = cp.parse(raw_text=text)
        if not res.get('email') or not res.get('phone'):
            missing.append({
                'name': p.name,
                'email': res.get('email'),
                'phone': res.get('phone')
            })
    except Exception as e:
        pass

print(f"Total Missing: {len(missing)}")
for m in missing[:5]:
    print(m)
