import re
new_re = re.compile(r'(?<!\d)(?:1\s*9|2\s*0)\s*\d{1}\s*\d{1}(?!\d)')
old_re = re.compile(r'\b(?:19|20)\d{2}\b')

tests = [
    "2020",
    " 2020 ",
    "July2020",
    "July 2020",
    "2 0 2 0",
    "9876543210 2020",
    "98765432102020",
    "2020-2021",
    "2020 - 2021"
]

for t in tests:
    print(f"'{t}':")
    old_m = old_re.search(t)
    new_m = new_re.search(t)
    print(f"  Old: {old_m.group() if old_m else None}")
    print(f"  New: {new_m.group() if new_m else None}")
