"""
skills_parser.py — Phase 5: Dictionary-based skills extraction
===============================================================
Exact-match only. Never uses NER PERSON / ORG / LOCATION as skills.
Loads skills_dictionary.json, matches against resume text.
"""

import re, json, os
from typing import List, Set


_DICT_PATH = os.path.join(os.path.dirname(__file__), "skills_dictionary.json")

def _load_skills_dict() -> List[str]:
    try:
        with open(_DICT_PATH, "r", encoding="utf-8") as f:
            return [s.strip() for s in json.load(f) if isinstance(s, str) and s.strip()]
    except Exception:
        return []

_SKILLS_LIST: List[str]   = _load_skills_dict()
_SKILLS_SORTED            = sorted(_SKILLS_LIST, key=len, reverse=True)
_SKILLS_LOWER: Set[str]   = {s.lower() for s in _SKILLS_LIST}
_SKILLS_CANONICAL: dict   = {s.lower(): s for s in _SKILLS_LIST}


def _build_pattern(skill: str) -> re.Pattern:
    escaped = re.escape(skill)
    return re.compile(
        r'(?<![A-Za-z0-9\-_])' + escaped + r'(?![A-Za-z0-9\-_])',
        re.IGNORECASE
    )

_SKILL_PATTERNS = [(skill, _build_pattern(skill)) for skill in _SKILLS_SORTED]


class SkillsParser:
    """
    Parse skills from:
      1. skills_section text (comma / pipe / bullet)
      2. full_text (dictionary scan)
    Returns deduplicated list with canonical casing.
    """

    def parse(self, skills_section: str = "", full_text: str = "",
              also_scan_fulltext: bool = True) -> List[str]:
        found: Set[str] = set()

        # Step 1: raw section parsing
        if skills_section:
            raw_skills = self._parse_raw_section(skills_section)
            for raw in raw_skills:
                canonical = _SKILLS_CANONICAL.get(raw.lower().strip(), "")
                if canonical:
                    found.add(canonical)
                elif self._looks_like_skill(raw):
                    found.add(raw.strip())

        # Step 2: dictionary scan of section
        if skills_section:
            found.update(self._dict_scan(skills_section))

        # Step 3: full-text scan
        if also_scan_fulltext and full_text:
            found.update(self._dict_scan(full_text))

        return self._deduplicate(found)

    def _parse_raw_section(self, text: str) -> List[str]:
        raw: List[str] = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Skip section headers (ALL CAPS short lines)
            if line.isupper() and len(line.split()) <= 3:
                continue
            # Handle "Category: skill1, skill2, skill3" pattern
            # Strip the category prefix (e.g., "Programming Languages:", "Databases:")
            if ':' in line:
                parts = line.split(':', 1)
                # If left side is short (category) and right side has content, use right side
                if len(parts[0].split()) <= 4 and parts[1].strip():
                    line = parts[1].strip()
            # Now split by comma, pipe, or bullet
            if ',' in line:
                raw.extend(s.strip() for s in line.split(',') if s.strip())
            elif '|' in line:
                raw.extend(s.strip() for s in line.split('|') if s.strip())
            elif '•' in line or line.startswith('-'):
                raw.extend(
                    re.sub(r'^[-•·▪▸►✓✔\*]\s*', '', s).strip()
                    for s in re.split(r'[•\-]', line) if s.strip()
                )
            else:
                raw.append(line)
        return [r for r in raw if r and 1 < len(r) < 40]

    def _looks_like_skill(self, text: str) -> bool:
        text = text.strip()
        if not text or len(text) > 35 or text.isdigit():
            return False
        # Max 3 words for non-dictionary skills
        if len(text.split()) > 3:
            return False
        # Must not look like a sentence (no common verbs/articles)
        lower = text.lower()
        noise_words = {'the', 'and', 'for', 'with', 'from', 'that', 'this',
                       'are', 'was', 'were', 'has', 'have', 'had', 'will',
                       'can', 'could', 'would', 'should', 'may', 'might',
                       'not', 'but', 'also', 'just', 'only', 'into',
                       'about', 'their', 'which', 'when', 'where', 'what',
                       'how', 'all', 'each', 'every', 'both', 'few',
                       'more', 'most', 'other', 'some', 'such'}
        words = set(lower.split())
        if words & noise_words:
            return False
        return True

    def _dict_scan(self, text: str) -> Set[str]:
        found: Set[str] = set()
        for skill, pattern in _SKILL_PATTERNS:
            if pattern.search(text):
                found.add(_SKILLS_CANONICAL.get(skill.lower(), skill))
        return found

    def _deduplicate(self, skills: Set[str]) -> List[str]:
        seen_lower: Set[str] = set()
        result: List[str] = []
        in_dict = sorted([s for s in skills if s.lower() in _SKILLS_LOWER])
        not_in_dict = sorted([s for s in skills if s.lower() not in _SKILLS_LOWER])
        for s in in_dict + not_in_dict:
            lower = s.lower()
            if lower not in seen_lower:
                seen_lower.add(lower)
                result.append(s)
        return result
