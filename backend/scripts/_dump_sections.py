import json, sys
d = json.load(open('diagnostic_output.json', encoding='utf-8'))
sys.stdout.reconfigure(encoding='utf-8')

print('=== FULL Cat A missing-experience markdown snippets ===')
for i, doc in enumerate(d['cat_a']):
    if 'experience' in doc['missing']:
        md = doc['markdown']
        idx = md.lower().find('experience')
        if idx < 0:
            idx = 0
        chunk = md[max(0, idx-30):idx+500]
        fname = doc['file']
        print(f'DOC {i} [{fname}]')
        print(chunk[:600])
        print('---')

print()
print('=== FULL Cat B missing-experience plain text snippets ===')
for i, doc in enumerate(d['cat_b']):
    if 'experience' in doc.get('missing', []):
        txt = doc.get('text', doc.get('markdown', ''))
        idx = txt.lower().find('experience')
        if idx < 0:
            idx = 0
        chunk = txt[max(0, idx-30):idx+500]
        fname = doc['file']
        print(f'DOC {i} [{fname}]')
        print(chunk[:600])
        print('---')

print()
print('=== FULL Cat A missing-skills snippets ===')
for i, doc in enumerate(d['cat_a']):
    if 'skills' in doc['missing']:
        md = doc['markdown']
        idx = md.lower().find('skill')
        if idx < 0:
            idx = 0
        chunk = md[max(0, idx-30):idx+400]
        fname = doc['file']
        print(f'DOC {i} [{fname}]')
        print(chunk[:500])
        print('---')
