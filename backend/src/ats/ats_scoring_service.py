from datetime import datetime
from uuid import uuid4
from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsResult
from src.ats.evaluators.layout_stability import LayoutStabilityEvaluator
from src.ats.evaluators.section_hierarchy import SectionHierarchyEvaluator
from src.ats.evaluators.reading_order import ReadingOrderEvaluator
from src.ats.evaluators.metric_coverage import MetricCoverageEvaluator
from src.ats.evaluators.chronology import ChronologyConsistencyEvaluator
from src.ats.evaluators.contact_presence import ContactPresenceEvaluator
from src.ats.evaluators.parseability import ParseabilityEvaluator

class AtsScoringService:
    def __init__(self):
        self.evaluators = [
            ParseabilityEvaluator(),
            LayoutStabilityEvaluator(),
            SectionHierarchyEvaluator(),
            ReadingOrderEvaluator(),
            MetricCoverageEvaluator(),
            ChronologyConsistencyEvaluator(),
            ContactPresenceEvaluator()
        ]
        
    def score(self, extraction: ExtractionResult) -> AtsResult:
        if not isinstance(extraction, ExtractionResult):
            raise TypeError("Raw PDF parsing is prohibited in the evaluation hot path. Pass an ExtractionResult.")
            
        signals = {}
        all_flags = []
        all_suggestions = []
        total_score = 0.0
        
        for evaluator in self.evaluators:
            signal, flags, suggestions = evaluator.evaluate(extraction)
            signals[signal.name] = signal
            all_flags.extend(flags)
            all_suggestions.extend(suggestions)
            
            total_score += signal.score * signal.weight
            
        # Handle instant fail
        if any(f.severity == "instant_fail" for f in all_flags):
            total_score = 0.0
            
        return AtsResult(
            id=str(uuid4()),
            document_id=extraction.document_id,
            signals=signals,
            ats_score=total_score,
            flags=all_flags,
            fix_suggestions=all_suggestions,
            computed_at=datetime.utcnow(),
            bounding_boxes=extraction.layout_metadata.bounding_boxes if extraction.layout_metadata else None
        )
