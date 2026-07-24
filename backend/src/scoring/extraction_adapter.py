"""
scoring/extraction_adapter.py — ExtractionResult → legacy candidate dict
=========================================================================
Bridge between Phase 2/3 ExtractionResult dataclass and the dict format
that the V1 scoring functions in src/ranking/ expect.

Zero math lives here. Pure field mapping only.
If ExtractionResult schema changes, update this file alone.
"""

from __future__ import annotations

from typing import Any

from src.extraction.domain_extraction import ExtractionResult


def extraction_result_to_candidate_dict(
    result: ExtractionResult,
    document_id: str,
) -> dict[str, Any]:
    """
    Map an ExtractionResult to the legacy candidate dict format consumed
    by CandidateScorer / similarity.py / bm25_scorer.py.

    Field mapping:
        result.name              → personal_info.name
        result.email             → personal_info.email
        result.phone             → personal_info.phone
        result.location          → personal_info.location
        result.skills            → skills (list[str])
        result.experience        → experience (list[dict])
        result.education         → education (list[dict])
        result.summary           → raw_text_sections.summary
    """
    personal_info: dict[str, Any] = {
        "name":     result.name.value if result.name else None,
        "email":    result.email.value if result.email else None,
        "phone":    result.phone.value if result.phone else None,
        "location": result.location.value if result.location else None,
        "linkedin": result.linkedin.value if result.linkedin else None,
        "github":   result.github.value if result.github else None,
    }

    skills: list[str] = []
    if result.skills and result.skills.value:
        raw = result.skills.value
        if isinstance(raw, list):
            skills = [str(s) for s in raw]

    experience: list[dict[str, Any]] = []
    if result.experience and result.experience.value:
        raw_exp = result.experience.value
        if isinstance(raw_exp, list):
            experience = [_ensure_exp_dict(e) for e in raw_exp]

    education: list[dict[str, Any]] = []
    if result.education and result.education.value:
        raw_edu = result.education.value
        if isinstance(raw_edu, list):
            education = [_ensure_edu_dict(e) for e in raw_edu]

    summary = result.summary.value if result.summary else ""

    return {
        "_document_id": document_id,
        "personal_info": personal_info,
        "skills": skills,
        "experience": experience,
        "education": education,
        "certifications": [],           # Phase 2 does not extract certs yet
        "projects": [],                 # Phase 2 does not extract projects yet
        "raw_text_sections": {
            "summary": summary or "",
            "full_text": "",            # Not available in Phase 2 ExtractionResult
        },
        "extraction_quality": _compute_quality(result),
    }


def _compute_quality(result: ExtractionResult) -> float:
    """
    Estimate extraction quality as the fraction of contact fields resolved
    with high confidence by the deterministic engine.

    0.0 = nothing resolved, 1.0 = all core contact fields resolved.
    """
    fields = [result.name, result.email, result.phone]
    resolved = sum(
        1 for f in fields
        if f is not None and f.value is not None and f.confidence >= 0.7  # noqa: PLR2004
    )
    return round(resolved / len(fields), 2)


def _ensure_exp_dict(e: Any) -> dict[str, Any]:
    """
    Normalise an experience entry to the dict format experience_score expects.
    Handles both dict (from Nova JSON) and dataclass inputs.
    """
    if isinstance(e, dict):
        return e
    # Pydantic model or dataclass — convert via __dict__ / model_dump
    try:
        out: dict[str, Any] = {k: v for k, v in e}
        return out
    except TypeError:
        return {k: v for k, v in vars(e).items()}


def _ensure_edu_dict(e: Any) -> dict[str, Any]:
    """Normalise an education entry to dict format."""
    if isinstance(e, dict):
        return e
    try:
        out: dict[str, Any] = {k: v for k, v in e}
        return out
    except TypeError:
        return {k: v for k, v in vars(e).items()}
