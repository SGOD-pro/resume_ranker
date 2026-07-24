"""
extraction/parsers/skills_parser.py — V2 skills extraction
===========================================================
Adapter that feeds SectionRouter-sliced skills section text + full document
flat_text into V1's SkillsParser dictionary engine unchanged.

V2 adds:
  - Deduplication of skills that appear in both section and full-text scan.
  - Confidence = 0.95 when ≥3 skills found in the skills section itself
    (structural signal: the skills section exists and is non-trivial).
  - Confidence = 0.75 when skills come only from full-text scan (no
    dedicated skills section found or it yielded < 3 skills).
"""

from __future__ import annotations

from src.extraction.domain import StructuralParse
from src.extraction.domain_extraction import ExtractedField, UnresolvedChunk
from src.extraction.parsers.section_router import SectionSlice, section_text
from src.extractors.skills.skills_parser import SkillsParser as _V1Parser


class SkillsParserV2:
    """Parse skills from a StructuralParse using V1 dictionary engine."""

    def __init__(self) -> None:
        self._v1 = _V1Parser()

    def parse(
        self,
        parse: StructuralParse,
        sl: SectionSlice | None,
        document_id: str,
    ) -> tuple[ExtractedField | None, list[UnresolvedChunk]]:
        """
        sl may be None if no skills section was detected — in that case we
        do a full-text dictionary scan only.

        Returns (ExtractedField | None, list[UnresolvedChunk]).
        ExtractedField.value = list[str] of canonical skill names.
        """
        skills_section_text = section_text(parse, sl) if sl is not None else ""
        full_text = parse.flat_text

        skills = self._v1.parse(
            skills_section=skills_section_text,
            full_text=full_text,
            also_scan_fulltext=True,
        )

        if not skills:
            # No skills at all — emit unresolved chunk
            chunk = UnresolvedChunk(
                field_name="skills",
                text=full_text[:2000],  # cap at 2000 chars for SQS payload
                document_id=document_id,
                section="skills",
                confidence_so_far=0.0,
            )
            return None, [chunk]

        # Confidence depends on whether a dedicated skills section existed
        min_section_skills: int = 3
        section_skills_count: int = 0
        if skills_section_text:
            section_skills_count = len(
                self._v1.parse(
                    skills_section=skills_section_text,
                    full_text="",
                    also_scan_fulltext=False,
                )
            )
        confidence = 0.95 if section_skills_count >= min_section_skills else 0.75


        return (
            ExtractedField(
                value=skills,
                confidence=confidence,
                provenance="deterministic",
            ),
            [],
        )
