"""
section_registry.py — Single source of truth for section names
================================================================
All section names, aliases, and canonical mappings live here.
No other module should define section aliases.

Usage:
    from section_registry import SECTION_ALIASES, CANONICAL_SECTIONS, resolve

    canonical = resolve("Employment History")   # → "experience"
    canonical = resolve("PRACTICE AREAS")       # → "experience"
    canonical = resolve("random heading")       # → None
"""

import re
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Canonical sections — the target schema contract
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_SECTIONS: List[str] = [
    "summary",
    "experience",
    "education",
    "projects",
    "skills",
    "certifications",
    "languages",
    "awards",
    "achievements",
    "publications",
    "references",
]


# ─────────────────────────────────────────────────────────────────────────────
# Unified alias map: UPPERCASE raw header → lowercase canonical key
# ─────────────────────────────────────────────────────────────────────────────
# Every alias that existed in section_parser.SECTION_ALIASES and
# section_detector.SECTION_HEADERS is merged here. Profession-specific
# aliases are added for Medical, Legal, Finance, Education, Sales, Research.
#
# NOTE: section_parser.py used "employment" and "profile" as canonical keys
# internally for ResumeAssembler. We map both to the schema-level canonical:
#   "employment" → "experience"
#   "profile"    → "summary"
#   "courses"    → "certifications"
# The assembler compatibility layer re-maps these back if needed.
# ─────────────────────────────────────────────────────────────────────────────

SECTION_ALIASES: Dict[str, str] = {
    # ── Summary / Profile ─────────────────────────────────────────────────
    "SUMMARY":                  "summary",
    "PROFILE":                  "summary",
    "ABOUT":                    "summary",
    "ABOUT ME":                 "summary",
    "OBJECTIVE":                "summary",
    "OVERVIEW":                 "summary",
    "PROFESSIONAL SUMMARY":     "summary",
    "CAREER OBJECTIVE":         "summary",
    "PERSONAL STATEMENT":       "summary",
    "EXECUTIVE SUMMARY":        "summary",
    "PROFESSIONAL PROFILE":     "summary",
    "CAREER SUMMARY":           "summary",

    # ── Experience / Employment ───────────────────────────────────────────
    "EXPERIENCE":               "experience",
    "EMPLOYMENT HISTORY":       "experience",
    "WORK EXPERIENCE":          "experience",
    "PROFESSIONAL EXPERIENCE":  "experience",
    "CAREER HISTORY":           "experience",
    "WORK HISTORY":             "experience",
    "JOB HISTORY":              "experience",
    "RELEVANT EXPERIENCE":      "experience",
    "EMPLOYMENT":               "experience",
    # Medical
    "CLINICAL EXPERIENCE":      "experience",
    "PATIENT CARE EXPERIENCE":  "experience",
    # Education profession
    "TEACHING EXPERIENCE":      "experience",
    # Legal
    "LEGAL EXPERIENCE":         "experience",
    "PRACTICE AREAS":           "experience",
    # Finance
    "DEAL EXPERIENCE":          "experience",
    # Sales
    "KEY ACCOUNTS":             "experience",
    # Consulting
    "CONSULTING EXPERIENCE":    "experience",
    # Military
    "MILITARY SERVICE":         "experience",
    "SERVICE HISTORY":          "experience",
    # Management
    "CASE MANAGEMENT":          "experience",

    # ── Education ─────────────────────────────────────────────────────────
    "EDUCATION":                "education",
    "ACADEMIC BACKGROUND":      "education",
    "QUALIFICATIONS":           "education",
    "ACADEMIC HISTORY":         "education",
    "EDUCATIONAL BACKGROUND":   "education",
    "ACADEMICS":                "education",
    "ACADEMIC QUALIFICATIONS":  "education",

    # ── Projects ──────────────────────────────────────────────────────────
    "PROJECTS":                 "projects",
    "PERSONAL PROJECTS":        "projects",
    "OPEN SOURCE":              "projects",
    "OPEN-SOURCE":              "projects",
    "PROJECT EXPERIENCE":       "projects",
    "KEY PROJECTS":             "projects",
    "NOTABLE PROJECTS":         "projects",
    "PORTFOLIO":                "projects",
    "SIDE PROJECTS":            "projects",
    "TECHNICAL PROJECTS":       "projects",
    "ACADEMIC PROJECTS":        "projects",
    "PROJECTS / OPEN-SOURCE":   "projects",
    "PROJECTS / OPEN SOURCE":   "projects",
    "PROJECTS/OPEN-SOURCE":     "projects",
    "PROJECTS/OPEN SOURCE":     "projects",
    # Profession-specific
    "CASES":                    "projects",
    "CASE STUDIES":             "projects",
    "ENGAGEMENTS":              "projects",
    "RESEARCH WORK":            "projects",
    "RESEARCH PROJECTS":        "projects",
    "INITIATIVES":              "projects",
    "CAMPAIGNS":                "projects",
    "CONSULTING ENGAGEMENTS":   "projects",
    "CLIENT PROJECTS":          "projects",

    # ── Skills ────────────────────────────────────────────────────────────
    "SKILLS":                   "skills",
    "TECHNICAL SKILLS":         "skills",
    "CORE COMPETENCIES":        "skills",
    "COMPETENCIES":             "skills",
    "EXPERTISE":                "skills",
    "TECHNOLOGIES":             "skills",
    "TOOLS":                    "skills",
    "TOOLS & TECHNOLOGIES":     "skills",
    "TECHNICAL EXPERTISE":      "skills",
    "PROGRAMMING LANGUAGES":    "skills",
    # Profession-specific
    "PROFESSIONAL SKILLS":      "skills",
    "AREAS OF EXPERTISE":       "skills",
    "SPECIALIZATIONS":          "skills",
    "TECHNICAL PROFICIENCIES":  "skills",
    "CLINICAL SKILLS":          "skills",
    "THERAPEUTIC MODALITIES":   "skills",
    "KEY STRENGTHS":            "skills",

    # ── Certifications ────────────────────────────────────────────────────
    "CERTIFICATIONS":           "certifications",
    "CERTIFICATES":             "certifications",
    "COURSES":                  "certifications",
    "TRAINING":                 "certifications",
    "LICENSES":                 "certifications",
    "CREDENTIALS":              "certifications",
    "PROFESSIONAL DEVELOPMENT": "certifications",
    "CERTIFICATION":            "certifications",
    # Profession-specific
    "PROFESSIONAL LICENSES":    "certifications",
    "BAR ADMISSIONS":           "certifications",
    "BOARD CERTIFICATIONS":     "certifications",
    "ACCREDITATIONS":           "certifications",
    "CONTINUING EDUCATION":     "certifications",

    # ── Languages ─────────────────────────────────────────────────────────
    "LANGUAGES":                "languages",
    "LANGUAGE SKILLS":          "languages",
    "SPOKEN LANGUAGES":         "languages",

    # ── Awards ────────────────────────────────────────────────────────────
    "AWARDS":                   "awards",
    "HONORS":                   "awards",
    "RECOGNITIONS":             "awards",
    "DISTINCTIONS":             "awards",

    # ── Achievements ──────────────────────────────────────────────────────
    "ACCOMPLISHMENTS":          "achievements",
    "ACHIEVEMENTS":             "achievements",
    "KEY ACHIEVEMENTS":         "achievements",
    "KEY ACCOMPLISHMENTS":      "achievements",

    # ── Publications ──────────────────────────────────────────────────────
    "PUBLICATIONS":             "publications",
    "RESEARCH PAPERS":          "publications",
    "JOURNAL ARTICLES":         "publications",
    "CONFERENCE PAPERS":        "publications",
    "PRESENTATIONS":            "publications",
    "AUTHORED WORKS":           "publications",

    # ── References ────────────────────────────────────────────────────────
    "REFERENCES":               "references",
}


