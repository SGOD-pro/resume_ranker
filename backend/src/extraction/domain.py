"""
extraction/domain.py — Structural parsing domain types
=======================================================
The ONLY place in the codebase that knows ODL's raw field names.
Downstream code consumes these frozen dataclasses exclusively.

ODL JSON field names use spaces ("page number", "bounding box", etc.)
All mapping from those keys lives here or in structural_parsing_service.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# ---------------------------------------------------------------------------
# ODL element types recognised in the resume context
# ---------------------------------------------------------------------------

OdlElementType = Literal["heading", "paragraph", "table", "list", "caption", "image"]


@dataclass(frozen=True)
class OdlElement:
    """
    One content element from opendataloader-pdf output.

    Coordinate system: PDF points, origin at bottom-left of page.
    bounding_box = (left, bottom, right, top) — same as ODL's "bounding box" field.
    """

    type: str                                           # heading | paragraph | table | list | ...
    text: str                                           # "content" in ODL JSON
    bounding_box: tuple[float, float, float, float]     # (left, bottom, right, top)
    hidden: bool                                        # "hidden text" flag
    page: int                                           # 1-indexed "page number"
    heading_level: int | None = None                    # only for type == "heading"
    element_id: int | None = None                       # ODL's "id" field


@dataclass(frozen=True)
class StructuralParse:
    """
    Immutable wrapper around a single opendataloader-pdf parse result.

    This is the anti-corruption boundary output type.
    Nothing outside StructuralParsingService produces this; nothing
    outside the extraction context reads ODL's raw field names.
    """

    kids: tuple[OdlElement, ...]        # all content elements, in document order
    markdown: str                        # full markdown string (empty if not requested)
    page_count: int
    parser_version: str                 # opendataloader-pdf version string
    content_hash: str                   # SHA-256 of the source PDF bytes (dedup key)

    @property
    def flat_text(self) -> str:
        """All element text joined — convenience for regex parsers."""
        return "\n".join(e.text for e in self.kids if e.text)


@dataclass
class StructuralParseError(Exception):
    """
    Raised by StructuralParsingService when ODL cannot parse a PDF.
    Carries the document_id for log correlation and the raw error message.
    """

    document_id: str
    reason: str
    retriable: bool = False             # True for transient JVM failures

    def __str__(self) -> str:
        return f"StructuralParseError [{self.document_id}]: {self.reason}"


@dataclass(frozen=True)
class OdlParseCache:
    """
    Value object describing a cached ODL result in S3.
    Used by StructuralParsingService to avoid re-running ODL on identical bytes.
    """

    content_hash: str
    s3_key: str                         # odl-cache/{content_hash}.json
    parser_version: str


# ---------------------------------------------------------------------------
# ODL JSON → OdlElement mapping helper
# ---------------------------------------------------------------------------

def _element_from_odl_dict(raw: dict[str, Any]) -> OdlElement:
    """
    Map one raw ODL JSON element dict → OdlElement.

    ODL field names use spaces.  This is the ONE place that knows them.
    Missing optional fields default to safe values so the caller never
    needs to defensive-check them.
    """
    bbox_raw = raw.get("bounding box", [0.0, 0.0, 0.0, 0.0])
    bbox: tuple[float, float, float, float] = (
        float(bbox_raw[0]),
        float(bbox_raw[1]),
        float(bbox_raw[2]),
        float(bbox_raw[3]),
    )
    return OdlElement(
        type=raw.get("type", "paragraph"),
        text=raw.get("content", ""),
        bounding_box=bbox,
        hidden=bool(raw.get("hidden text", False)),
        page=int(raw.get("page number", 1)),
        heading_level=raw.get("heading level"),
        element_id=raw.get("id"),
    )


def structural_parse_from_odl_json(
    odl_json: dict[str, Any],
    content_hash: str,
    parser_version: str,
    markdown: str = "",
) -> StructuralParse:
    """
    Build a StructuralParse from a raw ODL JSON dict.

    Public so golden-file tests can call it directly without needing
    a live ODL process.
    """
    raw_kids: list[dict[str, Any]] = odl_json.get("kids", [])
    elements = tuple(_element_from_odl_dict(k) for k in raw_kids)
    page_count = int(odl_json.get("number of pages", 0))
    return StructuralParse(
        kids=elements,
        markdown=markdown,
        page_count=page_count,
        parser_version=parser_version,
        content_hash=content_hash,
    )
