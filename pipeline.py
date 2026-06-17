"""
Pipeline v2 — Layout-First Architecture
Flow: PDF → Layout Detection → Column Separation → Section Parsing → NLP → JSON
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from layout_extractor import LayoutAwarePDFExtractor
from section_parser import ResumeAssembler
from domain_detector import DomainDetector


class PDFPipelineV2:

    def __init__(self):
        self.layout_extractor = LayoutAwarePDFExtractor()
        self.domain_detector = DomainDetector()
        self.resume_assembler = ResumeAssembler()

    def extract(self, pdf_path: str) -> dict:
        # Step 1: Layout-aware extraction
        doc = self.layout_extractor.extract(pdf_path)

        # Step 2: Parse sections from each region
        main_sections = self.layout_extractor.parse_sections(doc)
        sidebar_sections = self.layout_extractor.parse_sidebar(doc)

        # Step 3: Detect domain (run on main text only)
        combined_text = doc.full_width_text + "\n" + doc.main_text
        domain_result = self.domain_detector.detect(combined_text)

        # Step 4: Domain-specific assembly
        if domain_result.domain == "resume":
            fields = self.resume_assembler.assemble(
                full_width_text=doc.full_width_text,
                sidebar_sections=sidebar_sections,
                main_sections=main_sections,
            )
        else:
            # Fallback: return raw sections for non-resume docs
            fields = {
                "main_sections": main_sections,
                "sidebar_sections": {k: v for k, v in sidebar_sections.items()},
            }

        return {
            "document_id": os.path.basename(pdf_path),
            "domain": domain_result.domain,
            "domain_confidence": domain_result.confidence,
            "layout": doc.layout,
            "fields": fields,
            "raw_structure": {
                "full_width": doc.full_width_text,
                "sidebar": doc.sidebar_text,
                "main": doc.main_text,
            }
        }


if __name__ == "__main__":
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent
    pdf_path = BASE_DIR / "resume" / "1.pdf"
    # pdf = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/1__2_.pdf"
    pipeline = PDFPipelineV2()
    result = pipeline.extract(pdf_path)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))