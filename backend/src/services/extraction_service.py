"""
extraction_service.py — PDF extraction orchestrator
=====================================================
Thin service wrapper around PDFPipelineV3 for dependency injection
and FastAPI integration.
"""

from typing import List
from src.core.pipeline import PDFPipelineV3
from src.schemas.extraction import ExtractionResult


class ExtractionService:
    """Service layer for PDF extraction."""

    def __init__(self):
        self.pipeline = PDFPipelineV3()

    def extract_single(self, pdf_path: str) -> ExtractionResult:
        """Extract structured data from a single PDF."""
        return self.pipeline.extract(pdf_path)

    def extract_batch(self, pdf_paths: List[str]) -> List[ExtractionResult]:
        """Extract structured data from multiple PDFs."""
        return [self.pipeline.extract(p) for p in pdf_paths]
