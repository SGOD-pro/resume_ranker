import sys
sys.path.insert(0, '.')
import fitz
import re
from pathlib import Path
from src.extractors.experience.experience_parser import ExperienceParser

resumes_dir = Path('data/resumes')
import random
all_pdfs = sorted(resumes_dir.glob("*.pdf"))
random.seed(42)
random.shuffle(all_pdfs)
pdfs = all_pdfs[:200]

parser = ExperienceParser()
missing = []
for pdf in pdfs:
    try:
        doc = fitz.open(str(pdf))
        text = ''
        for page in doc: text += page.get_text()
        doc.close()
        
        res = parser.parse(text)
        if not res:
            missing.append(pdf.name)
    except:
        pass

print(f"Missing in PyMuPDF text alone: {len(missing)}")
for pdf_name in missing[:15]:
    try:
        doc = fitz.open(str(resumes_dir / pdf_name))
        text = ''
        for page in doc: text += page.get_text()
        doc.close()
        
        m = re.search(r'experience', text, re.I)
        if m:
            print(f'\n--- {pdf_name} ---')
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 300)
            print(text[start:end])
    except:
        pass
