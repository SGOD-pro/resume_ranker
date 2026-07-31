import re
import fitz
import sys

_MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
_START_PATTERNS = '|'.join([
    _MONTH + r'\.?\s+\d{4}', _MONTH + r'\.\d{4}', _MONTH + r"'\d{2}", _MONTH + r'-\d{2,4}',
    r'\d{1,2}\s+' + _MONTH + r'\s+\d{4}', r'\d{1,2}/\d{1,2}/\d{4}', r'\d{1,2}-\d{1,2}-\d{4}',
    r'\d{1,2}/\d{4}', r'\d{1,2}-\d{4}', r'\d{1,2}\.\d{4}', r'\d{4}/\d{1,2}', r'\d{4}',
])
_END_PATTERNS = '|'.join([
    _MONTH + r'\.?\s+\d{4}', _MONTH + r'\.\d{4}', _MONTH + r"'\d{2}", _MONTH + r'-\d{2,4}',
    r'\d{1,2}\s+' + _MONTH + r'\s+\d{4}', r'\d{1,2}/\d{1,2}/\d{4}', r'\d{1,2}-\d{1,2}-\d{4}',
    r'\d{1,2}/\d{4}', r'\d{1,2}-\d{4}', r'\d{1,2}\.\d{4}', r'\d{4}/\d{1,2}',
    r'Present|Current|Now|Till\s+Date|Till\s+Now|To\s+Date|Ongoing', r'\d{4}',
])
_DATE_SEP = r'\s*(?:[–—\-–]+|to|till)\s*'
DATE_RANGE_RE = re.compile(r'(?P<start>' + _START_PATTERNS + r')' + _DATE_SEP + r'(?P<end>' + _END_PATTERNS + r')', re.I)

doc = fitz.open('data/resumes/cv (1025).pdf')
text = ""
for page in doc: text += page.get_text()

import time
t0 = time.time()
print("Starting regex finditer...")
try:
    for m in DATE_RANGE_RE.finditer(text):
        pass
    print("Done in", time.time() - t0)
except Exception as e:
    print(e)
