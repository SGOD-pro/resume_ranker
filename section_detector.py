"""
section_detector.py — Phase 3: Standalone section detection
============================================================
SECTION_HEADERS dictionary + SectionDetector class.
Maps any raw section header to its canonical name.
"""

import re
from typing import Dict, List, Optional


SECTION_HEADERS: Dict[str, List[str]] = {
    "summary": ["summary", "profile", "about", "about me", "objective",
                "career objective", "professional summary", "personal statement", "overview"],
    "experience": ["experience", "employment", "employment history", "work experience",
                   "professional experience", "career history", "work history",
                   "job history", "relevant experience"],
    "education": ["education", "academic background", "academic history",
                  "qualifications", "educational background", "academics"],
    "projects": ["projects", "personal projects", "open source", "open-source",
                 "project experience", "key projects", "notable projects", "portfolio",
                 "side projects", "technical projects", "academic projects",
                 "projects / open-source", "projects / open source",
                 "projects/open-source", "projects/open source"],
    "skills": ["skills", "technical skills", "core competencies", "competencies",
               "expertise", "technologies", "tools", "tools & technologies",
               "technical expertise", "programming languages"],
    "certifications": ["certifications", "certificates", "courses", "licenses",
                       "credentials", "training", "professional development",
                       "achievements", "awards", "accomplishments", "honors",
                       "certification"],
    "languages": ["languages", "language skills", "spoken languages"],
}

_ALIAS_MAP: Dict[str, str] = {}
for _canonical, _aliases in SECTION_HEADERS.items():
    for _alias in _aliases:
        _ALIAS_MAP[_alias.upper()] = _canonical


def resolve_section_name(raw_name: str) -> Optional[str]:
    """Map raw section header to canonical name. None if unrecognized."""
    cleaned = raw_name.strip().upper()
    # Exact match
    if cleaned in _ALIAS_MAP:
        return _ALIAS_MAP[cleaned]
    # Try removing trailing special chars and re-matching
    cleaned2 = re.sub(r'[/\-|&]+\s*\S*$', '', cleaned).strip()
    if cleaned2 in _ALIAS_MAP:
        return _ALIAS_MAP[cleaned2]
    return None


class SectionDetector:
    """Split raw text into canonical resume sections."""

    def detect(self, text: str) -> Dict[str, str]:
        """
        Split plain text into sections by detecting header lines.
        A header line is: short (1-5 words), matches a known alias,
        and is NOT a long description sentence.
        """
        sections: Dict[str, List[str]] = {}
        current: Optional[str] = "__preamble__"
        current_lines: List[str] = []

        for line in text.split('\n'):
            stripped = line.strip()
            canonical = self._try_match_header(stripped)

            if canonical:
                if current_lines and current:
                    content = '\n'.join(current_lines).strip()
                    if content:
                        sections.setdefault(current, []).append(content)
                current = canonical
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines and current:
            content = '\n'.join(current_lines).strip()
            if content:
                sections.setdefault(current, []).append(content)

        return {k: '\n\n'.join(v) for k, v in sections.items() if k != '__preamble__'}

    def _try_match_header(self, line: str) -> Optional[str]:
        """Check if a line is a section header."""
        if not line:
            return None
        # Must be short (section headers are 1-5 words)
        words = line.split()
        if len(words) > 6:
            return None
        # Must not contain digits (like "2022 - 2025")
        if re.search(r'\d{4}', line):
            return None
        # Try resolving
        return resolve_section_name(line)

    def detect_from_tagged(self, main_sections: Dict[str, str]) -> Dict[str, str]:
        """Map layout_extractor raw section keys to canonical names."""
        result: Dict[str, List[str]] = {}
        for raw_key, content in main_sections.items():
            canonical = resolve_section_name(raw_key)
            if canonical and content.strip():
                result.setdefault(canonical, []).append(content.strip())
        return {k: '\n\n'.join(v) for k, v in result.items()}
