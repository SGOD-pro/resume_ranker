"""
document_service.py — End-to-end document processing
======================================================
Combines extraction and ranking into a single service for the
most common use case: upload PDFs + JD → ranked candidates.
"""

import json
from typing import Any, Dict, List

from src.services.extraction_service import ExtractionService
from src.services.ranking_service import RankingService
from src.schemas.scoring import JobDescription, ScoredCandidate


class DocumentService:
    """End-to-end document processing service."""

    def __init__(self):
        self.extraction = ExtractionService()
        self.ranking = RankingService()

    def process_and_rank(self, pdf_paths: List[str],
                         jd: JobDescription) -> List[ScoredCandidate]:
        """Extract all PDFs and rank candidates against a JD.

        Args:
            pdf_paths: List of PDF file paths to process
            jd: Job description for scoring

        Returns:
            List of ScoredCandidate sorted by score descending
        """
        candidates = []
        for path in pdf_paths:
            result = self.extraction.extract_single(path)
            # Serialize fields to ensure clean dict (no dataclass artifacts)
            fields = json.loads(json.dumps(
                result.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
            ))
            fields['_document_id'] = result.document_id
            candidates.append(fields)

        return self.ranking.rank_candidates(jd, candidates)
