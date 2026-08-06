import sys
sys.path.insert(0, '.')
from pathlib import Path
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from unittest.mock import patch, MagicMock

# Mock S3 to run in Mock Mode
patch('boto3.client', return_value=MagicMock()).start()

resumes_dir = Path('data/resumes')
pdfs = sorted(resumes_dir.glob('*.pdf'))

svc = StructuralParsingService()
md_svc = MarkdownExtractionService()

failed_count = 0

for pdf in pdfs:
    if failed_count >= 10:
        break
    try:
        res = svc.parse_pdf(str(pdf), pdf.name, 'bucket', 'dummy')
        md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
        
        has_email = md_result['fields'].get('email')
        has_name = md_result['fields'].get('name')
        
        if not has_email or not has_name:
            print("="*60)
            print(f"DOCUMENT ID: {pdf.name}")
            print(f"Missing: {'Email ' if not has_email else ''}{'Name' if not has_name else ''}")
            print("-" * 20 + " RAW MARKDOWN (First 500 chars) " + "-" * 20)
            print(res.markdown[:500])
            
            # Check if ODL was used
            # ODL elements have 'text' and 'box' attributes
            if res.elements and len(res.elements) > 0 and 'box' in res.elements[0]:
                print("-" * 20 + " ODL TOP 20% BOXES " + "-" * 20)
                # ODL elements are flattened layout items
                # They should have bounding boxes.
                num_elements = len(res.elements)
                top_20_count = max(1, int(num_elements * 0.2))
                for el in res.elements[:top_20_count]:
                    print(f"Text: {el.get('text', '')}")
            
            print("="*60 + "\n")
            failed_count += 1
            
    except Exception as e:
        pass
