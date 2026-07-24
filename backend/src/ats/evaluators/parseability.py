from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class ParseabilityEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        layout = extraction.layout_metadata
        # Check if bounding boxes are completely empty
        if not layout or not layout.bounding_boxes:
            score = 0.0
            flags.append(
                AtsFlag(
                    signal_name="parseability",
                    severity="instant_fail",
                    message="Document contains no parseable text (likely a scanned image or empty file)."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="parseability",
                    action="Upload a text-based PDF, not a scanned image."
                )
            )
            
        signal = AtsSignal(
            name="parseability",
            score=score,
            weight=0.0, # We don't weight it, it's an instant fail trigger
            detail="Checked document for parseable text layers."
        )
        
        return signal, flags, suggestions
