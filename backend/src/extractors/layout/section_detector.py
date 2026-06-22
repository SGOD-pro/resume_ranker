"""
section_detector.py — Phase 3: Standalone section detection
============================================================
Uses section_registry as the single source of truth for section names.
Maps any raw section header to its canonical name.

v2 fixes:
  - Strip Unicode PUA characters (icon fonts) before header matching
  - Strip common icon prefixes (►, ▸, ■, ●) before matching
  - Strip bracket tag wrappers before matching
"""

import re
from typing import Dict, List, Optional

from src.registries.section_registry import SECTION_ALIASES, resolve as resolve_section_name

# Unicode PUA range (private use area — used for icon fonts in PDF templates)
_PUA_RE = re.compile(r'[\ue000-\uf8ff]')
# Common decorative prefixes before section headers
_ICON_PREFIX_RE = re.compile(r'^[►▸▹▻■□●○◆◇★☆✦✧▪▫◈◉⬢⬡⬤♦♣♠♥✚✜✪✫✬✭✮✯✰⊕⊗⊙⊚\s]+')
# Bracket tag wrappers from layout_extractor
_TAG_RE = re.compile(r'\[/?[A-Z_]+\]')


def _clean_for_header_match(line: str) -> str:
    """Clean a line for section header matching.
    
    Strips Unicode PUA icons, decorative prefixes, bracket tags,
    numbered prefixes (e.g., '02 EDUCATION'), and normalizes whitespace.
    """
    s = _PUA_RE.sub('', line)           # Strip icon font chars
    s = _TAG_RE.sub('', s)              # Strip [TAG] wrappers
    s = _ICON_PREFIX_RE.sub('', s)      # Strip decorative prefixes
    s = s.strip()
    # Strip leading numbered prefixes like "02 " or "06" (attached to word)
    # Handles: "02 EMPLOYMENT HISTORY" → "EMPLOYMENT HISTORY"
    # Handles: "06LANGUAGES" → "LANGUAGES"  
    s = re.sub(r'^\d{1,2}\s*', '', s).strip()
    # Remove trailing colon (common in "Skills:" style headers)
    s = s.rstrip(':').strip()
    return s


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

        # Clean the line for matching (PUA, icons, tags)
        cleaned = _clean_for_header_match(line)
        if not cleaned:
            return None

        # Must be short (section headers are 1-6 words)
        words = cleaned.split()
        if len(words) > 6:
            return None
        # Must not contain year-like digits (like "2022 - 2025")
        if re.search(r'\d{4}', cleaned):
            return None
        # Try resolving the cleaned text
        result = resolve_section_name(cleaned)
        if result:
            return result

        # Also try the original stripped line (in case cleaning removed too much)
        if cleaned != line.strip():
            orig_words = line.strip().split()
            if len(orig_words) <= 6 and not re.search(r'\d{4}', line.strip()):
                return resolve_section_name(line.strip())

        return None

    def detect_from_tagged(self, main_sections: Dict[str, str]) -> Dict[str, str]:
        """Map layout_extractor raw section keys to canonical names."""
        result: Dict[str, List[str]] = {}
        for raw_key, content in main_sections.items():
            canonical = resolve_section_name(raw_key)
            if canonical and content.strip():
                result.setdefault(canonical, []).append(content.strip())
        return {k: '\n\n'.join(v) for k, v in result.items()}
