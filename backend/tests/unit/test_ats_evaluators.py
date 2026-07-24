import pytest
import hashlib
import json
import dataclasses
from src.extraction.domain_extraction import ExtractionResult, LayoutMetadata, ExtractedField, Provenance
from src.ats.ats_scoring_service import AtsScoringService
from src.ats.evaluators.layout_stability import LayoutStabilityEvaluator

class TestAtsEvaluators:
    def test_ats_determinism(self):
        """
        Determinism Test: A test that runs the exact same ExtractionResult 
        through AtsScoringService 100 times and asserts the output hash is identical every time.
        """
        # Create a mock ExtractionResult
        layout = LayoutMetadata(
            has_overlaps=False,
            column_boundaries=[100.0, 300.0],
            font_stats={"avg_size": 12.0},
            reading_order_gaps=[15.0],
            bounding_boxes=[]
        )
        
        extraction = ExtractionResult(
            document_id="doc-123",
            content_hash="hash-456",
            email=ExtractedField(value="test@example.com", confidence=1.0, provenance="deterministic"),
            phone=ExtractedField(value="555-0100", confidence=1.0, provenance="deterministic"),
            layout_metadata=layout
        )
        
        ats_svc = AtsScoringService()
        
        # We need a stable hash to compare. We will ignore `id` and `computed_at` 
        # since those are dynamic by definition.
        def get_stable_hash(result):
            # Serialize the dataclass to dict
            data = dataclasses.asdict(result)
            # Remove dynamic fields for deterministic hashing
            data.pop("id", None)
            data.pop("computed_at", None)
            
            # Serialize to JSON with sorted keys to ensure deterministic string
            json_str = json.dumps(data, sort_keys=True)
            return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

        # Run the first time to get base hash
        first_result = ats_svc.score(extraction)
        base_hash = get_stable_hash(first_result)
        
        # Run 99 more times and verify
        for _ in range(99):
            res = ats_svc.score(extraction)
            current_hash = get_stable_hash(res)
            assert current_hash == base_hash, "Determinism check failed! Outputs are not identical."

    def test_overlap_false_positive(self):
        """
        Overlap False-Positive Test: feeds a mock LayoutMetadata with heavily 
        intersecting bounding boxes to LayoutStabilityEvaluator and asserts it triggers correctly 
        without throwing exceptions.
        """
        # heavily intersecting bounding boxes
        boxes = [
            {"box": [10.0, 10.0, 100.0, 100.0], "text": "Intersecting text 1"},
            {"box": [50.0, 50.0, 150.0, 150.0], "text": "Intersecting text 2"},
            {"box": [75.0, 75.0, 200.0, 200.0], "text": "Intersecting text 3"},
        ]
        
        layout = LayoutMetadata(
            has_overlaps=True, # We flag has_overlaps to True explicitly based on the boxes
            bounding_boxes=boxes
        )
        
        extraction = ExtractionResult(
            document_id="overlap-doc",
            content_hash="overlap-hash",
            layout_metadata=layout
        )
        
        evaluator = LayoutStabilityEvaluator()
        
        # Should execute cleanly without exceptions
        signal, flags, suggestions = evaluator.evaluate(extraction)
        
        assert signal.name == "layout_stability"
        assert signal.score == 50.0, "Score should be penalized due to overlaps"
        
        assert any(f.signal_name == "layout_stability" and f.severity == "severe" for f in flags)
        assert any("overlap" in f.message.lower() for f in flags)
        assert len(suggestions) > 0
