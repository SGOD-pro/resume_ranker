import fitz
import sys
from src.extractors.experience.experience_parser import ExperienceParser
doc = fitz.open('data/resumes/cv (1025).pdf')
text = ""
for page in doc: text += page.get_text()
print("Starting parser...")
import time
t0 = time.time()
ep = ExperienceParser()
ep.parse(text)
print("Done in", time.time() - t0)
