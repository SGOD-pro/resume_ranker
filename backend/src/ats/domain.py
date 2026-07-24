from dataclasses import dataclass, field
from typing import Literal, Any
from datetime import datetime

@dataclass(frozen=True)
class AtsSignal:
    name: str            # e.g., "two_column_layout"
    score: float         # 0.0 or 1.0 for binary, continuous otherwise
    weight: float        # contribution to final ats_score
    detail: str | None   # e.g., "3 of 5 pages show multi-column clustering"

@dataclass(frozen=True)
class AtsIssue:
    signal_name: str
    severity: Literal["instant_fail", "severe", "moderate"]
    message: str         # human-readable
    bounding_boxes: list[dict[str, Any]] = field(default_factory=list)

# Alias AtsFlag for backward compatibility
AtsFlag = AtsIssue

@dataclass(frozen=True)
class FixSuggestion:
    signal_name: str
    action: str

@dataclass
class AtsResult:
    id: str
    document_id: str | None
    signals: dict[str, AtsSignal]
    ats_score: float
    flags: list[AtsIssue]
    fix_suggestions: list[FixSuggestion]
    computed_at: datetime
    bounding_boxes: list[dict[str, Any]] | None = None
