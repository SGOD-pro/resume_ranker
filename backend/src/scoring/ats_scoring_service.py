"""
scoring/ats_scoring_service.py — ATS Engine entry point (Phase 5 stub)
"""

from src.extraction.domain_extraction import ExtractionResult

class AtsScoringService:
    def score(self, extraction: ExtractionResult):
        if not isinstance(extraction, ExtractionResult):
            raise TypeError("Raw PDF parsing is prohibited in the evaluation hot path. Pass an ExtractionResult.")
        
        # Phase 5 logic will go here
        return {"ats_score": 100.0}
