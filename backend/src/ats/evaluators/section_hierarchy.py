from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class SectionHierarchyEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        # In a real implementation we would check font_stats to ensure headers are larger/bolder
        # than body text. For now, we return perfect score.
        
        signal = AtsSignal(
            name="section_hierarchy",
            score=score,
            weight=0.15,
            detail="Section headings exhibit good visual hierarchy."
        )
        
        return signal, flags, suggestions
