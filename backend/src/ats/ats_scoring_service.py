import logging
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AtsResult:
    ats_score: float
    warnings: List[str]

class AtsScoringService:
    def score(self, elements: List[Dict[str, Any]], extraction_quality: float = 0.0) -> AtsResult:
        """
        Computes an ATS compatibility score based purely on bounding box overlaps
        from the extracted elements.
        If elements are missing or overlap heavily, the score decreases.
        """
        if not elements:
            if extraction_quality >= 0.90:
                # PyMuPDF fast-path implies perfect reading order and no complex layout
                return AtsResult(ats_score=100.0, warnings=[])
            # If no elements were extracted and quality is low, it's either an image PDF or totally unparsable by ATS
            return AtsResult(ats_score=0.0, warnings=["No parsable elements found (possible image PDF)."])
            
        warnings = []
        overlap_count = 0
        total_elements = len(elements)
        
        # Simple O(N^2) bbox overlap check (in a real system, use an R-tree)
        # Bbox format expected from ODL: [x0, y0, x1, y1]
        for i, el1 in enumerate(elements):
            if getattr(el1, "get", None) is None:
                continue
            bbox1 = el1.get("bbox")
            if not bbox1 or len(bbox1) != 4:
                continue
                
            # Treat very small text as white-text/hidden
            text = el1.get("text", "")
            if len(text.strip()) > 5 and el1.get("font_size", 10) < 4:
                warnings.append(f"Hidden/tiny text detected: {text[:20]}...")
                overlap_count += 1
                continue
                
            for j in range(i + 1, total_elements):
                el2 = elements[j]
                if getattr(el2, "get", None) is None:
                    continue
                bbox2 = el2.get("bbox")
                if not bbox2 or len(bbox2) != 4:
                    continue
                    
                # Check for rectangle intersection
                # x0 < x1_other and x1 > x0_other and y0 < y1_other and y1 > y0_other
                if (bbox1[0] < bbox2[2] and bbox1[2] > bbox2[0] and
                    bbox1[1] < bbox2[3] and bbox1[3] > bbox2[1]):
                    overlap_count += 1
                    
        # Max penalty is 1.0
        penalty = min(1.0, (overlap_count / max(1, total_elements)) * 2)
        score = max(0.0, 1.0 - penalty)
        
        if overlap_count > 0:
            warnings.append(f"Detected {overlap_count} overlapping text elements (complex layout).")
            
        return AtsResult(ats_score=round(score * 100, 2), warnings=warnings)
