import sys
sys.path.insert(0, '.')
import fitz
import re
from pathlib import Path
import src.extractors.experience.experience_parser as ep

resumes_dir = Path("data/resumes")
all_pdfs = sorted(resumes_dir.glob("*.pdf"))

parser_strict = ep.ExperienceParser()
parser_lenient = ep.ExperienceParser()

# Lenient uses \d{1}\s*\d{1}\s*\d{1}\s*\d{1}
old_year = r'\d{1}\s*\d{1}\s*\d{1}\s*\d{1}'
old_start = ep._START_PATTERNS.replace(r'(?<!\d)(?:1\s*9|2\s*0)\s*\d{1}\s*\d{1}(?!\d)', old_year)
old_end = ep._END_PATTERNS.replace(r'(?<!\d)(?:1\s*9|2\s*0)\s*\d{1}\s*\d{1}(?!\d)', old_year)
old_date_range_re = re.compile(
    r'(?P<start>' + old_start + r')'
    + ep._DATE_SEP +
    r'(?P<end>' + old_end + r')',
    re.I)

regressions = []

print(f"Scanning {len(all_pdfs)} resumes...")
for pdf_path in all_pdfs:
    try:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # 1. Run strict
        ep.DATE_RANGE_RE = ep.re.compile(
            r'(?P<start>' + ep._START_PATTERNS + r')'
            + ep._DATE_SEP +
            r'(?P<end>' + ep._END_PATTERNS + r')',
            re.I)
        exp_strict = parser_strict.parse(text)
        
        # 2. Run lenient
        ep.DATE_RANGE_RE = old_date_range_re
        exp_lenient = parser_lenient.parse(text)
        
        if exp_lenient and not exp_strict:
            regressions.append((pdf_path.name, text))
    except Exception as e:
        pass

print(f"Found {len(regressions)} regressions.")
for name, text in regressions[:5]:
    print(f"\n{'='*80}\n{name}\n{'='*80}")
    # Print lines that matched lenient but not strict
    matches = list(old_date_range_re.finditer(text))
    for m in matches:
        print("Lenient matched:", repr(m.group(0)))
