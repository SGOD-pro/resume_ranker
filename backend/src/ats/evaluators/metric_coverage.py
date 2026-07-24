import re
from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion
from src.ats.evaluators.base import AtsEvaluator

class MetricCoverageEvaluator(AtsEvaluator):
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        flags = []
        suggestions = []
        score = 0.0
        
        # Regex to find numbers, percentages, currencies
        metric_pattern = re.compile(r'(\$[\d,]+(\.\d+)?|[€£]?\d+[\d,]*%|\d+[\d,]*\+)|\b\d+\b')
        
        experience = extraction.experience
        if experience and experience.value:
            # Experience is a list of entries (dict or objects, depending on parser)
            entries = experience.value
            total_bullets = 0
            bullets_with_metrics = 0
            
            for entry in entries:
                desc = entry.get("description", "") if isinstance(entry, dict) else getattr(entry, "description", "")
                if desc:
                    # Very simple bullet split
                    bullets = [b for b in desc.split("\n") if b.strip()]
                    total_bullets += len(bullets)
                    for bullet in bullets:
                        if metric_pattern.search(bullet):
                            bullets_with_metrics += 1
            
            if total_bullets > 0:
                coverage = bullets_with_metrics / total_bullets
                score = min(100.0, coverage * 200.0)  # 50% coverage gets 100 score
                
            if score < 50.0:
                flags.append(
                    AtsFlag(
                        signal_name="metric_coverage",
                        severity="moderate",
                        message="Low usage of quantifiable metrics in experience descriptions."
                    )
                )
                suggestions.append(
                    FixSuggestion(
                        signal_name="metric_coverage",
                        action="Include specific numbers, percentages, or dollar amounts to quantify your achievements."
                    )
                )
        else:
            # No experience section found
            score = 0.0
            flags.append(
                AtsFlag(
                    signal_name="metric_coverage",
                    severity="severe",
                    message="No work experience found to evaluate for metrics."
                )
            )
            
        signal = AtsSignal(
            name="metric_coverage",
            score=score,
            weight=0.15,
            detail="Checked for quantifiable metrics in experience."
        )
        
        return signal, flags, suggestions
