import fitz
import sys
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.experience.experience_parser import ExperienceParser
print("Opening cv 1026...")
doc = fitz.open('data/resumes/cv (1026).pdf')
text = ""
for page in doc: text += page.get_text()

print("ContactParser...")
cp = ContactParser()
cp.parse(raw_text=text)

print("ExperienceParser...")
ep = ExperienceParser()
ep.parse(text)
print("Done!")
