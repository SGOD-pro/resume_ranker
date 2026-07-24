from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class LayoutStabilityEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        layout = extraction.layout_metadata
        if layout and layout.has_overlaps:
            score = 50.0
            flags.append(
                AtsFlag(
                    signal_name="layout_stability",
                    severity="severe",
                    message="Text overlap detected. The resume contains bounding boxes that intersect, which can confuse ATS parsers."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="layout_stability",
                    action="Remove overlapping text boxes or adjust line spacing so text elements do not visually intersect."
                )
            )
            
        signal = AtsSignal(
            name="layout_stability",
            score=score,
            weight=0.20,
            detail="Checked layout for overlapping bounding boxes."
        )
        
        return signal, flags, suggestions
