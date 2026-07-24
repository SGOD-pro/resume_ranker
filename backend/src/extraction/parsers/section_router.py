"""
extraction/parsers/section_router.py — ODL heading → canonical section
========================================================================
Maps OdlElement heading text to one of the canonical section names defined
in section_registry.CANONICAL_SECTIONS.

Input:  StructuralParse.kids  (heading elements)
Output: list of (canonical_section, start_element_index, end_element_index)
        — slices that callers use to extract section text.

Design decisions:
  - Delegates all alias resolution to the existing section_registry.resolve().
    No new alias lists here — single source of truth is preserved.
  - Heading elements (type == "heading") act as section delimiters.
  - Non-heading elements between two headings belong to the first heading's section.
  - Sections not resolved by the registry produce a "UNRECOGNISED" entry that
    DeterministicExtractionService enqueues as an UnresolvedChunk.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.extraction.domain import OdlElement, StructuralParse
from src.registries.section_registry import resolve as _resolve


@dataclass(frozen=True)
class SectionSlice:
    """
    A contiguous range of OdlElement indices belonging to one canonical section.

    Elements from start (inclusive) to end (exclusive).
    header_text is the raw heading text that was resolved.
    """

    canonical: str        # resolved canonical name or "UNRECOGNISED"
    header_text: str      # the raw heading text as ODL gave it
    start: int            # index into StructuralParse.kids (inclusive) — points to heading
    end: int              # index into StructuralParse.kids (exclusive)


def route(parse: StructuralParse) -> list[SectionSlice]:
    """
    Partition StructuralParse.kids into SectionSlices by heading elements.

    Algorithm:
      1. Walk elements in document order.
      2. Any heading element starts a new section.
      3. The section contains all subsequent non-heading elements until the
         next heading or end of document.
      4. If no headings precede a block of content, that content is emitted
         under "PREAMBLE" — the contact block lives here on most resumes.
    """
    kids = parse.kids
    n = len(kids)
    slices: list[SectionSlice] = []

    current_header: str | None = None
    current_canonical: str = "PREAMBLE"
    current_start: int = 0

    for i, elem in enumerate(kids):
        if elem.type != "heading":
            continue

        # Close previous slice
        if i > current_start:
            slices.append(
                SectionSlice(
                    canonical=current_canonical,
                    header_text=current_header or "PREAMBLE",
                    start=current_start,
                    end=i,
                )
            )

        # Start new slice
        raw = elem.text.strip()
        resolved = _resolve(raw)
        current_canonical = resolved if resolved else "UNRECOGNISED"
        current_header = raw
        current_start = i

    # Final slice (from last heading to end)
    if current_start < n:
        slices.append(
            SectionSlice(
                canonical=current_canonical,
                header_text=current_header or "PREAMBLE",
                start=current_start,
                end=n,
            )
        )

    return slices


def section_text(parse: StructuralParse, sl: SectionSlice) -> str:
    """
    Return joined element text for a SectionSlice (excluding the heading itself).

    Joins all non-heading element texts with newlines.
    """
    kids = parse.kids
    parts: list[str] = []
    for elem in kids[sl.start : sl.end]:
        if elem.type == "heading":
            continue   # skip the heading delimiter itself
        if elem.text:
            parts.append(elem.text)
    return "\n".join(parts)


def section_elements(parse: StructuralParse, sl: SectionSlice) -> tuple[OdlElement, ...]:
    """Return the OdlElement objects (excluding heading) for a SectionSlice."""
    kids = parse.kids
    return tuple(
        e for e in kids[sl.start : sl.end] if e.type != "heading"
    )
