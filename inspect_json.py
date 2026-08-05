import json
import random

with open('backend/diagnostic_output.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

random.seed(42)
sample = random.sample(data, min(15, len(data)))
for idx, item in enumerate(sample, 1):
    print(f"--- Doc {idx}: {item['filename']} ---")
    print(f"Missing: {item['missing_fields']}")
    print(f"Raw Text snippet: {repr(item['raw_text_first_1000_chars'][:300])}")
