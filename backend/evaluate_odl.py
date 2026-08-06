import sys
sys.path.insert(0, '.')
from pathlib import Path
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from unittest.mock import patch, MagicMock
from src.extraction.odl_client import parse_batch

patch('boto3.client', return_value=MagicMock()).start()

resumes_dir = Path('data/resumes')
pdfs = sorted(resumes_dir.glob('*.pdf'))[:25] # Run a batch of 25

md_svc = MarkdownExtractionService()

# Call ODL in batch mode directly
s3_bucket = 'bucket'
batch_events = [{"document_id": pdf.name, "s3_bucket": s3_bucket, "s3_key": str(pdf)} for pdf in pdfs]
batch_payload = {"documents": batch_events, "save_images": False}

try:
    from src.extraction.odl_client import _invoke_local
    payload = _invoke_local(batch_payload)
    results = payload.get("results", [])
    
    for doc in results:
        doc_id = doc.get("document_id")
        md = doc.get("markdown", "")
        elements = doc.get("elements", [])
        hyperlinks = doc.get("hyperlinks", [])
        
        md_result = md_svc.extract(md, hyperlinks, elements)
        if not md_result['fields'].get('email'):
            print("="*60)
            print(f"DOCUMENT ID: {doc_id}")
            print(f"Missing: Email")
            print("-" * 20 + " RAW MARKDOWN (First 500 chars) " + "-" * 20)
            print(md[:500])
            
            if elements and len(elements) > 0 and 'box' in elements[0]:
                print("-" * 20 + " ODL TOP 20% BOXES " + "-" * 20)
                num_elements = len(elements)
                top_20_count = max(1, int(num_elements * 0.2))
                for el in elements[:top_20_count]:
                    print(f"Text: {el.get('text', '')}")
            
            print("="*60 + "\n")
except Exception as e:
    import traceback
    traceback.print_exc()
