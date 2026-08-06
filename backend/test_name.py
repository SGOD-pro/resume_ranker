import sys
sys.path.insert(0, '.')
import fitz
from pathlib import Path
from src.extractors.contact.contact_parser import ContactParser

pdf = Path('data/resumes/cv (2923).pdf')
doc = fitz.open(str(pdf))
text = ''
for page in doc[:1]:
    text += page.get_text()
doc.close()

print("--- TEXT ---")
print(text[:200])

parser = ContactParser()
name = parser._extract_name(full_width_text='', raw_text=text)
print("EXTRACTED NAME:", repr(name))
