import fitz
from typing import Dict, Any, List
from dataclasses import dataclass
from src.extraction.structural_parsing_service import StructuralParsingService, pymupdf_layout_quality_signals
from src.extraction.markdown_extraction_service import MarkdownExtractionService

@dataclass
class BoundingBox:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    severity: str
    reason: str

class B2BAtsScorer:
    def __init__(self):
        self.parser = StructuralParsingService()
        self.extractor = MarkdownExtractionService()
        
    def score(self, pdf_path: str, s3_bucket: str, s3_key: str) -> Dict[str, Any]:
        # 1. Structural Parsing
        parse_result = self.parser.parse_pdf(pdf_path, doc_id="ats_check", s3_bucket=s3_bucket, s3_key=s3_key)
        
        # 2. Markdown Extraction
        extraction_result = self.extractor.extract(
            markdown_text=parse_result.markdown,
            hyperlinks=parse_result.hyperlinks,
            elements=parse_result.elements,
            pymupdf_markdown=parse_result.pymupdf_text
        )
        fields = extraction_result["fields"]
        
        # 3. Calculate Score and Breakdown
        score = round(parse_result.quality_score * 100)
        breakdown = {"Base Parseability": score}
        layout_flags = []
        bounding_boxes = []
        
        # Analyze layout flags with heuristics
        try:
            doc = fitz.open(pdf_path)
            for page_idx, page in enumerate(doc):
                page_num = page_idx + 1
                signals = pymupdf_layout_quality_signals(page)
                if signals.get("n_x_clusters", 1) > 1:
                    if "Multi-column layout detected" not in layout_flags:
                        layout_flags.append("Multi-column layout detected")
                        breakdown["Column Penalty"] = -5
                        score -= 5
                    # Highlight right-column block for recruiter visual feedback
                    blocks = page.get_text("blocks")
                    for b in blocks:
                        if b[0] > page.rect.width * 0.45 and len(b) >= 4:
                            bounding_boxes.append(BoundingBox(
                                page=page_num, x0=float(b[0]), y0=float(b[1]), x1=float(b[2]), y1=float(b[3]),
                                severity="warning", reason="Multi-column layout element"
                            ))
                            break
                if signals.get("not_table_heavy", 1.0) == 0.0:
                    if "Tables detected" not in layout_flags:
                        layout_flags.append("Tables detected")
                        breakdown["Table Penalty"] = -10
                        score -= 10
                    drawings = page.get_drawings()
                    for d in drawings[:3]:
                        r = d.get("rect")
                        if r:
                            bounding_boxes.append(BoundingBox(
                                page=page_num, x0=float(r.x0), y0=float(r.y0), x1=float(r.x1), y1=float(r.y1),
                                severity="warning", reason="Table or graphic border detected"
                            ))
                            break
                if signals.get("char_density", 1.0) < 0.2:
                    image_count = len(page.get_images())
                    drawing_count = signals.get("n_drawings", 0)
                    if image_count > 0:
                        if "Images used instead of text" not in layout_flags:
                            layout_flags.append("Images used instead of text")
                    elif drawing_count > 100:
                        if "Text converted to vector shapes (Unparseable)" not in layout_flags:
                            layout_flags.append("Text converted to vector shapes (Unparseable)")
                    else:
                        if "Very sparse text (Low word count)" not in layout_flags:
                            layout_flags.append("Very sparse text (Low word count)")
            doc.close()
        except Exception:
            pass
            
        # Font health
        font_health = "Healthy"
        if "cid:" in parse_result.pymupdf_text.lower():
            font_health = "Warning: CID artifacts or garbled text detected."
            score -= 15
            breakdown["Font Issue Penalty"] = -15
            
        # Contact info visibility
        contact_info_visibility = {
            "email": bool(fields.get("email")),
            "phone": bool(fields.get("phone")),
        }
        
        # Section detection (found vs missed)
        found_sections = []
        missed_sections = []
        for sec in ["experience", "education", "skills"]:
            if fields.get(sec):
                found_sections.append(sec.capitalize())
            else:
                missed_sections.append(sec.capitalize())
                
        if not contact_info_visibility["email"]:
            missed_sections.append("Email")
        if not contact_info_visibility["phone"]:
            missed_sections.append("Phone")

        # Section Bonus
        section_bonus = min(20, len(found_sections) * 5)
        if section_bonus > 0:
            breakdown["Section Bonus"] = section_bonus
            score += section_bonus

        section_detection = {
            "found": found_sections,
            "missed": missed_sections,
        }
        
        # Date consistency
        date_consistency = "Consistent dates detected."
        if fields.get("experience"):
            for exp in fields["experience"]:
                # simple check if date fields are missing completely for any job
                if not exp.get("start") and not exp.get("end"):
                    date_consistency = "Inconsistent or missing dates detected in Experience."
                    break
                    
        # Clamp score between 0 and 100
        score = max(0, min(100, score))

        # Safe math consistency check without crashing production with assert
        expected_score = max(0, min(100, breakdown["Base Parseability"] + sum(v for k, v in breakdown.items() if k != "Base Parseability")))
        if score != expected_score:
            import logging
            logging.getLogger(__name__).warning("ATS score adjustment: raw=%s expected=%s", score, expected_score)
            score = expected_score

        # Convert bounding boxes to dicts for JSON serialization
        bbox_dicts = [
            {
                "page": b.page,
                "x0": b.x0,
                "y0": b.y0,
                "x1": b.x1,
                "y1": b.y1,
                "severity": b.severity,
                "reason": b.reason,
            }
            for b in bounding_boxes
        ]

        return {
            "score": score,
            "breakdown": breakdown,
            "layout_flags": layout_flags,
            "font_health": font_health,
            "contact_info_visibility": contact_info_visibility,
            "section_detection": section_detection,
            "keyword_preview": fields.get("skills", []),
            "date_consistency": date_consistency,
            "bounding_boxes": bbox_dicts,
            "limitations_disclaimer": "Informational parser diagnostic only. Passing this test does not guarantee ATS compatibility or hiring outcomes."
        }

