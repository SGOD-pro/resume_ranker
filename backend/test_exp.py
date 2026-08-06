import sys
sys.path.insert(0, '.')
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.markdown_extraction_service import MarkdownExtractionService

svc = StructuralParsingService()
md_svc = MarkdownExtractionService()

res = svc.parse_pdf('data/resumes/cv (10).pdf', 'cv (10).pdf', 'resume-ranker-lambda-bucket', 'data/resumes/cv (10).pdf')
md_result = md_svc.extract(res.markdown, res.hyperlinks, res.elements)
print("EXPERIENCE: ", md_result['fields'].get('experience', []))
print("MARKDOWN:")
print(res.markdown)
