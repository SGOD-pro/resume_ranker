import json
import sys

d = json.load(open('diagnostic_output.json', encoding='utf-8'))

# Check Category A entries for pipe-table skills syntax in ODL markdown
print("=== PIPE TABLES IN CATEGORY A (ODL Markdown) ===")
for i, doc in enumerate(d['cat_a'][:10]):
    md = doc['markdown']
    if '|' in md:
        pipes = [line for line in md.split('\n') if '|' in line][:5]
        print(f'--- Cat A doc {i} [{doc["file"]}] has PIPE lines ---')
        for p in pipes:
            print(repr(p))
        print()
    else:
        print(f'--- Cat A doc {i} [{doc["file"]}]: No pipe chars ---')

print()
print("=== PIPE TABLES IN CATEGORY B (PyMuPDF text) ===")
for i, doc in enumerate(d['cat_b'][:10]):
    txt = doc.get('text', doc.get('markdown', ''))
    if '|' in txt:
        pipes = [line for line in txt.split('\n') if '|' in line][:5]
        print(f'--- Cat B doc {i} [{doc["file"]}] has PIPE lines ---')
        for p in pipes:
            print(repr(p))
        print()
    else:
        print(f'--- Cat B doc {i} [{doc["file"]}]: No pipe chars ---')

# Also print a sample of experience sections from Category A to check markdown header dates
print()
print("=== EXPERIENCE SECTION SNIPPETS (Cat A, ODL markdown) ===")
for i, doc in enumerate(d['cat_a'][:5]):
    if 'experience' in doc['missing']:
        md = doc['markdown']
        # Find lines near "Experience" section
        idx = md.lower().find('experience')
        if idx >= 0:
            chunk = md[max(0, idx-50):idx+500]
            print(f'--- Doc {i} [{doc["file"]}] ---')
            for line in chunk.split('\n')[:20]:
                print(repr(line))
            print()
