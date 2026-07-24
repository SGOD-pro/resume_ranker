"""
extraction/parsers/experience_parser.py — V2 experience extraction
===================================================================
Adapter that feeds SectionRouter-sliced text into V1's ExperienceParser
regex engine unchanged.

V2 adds:
  - Confidence scoring based on number of date anchors found.
  - Source element IDs carried through for future bbox-based ATS checks.
  - UnresolvedChunk emission when experience section exists but parser
    returns 0 entries (indicates layout the regex couldn't handle).
"""

from __future__ import annotations

from src.extraction.domain import StructuralParse
from src.extraction.domain_extraction import ExtractedField, UnresolvedChunk
from src.extraction.parsers.section_router import SectionSlice, section_text
from src.extractors.experience.experience_parser import ExperienceParser as _V1Parser


class ExperienceParserV2:
    """Parse experience section from a StructuralParse using V1 regex engine."""

    def __init__(self) -> None:
        self._v1 = _V1Parser()

    def parse(
        self,
        parse: StructuralParse,
        sl: SectionSlice,
        document_id: str,
    ) -> tuple[ExtractedField | None, list[UnresolvedChunk]]:
        """
        Returns (ExtractedField | None, list[UnresolvedChunk]).

        ExtractedField.value = list[dict] matching V1's output schema:
          [{role, company, start, end, description, achievements}, ...]

        UnresolvedChunks are emitted when:
          - The section exists but the regex engine returns 0 entries.
        """
        text = section_text(parse, sl)
        if not text.strip():
            return None, []

        entries = self._v1.parse(text)

        if not entries:
            # Parser found the section but couldn't extract — enqueue to Nova
            chunk = UnresolvedChunk(
                field_name="experience",
                text=text,
                document_id=document_id,
                section="experience",
                confidence_so_far=0.0,
            )
            return None, [chunk]

        # Confidence: higher when more date-anchored entries found
        confidence = min(0.95, 0.70 + (len(entries) - 1) * 0.05)

        return (
            ExtractedField(
                value=entries,
                confidence=confidence,
                provenance="deterministic",
            ),
            [],
        )
