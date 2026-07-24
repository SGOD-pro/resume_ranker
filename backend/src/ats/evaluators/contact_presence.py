from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class ContactPresenceEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 100.0
        
        has_email = bool(extraction.email and extraction.email.value)
        has_phone = bool(extraction.phone and extraction.phone.value)
        
        if not (has_email or has_phone):
            score = 0.0
            flags.append(
                AtsFlag(
                    signal_name="contact_presence",
                    severity="severe",
                    message="No email address or phone number detected."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="contact_presence",
                    action="Ensure your email and phone number are clearly listed at the top of the resume in a single-column layout."
                )
            )
        elif not has_email:
            score = 50.0
            flags.append(
                AtsFlag(
                    signal_name="contact_presence",
                    severity="severe",
                    message="No email address detected."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="contact_presence",
                    action="Add a professional email address."
                )
            )
        elif not has_phone:
            score = 80.0
            flags.append(
                AtsFlag(
                    signal_name="contact_presence",
                    severity="moderate",
                    message="No phone number detected."
                )
            )
            suggestions.append(
                FixSuggestion(
                    signal_name="contact_presence",
                    action="Add a contact phone number."
                )
            )
            
        signal = AtsSignal(
            name="contact_presence",
            score=score,
            weight=0.15,
            detail="Checked for critical contact information."
        )
        
        return signal, flags, suggestions
