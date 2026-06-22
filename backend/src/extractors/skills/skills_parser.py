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
        # ── Step 1: Split space-separated bundles ─────────────────────────
        # Skills like "Vue Redux TypeScript" → individual "Vue", "Redux", "TypeScript"
        # A multi-word entry is a "bundle" if:
        #   - It has 3+ words, AND
        #   - At least 2 individual words are known dictionary skills
        #   - The whole phrase is NOT itself a known multi-word skill (like "Machine Learning")
        expanded: Set[str] = set()
        for s in skills:
            words = s.split()
            whole_is_known = s.lower() in _SKILLS_LOWER
            if len(words) >= 3 and not whole_is_known:
                known_count = sum(1 for w in words if w.lower() in _SKILLS_LOWER)
                # Heuristic: all words are Title Case or PascalCase single tokens
                # (typical of sidebar skill lists: "Vue Redux TypeScript")
                all_title_like = all(
                    w[0].isupper() and len(w) >= 2 and w.isalpha()
                    for w in words if w.strip()
                )
                is_bundle = (
                    known_count >= 2
                    or (known_count >= 1 and all_title_like and len(words) >= 3)
                )
                if is_bundle:
                    # Split: add individual words that are known skills
                    for w in words:
                        canonical = _SKILLS_CANONICAL.get(w.lower())
                        if canonical:
                            expanded.add(canonical)
                        elif self._looks_like_skill(w) and len(w) >= 2:
                            expanded.add(w.strip())
                    continue  # Don't add the bundle itself
            # Also split slash-separated items: "Git/Github" → "Git", "Github"
            if '/' in s and not whole_is_known:
                parts = [p.strip() for p in s.split('/') if p.strip()]
                if len(parts) >= 2:
                    # Further split each part by spaces
                    all_tokens = []
                    for p in parts:
                        sub_words = p.split()
                        if len(sub_words) >= 2:
                            all_tokens.extend(sub_words)
                        else:
                            all_tokens.append(p)
                    known_count = sum(1 for t in all_tokens if t.lower() in _SKILLS_LOWER)
                    if known_count >= 1:
                        for t in all_tokens:
                            canonical = _SKILLS_CANONICAL.get(t.lower())
                            if canonical:
                                expanded.add(canonical)
                            elif self._looks_like_skill(t) and len(t) >= 2:
                                expanded.add(t)
                        continue
            # Also split ampersand-separated items: "Teamwork & Collaboration"
            if '&' in s and not whole_is_known:
                parts = [p.strip() for p in re.split(r'\s*&\s*', s) if p.strip()]
                if len(parts) >= 2:
                    known_parts = sum(1 for p in parts if p.lower() in _SKILLS_LOWER)
                    if known_parts >= 1:
                        for p in parts:
                            canonical = _SKILLS_CANONICAL.get(p.lower())
                            if canonical:
                                expanded.add(canonical)
                            elif self._looks_like_skill(p) and len(p) >= 2:
                                expanded.add(p)
                        continue
            expanded.add(s)

        # ── Step 2: Case-insensitive dedup ────────────────────────────────
        seen_lower: Set[str] = set()
        deduped: List[str] = []
        in_dict = sorted([s for s in expanded if s.lower() in _SKILLS_LOWER])
        not_in_dict = sorted([s for s in expanded if s.lower() not in _SKILLS_LOWER])
        for s in in_dict + not_in_dict:
            lower = s.lower()
            if lower not in seen_lower:
                seen_lower.add(lower)
                deduped.append(s)

        # ── Step 3: Containment dedup ─────────────────────────────────────
        # Remove bundles: if skill A has 3+ words and at least 2 of its
        # content words appear as individual skills elsewhere, remove A.
        # Also applies to dictionary multi-word skills where ALL content
        # words are present individually (e.g., "Teamwork & Collaboration"
        # when both "Teamwork" and "Collaboration" are separate skills).
        lower_set = {d.lower() for d in deduped}
        _STOP_WORDS = {'&', 'and', 'or', 'of', 'in', 'for', 'the', 'a', 'an', 'with', 'to'}
        to_remove: Set[int] = set()
        for i, a in enumerate(deduped):
            a_lower = a.lower()
            a_words = a_lower.split()
            if len(a_words) < 3:
                continue
            # Get content words (skip punctuation and stop words)
            content_words = [w for w in a_words if w not in _STOP_WORDS and len(w) > 1]
            if len(content_words) < 2:
                continue
            # Count how many content words appear as separate skills
            individual_count = sum(
                1 for w in content_words
                if w in lower_set and w != a_lower
            )
            if individual_count >= 2:
                to_remove.add(i)

        return [s for i, s in enumerate(deduped) if i not in to_remove]

