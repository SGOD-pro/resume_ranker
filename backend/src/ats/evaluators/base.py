from abc import ABC, abstractmethod
from src.extraction.domain_extraction import ExtractionResult
from src.ats.domain import AtsSignal, AtsFlag, FixSuggestion

class AtsEvaluator(ABC):
    @abstractmethod
    def evaluate(self, extraction: ExtractionResult) -> tuple[AtsSignal, list[AtsFlag], list[FixSuggestion]]:
        """
        Evaluate the extraction result and layout metadata.
        Returns a tuple of (Signal, Flags, FixSuggestions).
        """
        pass
