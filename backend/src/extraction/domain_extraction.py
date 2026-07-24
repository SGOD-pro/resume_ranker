"""
extraction/domain_extraction.py — Extracted field types for Phase 2+
=====================================================================
All output types from DeterministicExtractionService (and the Nova fallback
in Phase 3) live here.

Key contract:
  - ExtractedField is immutable (frozen dataclass).
  - confidence is a float in [0.0, 1.0].
  - provenance MUST be one of the _VALID_PROVENANCES literals.
  - UnresolvedChunk is what gets queued to SQS→Nova.
  - ExtractionResult carries all extracted fields + unresolved chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Provenance literals — exhaustive; add new ones here only
# ---------------------------------------------------------------------------
Provenance = Literal[
    "deterministic",  # regex / dictionary / ODL structure — 100% rule-based
    "nova_micro",     # Amazon Nova Micro filled this field
    "nova_lite",      # Amazon Nova Lite filled this field (escalation path)
]


# ---------------------------------------------------------------------------
# ExtractedField
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractedField:
    """
    A single extracted value with confidence + provenance.

    Rules:
      - deterministic fields always overwrite Nova fields — Nova NEVER
        overwrites a field that the deterministic engine resolved.
      - confidence == 1.0 means the field was extracted from a well-structured
        ODL element (e.g., heading-level-1 name, regex email match).
      - confidence < 0.5 triggers a Nova re-check in Phase 3.
    """

    value: Any                          # str | list[str] | list[dict] | None
    confidence: float                   # 0.0–1.0
    provenance: Provenance = "deterministic"
    source_elements: tuple[int, ...] = ()  # ODL element IDs contributing to this field


# ---------------------------------------------------------------------------
# UnresolvedChunk
# ---------------------------------------------------------------------------

@dataclass
class UnresolvedChunk:
    """
    A text chunk that the deterministic engine could not confidently parse.
    Gets enqueued to SQS UnresolvedChunkQueue → Nova fallback Lambda.

    field_name: the canonical field this chunk should fill (e.g. "name", "experience")
    text: the raw text from the relevant ODL section
    document_id: correlates back to the DocumentItem
    """

    field_name: str
    text: str
    document_id: str
    section: str = ""       # canonical section where chunk lives
    confidence_so_far: float = 0.0   # deterministic confidence (may be partial)


# ---------------------------------------------------------------------------
# LayoutMetadata
# ---------------------------------------------------------------------------

@dataclass
class LayoutMetadata:
    """
    Pre-computed geometric primitives from the ODL parser.
    Decouples evaluation (JD Scoring + ATS) from raw PDF rendering/JVM.
    """
    has_overlaps: bool = False
    column_boundaries: list[float] = field(default_factory=list)
    font_stats: dict[str, float] = field(default_factory=dict)
    reading_order_gaps: list[float] = field(default_factory=list)
    bounding_boxes: list[dict[str, Any]] = field(default_factory=list)



# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """
    Full output of DeterministicExtractionService for one resume.

    Fields mirror the downstream scoring schema:
      name, email, phone, linkedin, github, location — contact block
      experience — list of experience entry dicts
      education  — list of education entry dicts
      skills     — list of canonical skill strings
      summary    — plain-text summary block

    Unresolved chunks are queued to Nova in Phase 3.
    """

    document_id: str
    content_hash: str

    # ── Contact fields ────────────────────────────────────────────────────
    name: ExtractedField | None = None
    email: ExtractedField | None = None
    phone: ExtractedField | None = None
    linkedin: ExtractedField | None = None
    github: ExtractedField | None = None
    location: ExtractedField | None = None

    # ── Structured sections ───────────────────────────────────────────────
    experience: ExtractedField | None = None      # value = list[dict]
    education: ExtractedField | None = None       # value = list[dict]
    skills: ExtractedField | None = None          # value = list[str]
    summary: ExtractedField | None = None         # value = str

    # ── Metadata ─────────────────────────────────────────────────────────
    unresolved: list[UnresolvedChunk] = field(default_factory=list)
    parser_version: str = "v2"
    layout_metadata: LayoutMetadata | None = None

    # ── Computed metrics ─────────────────────────────────────────────────
    @property
    def deterministic_ratio(self) -> float:
        """
        Fraction of populated fields extracted deterministically.
        Phase 2 verification gate: must be >= 0.85.
        """
        all_fields = [
            self.name, self.email, self.phone, self.linkedin,
            self.github, self.location, self.experience,
            self.education, self.skills, self.summary,
        ]
        populated = [f for f in all_fields if f is not None]
        if not populated:
            return 0.0
        deterministic = [
            f for f in populated if f.provenance == "deterministic"
        ]
        return len(deterministic) / len(populated)

    def to_fields_dict(self) -> dict[str, Any]:
        """
        Serialize to a flat dict for storage/scoring.
        Returns raw values (not ExtractedField wrappers).
        """
        return {
            "name":       self.name.value if self.name else None,
            "email":      self.email.value if self.email else None,
            "phone":      self.phone.value if self.phone else None,
            "linkedin":   self.linkedin.value if self.linkedin else None,
            "github":     self.github.value if self.github else None,
            "location":   self.location.value if self.location else None,
            "experience": self.experience.value if self.experience else [],
            "education":  self.education.value if self.education else [],
            "skills":     self.skills.value if self.skills else [],
            "summary":    self.summary.value if self.summary else None,
        }
