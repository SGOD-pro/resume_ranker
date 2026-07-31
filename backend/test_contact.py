import fitz
import sys
from src.extractors.contact.contact_parser import ContactParser
doc = fitz.open('data/resumes/cv (1025).pdf')
text = ""
for page in doc: text += page.get_text()
print("Starting parser...")
import time
t0 = time.time()
cp = ContactParser()
cp.parse(raw_text=text)
print("Done in", time.time() - t0)
