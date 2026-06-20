"""
section_detector.py — Phase 3: Standalone section detection
============================================================
Uses section_registry as the single source of truth for section names.
Maps any raw section header to its canonical name.
"""

import re
from typing import Dict, List, Optional

from src.registries.section_registry import SECTION_ALIASES, resolve as resolve_section_name


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
