import sys
sys.path.insert(0, '.')
import fitz
import re
from pathlib import Path
from src.extractors.experience.experience_parser import ExperienceParser
import random

resumes_dir = Path('data/resumes')
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

for pdf_name in missing:
    try:
        doc = fitz.open(str(resumes_dir / pdf_name))
        text = ''
        for page in doc: text += page.get_text()
        doc.close()
        
        m = re.search(r'experience', text, re.I)
        if m:
            snippet = text[max(0, m.start() - 20):min(len(text), m.end() + 300)]
            if re.search(r'\d', snippet):
                print(f'\n--- {pdf_name} ---')
                print(snippet)
    except:
        pass
