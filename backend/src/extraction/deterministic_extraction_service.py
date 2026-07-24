"""
extraction/deterministic_extraction_service.py — Phase 2 orchestrator
=======================================================================
Runs the full deterministic extraction pipeline on a StructuralParse.

Pipeline order:
  1. SectionRouter partitions kids[] into canonical section slices.
  2. ContactParserV2 extracts name/email/phone/linkedin/github/location.
  3. ExperienceParserV2 extracts experience entries.
  4. EducationParserV2  extracts education entries.
  5. SkillsParserV2     extracts skills.
  6. Summary is extracted as raw text from the summary section slice.
  7. Unrecognised section slices are emitted as UnresolvedChunks (for
     Phase 3 Nova fallback).

What this service does NOT do:
  - No LLM calls. Ever.
  - No S3 reads/writes (caller's responsibility).
  - No database writes.
  - No scoring.

Per boundaries.md §3: this class takes StructuralParse, returns ExtractionResult.
"""

from __future__ import annotations

import logging

from src.extraction.domain import StructuralParse
from src.extraction.domain_extraction import (
    ExtractedField,
    ExtractionResult,
    UnresolvedChunk,
)
from src.extraction.parsers.contact_parser import ContactParserV2
from src.extraction.parsers.education_parser import EducationParserV2
from src.extraction.parsers.experience_parser import ExperienceParserV2
from src.extraction.parsers.section_router import SectionSlice, route, section_text
from src.extraction.parsers.skills_parser import SkillsParserV2

logger = logging.getLogger(__name__)


class DeterministicExtractionService:
    """
    StructuralParse → ExtractionResult.

    Instantiate once; parse() is stateless and thread-safe.
    """

    def __init__(self) -> None:
        self._contact = ContactParserV2()
        self._experience = ExperienceParserV2()
        self._education = EducationParserV2()
        self._skills = SkillsParserV2()

    def parse(self, structural: StructuralParse, document_id: str) -> ExtractionResult:
        """
        Run all deterministic parsers over a StructuralParse.

        Args:
            structural: Output from StructuralParsingService.parse().
            document_id: Used for UnresolvedChunk correlation / logging.

        Returns:
            ExtractionResult with all extracted fields and any unresolved chunks.
        """
        result = ExtractionResult(
            document_id=document_id,
            content_hash=structural.content_hash,
        )
        unresolved: list[UnresolvedChunk] = []

        # ── 1. Section routing ───────────────────────────────────────────
        slices = route(structural)
        logger.debug(
            "SectionRouter produced %d slices for doc %s: %s",
            len(slices),
            document_id[:12],
            [sl.canonical for sl in slices],
        )

        section_map: dict[str, SectionSlice] = {}
        for sl in slices:
            if sl.canonical not in ("PREAMBLE", "UNRECOGNISED"):
                # Keep first occurrence of each canonical section
                section_map.setdefault(sl.canonical, sl)
            elif sl.canonical == "UNRECOGNISED":
                # Unknown section — emit text as unresolved chunk
                txt = section_text(structural, sl)
                if txt.strip():
                    unresolved.append(
                        UnresolvedChunk(
                            field_name="unknown",
                            text=txt[:2000],
                            document_id=document_id,
                            section=sl.header_text,
                            confidence_so_far=0.0,
                        )
                    )

        # ── 2. Contact extraction ────────────────────────────────────────
        contact_fields = self._contact.parse(structural)
        result.name     = contact_fields.get("name")
        result.email    = contact_fields.get("email")
        result.phone    = contact_fields.get("phone")
        result.linkedin = contact_fields.get("linkedin")
        result.github   = contact_fields.get("github")
        result.location = contact_fields.get("location")

        # Emit unresolved chunk for name if not found
        if result.name is None:
            unresolved.append(
                UnresolvedChunk(
                    field_name="name",
                    text=structural.flat_text[:500],
                    document_id=document_id,
                    section="PREAMBLE",
                    confidence_so_far=0.0,
                )
            )

        # ── 3. Experience ────────────────────────────────────────────────
        if "experience" in section_map:
            exp_field, exp_chunks = self._experience.parse(
                structural, section_map["experience"], document_id
            )
            result.experience = exp_field
            unresolved.extend(exp_chunks)

        # ── 4. Education ─────────────────────────────────────────────────
        if "education" in section_map:
            edu_field, edu_chunks = self._education.parse(
                structural, section_map["education"], document_id
            )
            result.education = edu_field
            unresolved.extend(edu_chunks)

        # ── 5. Skills ────────────────────────────────────────────────────
        skills_sl = section_map.get("skills")  # may be None → full-text scan
        skills_field, skills_chunks = self._skills.parse(
            structural, skills_sl, document_id
        )
        result.skills = skills_field
        unresolved.extend(skills_chunks)

        # ── 6. Summary ───────────────────────────────────────────────────
        if "summary" in section_map:
            summary_text = section_text(structural, section_map["summary"])
            if summary_text.strip():
                result.summary = ExtractedField(
                    value=summary_text.strip(),
                    confidence=0.90,
                    provenance="deterministic",
                )

        result.unresolved = unresolved

        logger.info(
            "Extraction complete doc=%s deterministic_ratio=%.2f unresolved=%d",
            document_id[:12],
            result.deterministic_ratio,
            len(unresolved),
        )

        return result
