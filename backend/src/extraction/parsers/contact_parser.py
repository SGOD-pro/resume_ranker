"""
extraction/parsers/contact_parser.py — V2 contact extraction
=============================================================
Adapts V1's ContactParser to consume a StructuralParse instead of
raw PyMuPDF text and tag strings.

V2 input path (replacing PyMuPDF tag-based approach):
  - Name:     heading-level-1 element on page 1 (ODL structural signal)
  - Email/phone/linkedin/github: regex on preamble flat_text (same as V1)
  - Location: regex on preamble flat_text (same as V1)
  - Fallback: if heading-level-1 is absent, fall back to V1's heuristic
              line scanner on preamble text.

Confidence rules:
  - Name from H1 heading element:  0.95
  - Name from heuristic scan:      0.75
  - Email (regex match):           1.00
  - Phone (regex match):           0.95
  - LinkedIn/GitHub (regex match): 1.00
  - Location (label-based):        0.85
  - Location (heuristic):          0.65

This file imports from src.extractors.contact.contact_parser to reuse
the battle-tested regex engine unchanged. Only the input adapter is new.
"""

from __future__ import annotations

import re

from src.extraction.domain import OdlElement, StructuralParse
from src.extraction.domain_extraction import ExtractedField
from src.extractors.contact.contact_parser import ContactParser as _V1ContactParser
from src.extractors.contact.contact_parser import _is_name_line
from src.registries.section_registry import resolve as _resolve

# Preamble scan limits
_MAX_PREAMBLE_PAGE: int = 2
_MAX_PREAMBLE_ELEMENTS: int = 30


class ContactParserV2:
    """
    Extract contact fields from a StructuralParse.

    Call order:
      1. Attempt name from ODL H1 heading element (page 1).
      2. Feed preamble text into V1 ContactParser for all other fields.
      3. If name not found in step 1, fall back to V1 heuristic on preamble.
    """

    def __init__(self) -> None:
        self._v1 = _V1ContactParser()

    def parse(self, parse: StructuralParse) -> dict[str, ExtractedField | None]:
        """
        Returns a dict with keys: name, email, phone, linkedin, github, location.
        All values are ExtractedField instances or None if not found.
        """
        preamble_text, preamble_elements = self._get_preamble(parse)

        # 1. Name from ODL structure
        name_field = self._extract_name_from_structure(parse)

        # 2. All other fields via V1 regex on preamble text
        v1_result = self._v1.parse(
            full_width_text=preamble_text,
            raw_text=preamble_text,
        )

        # 3. Fallback name from V1 heuristic
        if name_field is None and v1_result.get("name"):
            name_field = ExtractedField(
                value=v1_result["name"],
                confidence=0.75,
                provenance="deterministic",
            )

        return {
            "name":     name_field,
            "email":    self._wrap(v1_result.get("email"), 1.00),
            "phone":    self._wrap(v1_result.get("phone"), 0.95),
            "linkedin": self._wrap(v1_result.get("linkedin"), 1.00),
            "github":   self._wrap(v1_result.get("github"), 1.00),
            "location": self._wrap(v1_result.get("location"), 0.75),
        }

    # ------------------------------------------------------------------

    def _extract_name_from_structure(
        self, parse: StructuralParse
    ) -> ExtractedField | None:
        """
        Find the first heading-level-1 element on page 1 and treat it as the name.
        Only accepts it if the text passes the V1 name heuristic (not a section header).
        """
        for elem in parse.kids:
            if elem.page > 1:
                break
            if elem.type == "heading" and elem.heading_level == 1:
                text = elem.text.strip()
                if text and _is_name_line(text):
                    return ExtractedField(
                        value=text,
                        confidence=0.95,
                        provenance="deterministic",
                        source_elements=(elem.element_id,) if elem.element_id else (),
                    )
                # If _is_name_line rejects it, try splitting by common contact separators
                # e.g. "John Smith | john@example.com" → "John Smith"
                if "|" in text or "•" in text:
                    candidate = re.split(r"[|•●]", text)[0].strip()
                    if candidate and _is_name_line(candidate):
                        return ExtractedField(
                            value=candidate,
                            confidence=0.90,
                            provenance="deterministic",
                            source_elements=(elem.element_id,) if elem.element_id else (),
                        )
        return None

    def _get_preamble(
        self, parse: StructuralParse
    ) -> tuple[str, tuple[OdlElement, ...]]:
        """
        Return the text of all page-1 elements before the first non-contact
        section heading, or up to 30 elements — whichever comes first.
        """
        lines: list[str] = []
        elements = []
        for count, elem in enumerate(parse.kids, start=1):
            if elem.page > _MAX_PREAMBLE_PAGE:
                break
            if count > _MAX_PREAMBLE_ELEMENTS:
                break
            # Stop at first recognised section that isn't contact
            if elem.type == "heading":
                resolved = _resolve(elem.text)
                if resolved and resolved not in {"summary"}:
                    break
            if not elem.hidden and elem.text:
                lines.append(elem.text)
                elements.append(elem)
        return "\n".join(lines), tuple(elements)

    @staticmethod
    def _wrap(value: str | None, confidence: float) -> ExtractedField | None:
        if not value:
            return None
        return ExtractedField(
            value=value,
            confidence=confidence,
            provenance="deterministic",
        )
