"""
extraction/parsers/education_parser.py — V2 education extraction
================================================================
Adapter that feeds SectionRouter-sliced text into V1's EducationParser
regex engine unchanged.
"""

from __future__ import annotations

from src.extraction.domain import StructuralParse
from src.extraction.domain_extraction import ExtractedField, UnresolvedChunk
from src.extraction.parsers.section_router import SectionSlice, section_text
from src.extractors.education.education_parser import EducationParser as _V1Parser


class EducationParserV2:
    """Parse education section from a StructuralParse using V1 regex engine."""

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

        ExtractedField.value = list[dict]:
          [{degree, institution, start, end, grade}, ...]
        """
        text = section_text(parse, sl)
        if not text.strip():
            return None, []

        entries = self._v1.parse(text)

        if not entries:
            chunk = UnresolvedChunk(
                field_name="education",
                text=text,
                document_id=document_id,
                section="education",
                confidence_so_far=0.0,
            )
            return None, [chunk]

        # Degree keyword matched → high confidence
        confidence = 0.90

        return (
            ExtractedField(
                value=entries,
                confidence=confidence,
                provenance="deterministic",
            ),
            [],
        )
