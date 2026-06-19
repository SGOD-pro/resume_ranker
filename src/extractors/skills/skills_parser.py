"""
skills_parser.py — Phase 5: Dictionary-based skills extraction
===============================================================
Exact-match first, then fuzzy-match for garbled PDF text.
Never uses NER PERSON / ORG / LOCATION as skills.
Loads skills_dictionary.json, matches against resume text.
"""

import re, json, os
from difflib import SequenceMatcher
from typing import List, Set, Optional, Dict


from src.config.settings import SKILLS_DICTIONARY

_DICT_PATH = str(SKILLS_DICTIONARY)

def _load_skills_dict() -> List[str]:
    try:
        with open(_DICT_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return [
                s.strip() for s in raw
                if isinstance(s, str) and s.strip()
                and not s.strip().startswith('__comment')
            ]
    except Exception:
        return []

_SKILLS_LIST: List[str]   = _load_skills_dict()
_SKILLS_SORTED            = sorted(_SKILLS_LIST, key=len, reverse=True)
_SKILLS_LOWER: Set[str]   = {s.lower() for s in _SKILLS_LIST}
_SKILLS_CANONICAL: dict   = {s.lower(): s for s in _SKILLS_LIST}

# ── Fuzzy matching index: group skills by word count for faster matching ──────
_SKILLS_BY_WORDCOUNT: Dict[int, List[str]] = {}
for _s in _SKILLS_LIST:
    _wc = len(_s.split())
    _SKILLS_BY_WORDCOUNT.setdefault(_wc, []).append(_s)

# ── Non-skill patterns to reject ─────────────────────────────────────────────
_LOCATION_RE = re.compile(
    r'^(?:[A-Z][a-z]+(?:ville|burg|burgh|town|port|field|land|dale|wood|ridge|'
    r'mont|view|lake|creek|ford|shire|ston|stead|bury|ham|ton|worth|bridge|'
    r'chester|cester|mouth|pool|gate|more|sea))$', re.I)

_US_CITY_SET = {
    'burnsville', 'minneapolis', 'new york', 'los angeles', 'chicago',
    'houston', 'phoenix', 'philadelphia', 'san antonio', 'san diego',
    'dallas', 'san jose', 'austin', 'jacksonville', 'columbus',
    'charlotte', 'indianapolis', 'san francisco', 'seattle', 'denver',
    'nashville', 'oklahoma city', 'portland', 'las vegas', 'memphis',
    'louisville', 'baltimore', 'milwaukee', 'tucson', 'fresno',
    'sacramento', 'mesa', 'atlanta', 'omaha', 'raleigh', 'miami',
    'oakland', 'tulsa', 'tampa', 'arlington', 'new orleans',
    'cleveland', 'honolulu', 'anaheim', 'aurora', 'santa ana',
    'st. louis', 'riverside', 'pittsburgh', 'lexington', 'stockton',
    'anchorage', 'cincinnati', 'saint paul', 'greensboro', 'toledo',
    'newark', 'plano', 'lincoln', 'orlando', 'irvine',
}


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
    Includes fuzzy matching to handle garbled PDF font encodings.
    """

    # Fuzzy match threshold — how similar a garbled skill must be to a
    # dictionary entry to be accepted. 0.65 is lenient enough to catch
    # common PDF font substitutions (2-3 chars wrong in a 10-char word).
    FUZZY_THRESHOLD = 0.65

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
                else:
                    # Try fuzzy match before accepting as-is
                    fuzzy = self._fuzzy_match(raw.strip())
                    if fuzzy:
                        found.add(fuzzy)
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
        """Check if a raw skill string from the skills section looks valid."""
        text = text.strip()
        if not text or len(text) > 50 or text.isdigit():
            return False
        # Max 5 words for non-dictionary skills (skills sections list real skills)
        if len(text.split()) > 5:
            return False
        # Filter out location/city names
        if text.lower() in _US_CITY_SET:
            return False
        if _LOCATION_RE.match(text):
            return False
        # Reject garbled strings with consecutive special chars or too many
        # non-alphanumeric chars (PDF font encoding artifacts like "zhi'''ids")
        special_count = sum(1 for c in text if not c.isalnum() and c not in ' -/&+#.')
        if special_count > 2:
            return False
        if re.search(r"['\"\`]{2,}", text):
            return False
        # Must not look like a sentence (no common verbs/articles/pronouns)
        lower = text.lower()
        noise_words = {'the', 'for', 'with', 'from', 'that', 'this',
                       'are', 'was', 'were', 'has', 'have', 'had', 'will',
                       'can', 'could', 'would', 'should', 'may', 'might',
                       'not', 'but', 'also', 'just', 'only', 'into',
                       'about', 'their', 'which', 'when', 'where', 'what',
                       'how', 'each', 'every', 'both', 'few',
                       'more', 'most', 'other', 'some', 'such',
                       'you', 'your', 'our', 'we', 'they', 'them',
                       'i', 'my', 'me', 'he', 'she', 'it', 'its',
                       'very', 'much', 'many', 'been', 'being'}
        words = set(lower.split())
        if words & noise_words:
            return False
        return True

    def _fuzzy_match(self, text: str) -> Optional[str]:
        """
        Try to match a garbled skill string against the skills dictionary
        using character-level similarity. Returns the canonical skill name
        if a close match is found, else None.

        Garbled PDF text typically has consistent character substitutions
        (e.g., p→g, K→P, y→p, G→v) which preserves word length and most
        characters, making SequenceMatcher effective.
        """
        if not text or len(text) < 3:
            return None

        text_lower = text.lower()

        # Quick check: skip if it's a location or noise
        if text_lower in _US_CITY_SET:
            return None

        text_wc = len(text.split())
        best_ratio = 0.0
        best_skill = None

        # Search skills with same word count ±1 for efficiency
        for wc in range(max(1, text_wc - 1), text_wc + 2):
            candidates = _SKILLS_BY_WORDCOUNT.get(wc, [])
            for skill in candidates:
                # Quick length filter: garbled text preserves length
                # Reject if lengths differ by more than 3 chars
                if abs(len(text) - len(skill)) > 3:
                    continue

                ratio = SequenceMatcher(
                    None, text_lower, skill.lower()
                ).ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_skill = skill

        # Adaptive threshold: short strings need higher similarity to avoid
        # false positives (e.g., "Design" → "UI Design" at 0.80)
        threshold = self.FUZZY_THRESHOLD
        if len(text) < 10:
            threshold = 0.85  # stricter for short strings

        if best_ratio >= threshold and best_skill:
            return _SKILLS_CANONICAL.get(best_skill.lower(), best_skill)

        return None

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
