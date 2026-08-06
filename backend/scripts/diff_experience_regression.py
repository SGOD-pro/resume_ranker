import sys
import re
import fitz
from pathlib import Path
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extractors.experience.experience_parser import ExperienceParser
import uuid

def main():
    import sys
    sys.path.insert(0, '.')
    from unittest.mock import patch, MagicMock
    _cur = ['']
    def _s3(svc, *a, **kw):
        m = MagicMock()
        m.download_file.side_effect = lambda B,K,F,**_: __import__('shutil').copy(_cur[0],F)
        m.upload_file = MagicMock()
        return m
    patch('boto3.client', side_effect=_s3).start()

    resumes_dir = Path("data/resumes")
    import random
    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    valid_pdfs = list(all_pdfs)
    random.seed(42)
    random.shuffle(valid_pdfs)
    pdfs = valid_pdfs[:50]

    svc = StructuralParsingService()
    # Ensure StructuralParsingService uses the current pdf path for the mock
    def _mock_parse(pdf_path, orig=svc.parse_pdf):
        _cur[0] = pdf_path
        return orig(pdf_path, Path(pdf_path).name, 'bucket', 'dummy')
    parser_strict = ExperienceParser()
    parser_lenient = ExperienceParser()
    
    # Monkeypatch parser_lenient to use \b instead of lookarounds for the year regex
    import src.extractors.experience.experience_parser as ep
    
    # The "old" regex from before Phase3 test3 was:
    old_year = r'\d{1}\s*\d{1}\s*\d{1}\s*\d{1}'
    
    old_start = ep._START_PATTERNS.replace(r'(?<!\d)(?:1\s*9|2\s*0)\s*\d{1}\s*\d{1}(?!\d)', old_year)
    old_end = ep._END_PATTERNS.replace(r'(?<!\d)(?:1\s*9|2\s*0)\s*\d{1}\s*\d{1}(?!\d)', old_year)
    
    old_date_range_re = re.compile(
        r'(?P<start>' + old_start + r')'
        + ep._DATE_SEP +
        r'(?P<end>' + old_end + r')',
        re.I)
        
    parser_lenient.DATE_RANGE_RE = old_date_range_re
    # Wait, DATE_RANGE_RE is a module-level variable in experience_parser!
    # I have to mock the module-level variable during the lenient pass.
    
    regressions = []
    
    print(f"Scanning {len(pdfs)} resumes to find experience regressions...")
    for pdf_path in pdfs:
        try:
            r = _mock_parse(str(pdf_path))
            text = r.markdown
            elements = r.elements
            
            # 1. Run strict (current)
            import src.extractors.experience.experience_parser as ep
            ep.DATE_RANGE_RE = ep.re.compile(
                r'(?P<start>' + ep._START_PATTERNS + r')'
                + ep._DATE_SEP +
                r'(?P<end>' + ep._END_PATTERNS + r')',
                re.I)
            exp_strict = parser_strict.parse(text, elements)
            
            # 2. Run lenient (old)
            ep.DATE_RANGE_RE = old_date_range_re
            exp_lenient = parser_lenient.parse(text, elements)
            
            if exp_lenient and not exp_strict:
                regressions.append((pdf_path.name, text, elements))
                
        except Exception as e:
            print("ERROR", e)
            pass

    print(f"Found {len(regressions)} documents with missing experience (regression).")
    for name, text, elements in regressions[:10]:
        print(f"\n{'='*80}")
        print(f"DOCUMENT ID: {name}")
        print(f"{'-'*80}")
        
        # Print experience section if found, else first 1000 chars
        exp_text = ""
        in_exp = False
        if elements:
            kids = elements.get('kids', []) if isinstance(elements, dict) else elements
            def _flat(nodes):
                res = []
                for n in nodes:
                    if isinstance(n, dict):
                        res.append(n)
                        if 'kids' in n and isinstance(n['kids'], list):
                            res.extend(_flat(n['kids']))
                return res
            for el in _flat(kids):
                raw = str(el.get('content', el.get('text', ''))).strip()
                if not raw: continue
                if el.get('type') == 'heading' or str(el.get('pdfua_tag')).startswith('H'):
                    c = re.sub(r'[^a-zA-Z\s]', '', raw.lower()).strip()
                    if c in parser_strict._EXP_SECTION_KEYWORDS:
                        in_exp = True
                        continue
                    elif in_exp and c:
                        break
                if in_exp:
                    exp_text += raw + "\n"
        
        if exp_text.strip():
            print("EXPERIENCE SECTION RAW TEXT:")
            print(exp_text[:1000])
        else:
            print("FIRST 1000 CHARS OF RAW TEXT:")
            print(text[:1000])

if __name__ == '__main__':
    main()
