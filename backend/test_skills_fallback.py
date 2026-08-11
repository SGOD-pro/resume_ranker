import sys
from pathlib import Path
sys.path.insert(0, '.')
from src.extraction.markdown_extraction_service import MarkdownExtractionService
import fitz

resumes_dir = Path("data/resumes")
all_pdfs = sorted(resumes_dir.glob("*.pdf"))

svc = MarkdownExtractionService()
fallback_count = 0

for pdf_path in all_pdfs[:200]:
    try:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        res = svc.extract(markdown_text=text)
        if len(res["unresolved_chunks"]) > 0:
            fallback_count += 1
    except Exception as e:
        pass

print(f"Fallback count on PyMuPDF text: {fallback_count}")