# ─────────────────────────────────────────────────────────────────────────────
# Assembler compatibility layer
# ─────────────────────────────────────────────────────────────────────────────
# section_parser.py's ResumeAssembler used its own internal canonical names:
#   "employment", "profile", "courses", "accomplishments"
# This map translates our new canonical names back to assembler keys.
# Used only by ResumeAssembler._split_into_sections().

ASSEMBLER_KEY_MAP: Dict[str, str] = {
    "experience":      "employment",
    "summary":         "profile",
    "certifications":  "courses",
    "achievements":    "accomplishments",
    "awards":          "accomplishments",   # assembler lumps awards + achievements
}


def to_assembler_key(canonical: str) -> str:
    """Convert schema canonical key to assembler internal key."""
    return ASSEMBLER_KEY_MAP.get(canonical, canonical)


# ─────────────────────────────────────────────────────────────────────────────
# Reverse lookup: canonical → list of aliases (for SECTION_HEADERS compat)
# ─────────────────────────────────────────────────────────────────────────────

def get_aliases(canonical: str) -> List[str]:
    """Get all lowercase aliases for a canonical section."""
    return [alias.lower() for alias, canon in SECTION_ALIASES.items()
            if canon == canonical]


# ─────────────────────────────────────────────────────────────────────────────
# Resolution API
# ─────────────────────────────────────────────────────────────────────────────

def resolve(raw_name: str) -> Optional[str]:
    """
    Resolve any raw section header to its canonical name.

    Args:
        raw_name: Raw section header text (any casing)

    Returns:
        Canonical section name (lowercase) or None if unrecognized.

    Examples:
        resolve("Employment History")  → "experience"
        resolve("CLINICAL EXPERIENCE") → "experience"
        resolve("Cases")               → "projects"
        resolve("random text")         → None
    """
    if not raw_name:
        return None

    cleaned = raw_name.strip().upper()

    # Exact match
    if cleaned in SECTION_ALIASES:
        return SECTION_ALIASES[cleaned]

    # Try removing trailing special chars (e.g., "Skills / Tools" → "SKILLS")
    cleaned2 = re.sub(r'[/\-|&]+\s*\S*$', '', cleaned).strip()
    if cleaned2 in SECTION_ALIASES:
        return SECTION_ALIASES[cleaned2]

    return None
