import sys
import re
from pathlib import Path
import fitz

resumes_dir = Path("data/resumes")
import random
all_pdfs = sorted(resumes_dir.glob("*.pdf"))
valid_pdfs = list(all_pdfs)
random.seed(42)
random.shuffle(valid_pdfs)
pdfs = valid_pdfs[:200]

import src.extractors.experience.experience_parser as ep
parser = ep.ExperienceParser()

print("Finding failing docs...")
fails = []
for pdf in pdfs:
    try:
        doc = fitz.open(str(pdf))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # Test if parser finds anything
        res = parser.parse(text)
        if not res:
            fails.append((pdf.name, text))
    except Exception as e:
        pass

for name, text in fails[:10]:
    print(f"\n{'='*80}\n{name}\n{'='*80}")
    
    # Print a window around potential years
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'20\d{2}|19\d{2}|2\s*0\s*\d\s*\d', line):
            start = max(0, i-2)
            end = min(len(lines), i+3)
            print(f"--- match around line {i}:")
            for j in range(start, end):
                print(lines[j].strip())
