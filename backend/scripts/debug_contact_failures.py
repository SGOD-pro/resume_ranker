import sys
sys.path.insert(0, '.')
import fitz
from pathlib import Path
from src.extraction.markdown_extraction_service import MarkdownExtractionService

md_svc = MarkdownExtractionService()
resumes_dir = Path('data/resumes')
pdfs = sorted(resumes_dir.glob('*.pdf'))

failed_count = 0
for pdf in pdfs:
    if failed_count >= 10:
        break
        
    doc = fitz.open(str(pdf))
    page = doc[0]
    
    # Simple PyMuPDF text dump
    text = page.get_text("text")
    doc.close()
    
    result = md_svc.extract(text, [], [])
    
    missing_email = not result['fields'].get('email')
    missing_name = not result['fields'].get('name')
    
    if missing_email or missing_name:
        print("="*60)
        print(f"DOCUMENT ID: {pdf.name}")
        missing = []
        if missing_name: missing.append("Name")
        if missing_email: missing.append("Email")
        print(f"Missing: {', '.join(missing)}")
        print("-" * 20 + " RAW MARKDOWN (First 500 chars) " + "-" * 20)
        print(text[:500])
        print("="*60 + "\n")
        failed_count += 1
