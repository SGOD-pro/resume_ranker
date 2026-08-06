import sys
sys.path.insert(0, '.')
from src.extractors.contact.contact_parser import ContactParser
parser = ContactParser()
test_strings = [
    'E-Mail ID    : vksuthakar10@gmail.com',
    'Email- sagartalreja@gmail.com',
    'E-Mail-naziralam280@gmail.com',
    'E-mail: amittt1407@outlook.com',
    'E-mail - dwivediprashant539@gmail.com',
    'Email-ID krdwivedi@outlook.com'
]
for s in test_strings:
    res = parser.parse(s)
    print(f'"{s}" -> Email: {res.get("email")}')
