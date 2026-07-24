from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class ReadingOrderEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        layout = extraction.layout_metadata
        if layout and layout.reading_order_gaps:
            score -= (len(layout.reading_order_gaps) * 10)
            score = max(0.0, score)
            
            flags.append(
                AtsFlag(
                    signal_name="reading_order",
                    severity="moderate",
                    message="Detected visual jumps in reading order. Columns or embedded tables may not parse sequentially."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="reading_order",
                    action="Use standard single-column formatting. Avoid tables for laying out sections."
                )
            )
            
        signal = AtsSignal(
            name="reading_order",
            score=score,
            weight=0.20,
            detail="Checked sequential parsing order."
        )
        
        return signal, flags, suggestions
