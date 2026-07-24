import pytest
import inspect
import socket
from typing import Any
from src.extraction.domain_extraction import ExtractionResult, LayoutMetadata, ExtractedField
from src.schemas.scoring import JobDescription
from src.scoring.scoring_service import ScoringService


class ExtractionResultMockFactory:
    @staticmethod
    def build_with_defaults() -> ExtractionResult:
        layout = LayoutMetadata(
            has_overlaps=False,
            column_boundaries=[50.0, 250.0],
            font_stats={"avg": 11.0},
            reading_order_gaps=[10.0],
            bounding_boxes=[{"x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 40.0, "text": "Header"}]
        )
        return ExtractionResult(
            document_id="doc-mock-1",
            content_hash="hash-mock-1",
            name=ExtractedField(value="John Doe", confidence=1.0, provenance="deterministic"),
            email=ExtractedField(value="john@example.com", confidence=1.0, provenance="deterministic"),
            skills=ExtractedField(value=["Python", "FastAPI", "Docker"], confidence=1.0, provenance="deterministic"),
            experience=ExtractedField(
                value=[{"title": "Senior Engineer", "years": 5}],
                confidence=1.0,
                provenance="deterministic"
            ),
            layout_metadata=layout
        )

    @staticmethod
    def build(skill_score: float = 0.8) -> ExtractionResult:
        # Construct mock ExtractionResult mapped to given target profile
        return ExtractionResult(
            document_id=f"doc-mock-{skill_score}",
            content_hash="hash-mock",
            skills=ExtractedField(value=["Python", "SQL"], confidence=skill_score, provenance="deterministic"),
            layout_metadata=LayoutMetadata(bounding_boxes=[])
        )


class JobMockFactory:
    @staticmethod
    def build_with_defaults() -> JobDescription:
        return JobDescription(
            title="Senior Backend Engineer",
            department="Engineering",
            description="Build scalable APIs",
            must_have_skills=["Python"],
            nice_to_have_skills=["Docker", "FastAPI"],
            min_years=3,
            max_years=8,
            required_degree="any",
            preferred_field="Computer Science",
            keywords=["api", "backend"],
            weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15}
        )


class TestArchitectureContracts:

    def test_extraction_result_json_round_trip(self):
        """
        1. The 'Round-Trip Serialization' Test
        What it tests: Can the ExtractionResult survive being saved to a database and fetched back without breaking its schema?
        """
        original_result = ExtractionResultMockFactory.build_with_defaults()
        
        # 2. Serialize to JSON string
        json_string = original_result.model_dump_json()
        
        # 3. Deserialize back to object
        fetched_result = ExtractionResult.model_validate_json(json_string)
        
        # 4. Assertions
        assert fetched_result.overall_confidence == original_result.overall_confidence
        assert fetched_result.layout_metadata is not None
        assert fetched_result.layout_metadata.bounding_boxes[0]["x0"] == original_result.layout_metadata.bounding_boxes[0]["x0"]

    def test_scoring_service_makes_zero_network_calls(self, monkeypatch):
        """
        2. The 'Zero I/O' Domain Test
        What it tests: Does the ScoringService try to make network calls when it shouldn't?
        """
        def patched_socket_connect(*args, **kwargs):
            raise ConnectionError("Network call detected in domain layer!")
            
        monkeypatch.setattr(socket.socket, "connect", patched_socket_connect)
        
        scoring_service = ScoringService()
        extraction = ExtractionResultMockFactory.build_with_defaults()
        job = JobMockFactory.build_with_defaults()
        
        result = scoring_service.score(extraction, job)
        assert result is not None

    def test_evaluate_100_mock_candidates(self):
        """
        3. The 'Mock Factory' Stress Test
        What it tests: Fast stress test of 100 mock candidates using factory pattern.
        """
        scoring_service = ScoringService()
        mock_job = JobMockFactory.build_with_defaults()
        
        candidates = [ExtractionResultMockFactory.build(skill_score=0.8) for _ in range(100)]
        
        for cand in candidates:
            res = scoring_service.score(cand, mock_job)
            assert res is not None

    def test_scoring_service_runs_synchronously(self):
        """
        4. The 'Sync-Async' Boundary Test
        What it tests: Are you mixing synchronous domain logic with async API calls incorrectly?
        """
        scoring_service = ScoringService()
        extraction = ExtractionResultMockFactory.build_with_defaults()
        mock_job = JobMockFactory.build_with_defaults()
        
        # Assert score is not a coroutine function
        assert not inspect.iscoroutinefunction(scoring_service.score)
        
        result = scoring_service.score(extraction, mock_job)
        assert result.skill_score >= 0.0

    def test_extraction_result_handles_missing_layout_metadata(self):
        """
        5. The 'Dirty Data' Deserialization Test
        What it tests: What happens when database returns missing/legacy layout_metadata?
        """
        dirty_json = """
        {
            "document_id": "legacy-doc",
            "content_hash": "legacy-hash",
            "overall_confidence": 0.9,
            "explicit_skills": ["Python"],
            "layout_metadata": null
        }
        """
        result = ExtractionResult.model_validate_json(dirty_json)
        
        assert result.layout_metadata is None
        assert result.document_id == "legacy-doc"
