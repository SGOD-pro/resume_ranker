"""
extraction.py — Extraction data models
========================================
Schemas for the PDF extraction pipeline output.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExtractionResult:
    """Final output schema — wraps normalized fields with PDF metadata."""
    document_id: str
    domain: str
    domain_confidence: float
    extraction_strategy: str
    page_count: int
    layout_type: str
    fields: Dict[str, Any]
    warnings: List[str]
    metadata: Dict[str, Any]


@dataclass
class SectionContent:
    """Section content preserving both tagged and plain text.

    tagged_text: text with [JOB_TITLE], [DATE], [BULLET] tags (for assembler)
    plain_text:  raw text stripped of tags (for standalone parsers)
    source:      which extraction path found this section
    """
    plain_text: str = ""
    tagged_text: str = ""
    source: str = "unknown"
