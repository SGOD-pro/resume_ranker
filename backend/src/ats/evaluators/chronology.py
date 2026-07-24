from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator
from dateutil.parser import parse
from datetime import datetime

class ChronologyConsistencyEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        experience = extraction.experience
        if experience and experience.value:
            entries = experience.value
            last_date = None
            out_of_order = False
            
            for entry in entries:
                end_date_str = entry.get("end_date") if isinstance(entry, dict) else getattr(entry, "end_date", None)
                
                if end_date_str:
                    try:
                        # Simple check assuming "Present" is handled or ignored
                        if end_date_str.lower() != "present":
                            current_date = parse(end_date_str)
                            if last_date and current_date > last_date:
                                out_of_order = True
                            last_date = current_date
                    except Exception:
                        pass
                        
            if out_of_order:
                score = 50.0
                flags.append(
                    AtsFlag(
                        signal_name="chronology",
                        severity="moderate",
                        message="Experience entries do not appear to be in reverse-chronological order."
                    )
                )
                suggestions.append(
                    FixSuggestion(
                        signal_name="chronology",
                        action="Order your work experience in strict reverse-chronological order (newest first)."
                    )
                )
                
        signal = AtsSignal(
            name="chronology",
            score=score,
            weight=0.15,
            detail="Checked experience for chronological consistency."
        )
        
        return signal, flags, suggestions
