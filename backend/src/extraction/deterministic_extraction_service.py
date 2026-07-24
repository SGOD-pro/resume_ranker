"""
extraction/deterministic_extraction_service.py — Phase 2 orchestrator
=======================================================================
Runs the full deterministic extraction pipeline on a StructuralParse.

Pipeline order:
  1. SectionRouter partitions kids[] into canonical section slices.
  1b. **Hybrid fallback:** If the ODL heading-based router yields < 3
      canonical sections, run V1's SectionDetector on flat_text and merge
      the results (gap-fill, don't overwrite).
  2. ContactParserV2 extracts name/email/phone/linkedin/github/location.
  2b. **Enhanced name fallback:** If no name found via ODL H1, scan
      flat_text with V1's full heuristic (font-size, line-position).
  3. ExperienceParserV2 extracts experience entries.
  3b. **Full-text fallback:** If no experience section found, run V1's
      ExperienceParser on flat_text using date-regex anchors.
  4. EducationParserV2  extracts education entries.
  4b. **Full-text fallback:** If no education section found, run V1's
      EducationParser on flat_text using degree-keyword anchors.
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

# V1 section detection for hybrid fallback (Fix 1)
from src.extractors.layout.section_detector import SectionDetector as _V1SectionDetector

# V1 parsers for full-text fallback (Fix 2)
from src.extractors.experience.experience_parser import ExperienceParser as _V1ExpParser
from src.extractors.education.education_parser import EducationParser as _V1EduParser

# V1 contact parser for enhanced name extraction (Fix 3)
from src.extractors.contact.contact_parser import ContactParser as _V1ContactParser

logger = logging.getLogger(__name__)

# Minimum number of canonical sections from ODL before triggering fallback
_MIN_SECTIONS_FOR_TRUST = 3


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
        self._v1_section_detector = _V1SectionDetector()
        self._v1_exp_parser = _V1ExpParser()
        self._v1_edu_parser = _V1EduParser()
        self._v1_contact = _V1ContactParser()

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

        # ── 1. Section routing (ODL heading-based) ───────────────────
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

        # ── 1b. Hybrid fallback: V1 SectionDetector on flat_text ─────
        #   When ODL heading-based routing yields too few sections,
        #   run V1's plain-text section detector and merge results.
        fallback_sections: dict[str, str] = {}
        real_sections = [k for k in section_map if k not in ("PREAMBLE",)]
        if len(real_sections) < _MIN_SECTIONS_FOR_TRUST:
            fallback_sections = self._v1_section_detector.detect(
                structural.flat_text
            )
            logger.debug(
                "Fallback SectionDetector found %d sections for doc %s: %s",
                len(fallback_sections),
                document_id[:12],
                list(fallback_sections.keys()),
            )

        # ── 2. Contact extraction ────────────────────────────────────
        contact_fields = self._contact.parse(structural)
        result.name     = contact_fields.get("name")
        result.email    = contact_fields.get("email")
        result.phone    = contact_fields.get("phone")
        result.linkedin = contact_fields.get("linkedin")
        result.github   = contact_fields.get("github")
        result.location = contact_fields.get("location")

        # ── 2b. Enhanced name fallback ───────────────────────────────
        #   If V2 ContactParser didn't find a name, try V1's full
        #   heuristic on the flat_text (handles more layout variants).
        if result.name is None:
            v1_contact_result = self._v1_contact.parse(
                full_width_text=structural.flat_text[:1000],
                raw_text=structural.flat_text[:1000],
            )
            v1_name = v1_contact_result.get("name")
            if v1_name and v1_name != "Unknown Candidate":
                result.name = ExtractedField(
                    value=v1_name,
                    confidence=0.75,
                    provenance="deterministic",
                )
            else:
                # Still no name — emit unresolved chunk
                unresolved.append(
                    UnresolvedChunk(
                        field_name="name",
                        text=structural.flat_text[:500],
                        document_id=document_id,
                        section="PREAMBLE",
                        confidence_so_far=0.0,
                    )
                )

        # ── 3. Experience ────────────────────────────────────────────
        if "experience" in section_map:
            exp_field, exp_chunks = self._experience.parse(
                structural, section_map["experience"], document_id
            )
            result.experience = exp_field
            unresolved.extend(exp_chunks)

        # ── 3b. Experience full-text fallback ────────────────────────
        #   If ODL routing didn't find an experience section, try:
        #     a) V1 SectionDetector fallback text for experience
        #     b) V1 ExperienceParser on full flat_text
        if result.experience is None:
            exp_text = fallback_sections.get("experience", "")
            if exp_text:
                entries = self._v1_exp_parser.parse(exp_text)
                if entries:
                    result.experience = ExtractedField(
                        value=entries,
                        confidence=0.80,
                        provenance="deterministic",
                    )
                    logger.debug(
                        "Experience recovered via fallback section_detector "
                        "for doc %s: %d entries",
                        document_id[:12], len(entries),
                    )

        if result.experience is None:
            # Last resort: run V1 parser on entire flat_text
            entries = self._v1_exp_parser.parse(structural.flat_text)
            if entries:
                result.experience = ExtractedField(
                    value=entries,
                    confidence=0.65,
                    provenance="deterministic",
                )
                logger.debug(
                    "Experience recovered via full-text fallback "
                    "for doc %s: %d entries",
                    document_id[:12], len(entries),
                )
            else:
                unresolved.append(
                    UnresolvedChunk(
                        field_name="experience",
                        text=structural.flat_text[:2000],
                        document_id=document_id,
                        section="experience",
                        confidence_so_far=0.0,
                    )
                )

        # ── 4. Education ─────────────────────────────────────────────
        if "education" in section_map:
            edu_field, edu_chunks = self._education.parse(
                structural, section_map["education"], document_id
            )
            result.education = edu_field
            unresolved.extend(edu_chunks)

        # ── 4b. Education full-text fallback ─────────────────────────
        if result.education is None:
            edu_text = fallback_sections.get("education", "")
            if edu_text:
                entries = self._v1_edu_parser.parse(edu_text)
                if entries:
                    result.education = ExtractedField(
                        value=entries,
                        confidence=0.80,
                        provenance="deterministic",
                    )
                    logger.debug(
                        "Education recovered via fallback section_detector "
                        "for doc %s: %d entries",
                        document_id[:12], len(entries),
                    )

        if result.education is None:
            entries = self._v1_edu_parser.parse(structural.flat_text)
            if entries:
                result.education = ExtractedField(
                    value=entries,
                    confidence=0.65,
                    provenance="deterministic",
                )
                logger.debug(
                    "Education recovered via full-text fallback "
                    "for doc %s: %d entries",
                    document_id[:12], len(entries),
                )
            else:
                unresolved.append(
                    UnresolvedChunk(
                        field_name="education",
                        text=structural.flat_text[:2000],
                        document_id=document_id,
                        section="education",
                        confidence_so_far=0.0,
                    )
                )

        # ── 5. Skills ────────────────────────────────────────────────
        skills_sl = section_map.get("skills")  # may be None → full-text scan
        skills_field, skills_chunks = self._skills.parse(
            structural, skills_sl, document_id
        )
        result.skills = skills_field
        unresolved.extend(skills_chunks)

        # ── 6. Summary ───────────────────────────────────────────────
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
