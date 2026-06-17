"""
contact_parser.py — Phase 4: Regex-only contact extraction
===========================================================
Zero NER dependency. Uses layout tags + heuristic name detection.

Name logic:
  1. [NAME] tag from layout_extractor (bold large font — most reliable)
  2. Heuristic: first 10 lines, 2-4 words, no digits, no @, no URL
  3. ALL CAPS line in first 5 lines (common resume template)

All other fields: pure regex.
"""

import re
from typing import Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE    = re.compile(r'\b[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}\b')
_LINKEDIN_RE = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w\-_%]+)', re.I)
_GITHUB_RE   = re.compile(r'(?:https?://)?(?:www\.)?github\.com/([\w\-_%]+)', re.I)
_URL_RE      = re.compile(r'https?://\S+|www\.\S+', re.I)
_SECTION_KW  = {
    'summary', 'profile', 'objective', 'experience', 'education', 'skills',
    'projects', 'certifications', 'languages', 'references', 'achievements',
    'employment', 'contact', 'about', 'address', 'phone', 'email', 'linkedin',
    'github', 'resume', 'cv', 'curriculum', 'vitae', 'portfolio',
    'details', 'links', 'hobbies',
}
# Country / location names that look like person names (2 words, Title Case)
_NOT_NAMES = {
    'united states', 'united kingdom', 'new york', 'los angeles',
    'san francisco', 'san antonio', 'new delhi', 'hong kong',
    'south africa', 'new zealand', 'sri lanka', 'saudi arabia',
    'costa rica', 'puerto rico', 'el salvador', 'san jose',
    'place of', 'driving license', 'place birth', 'amazon associate',
    'place of birth', 'date of birth', 'date birth',
    'project manager', 'software engineer', 'data analyst',
    'web developer', 'full stack', 'front end', 'back end',
    'senior developer', 'junior developer', 'lead developer',
    'fashion designer', 'graphic designer', 'interior designer',
    'build this', 'resume templates', 'it project', 'analytical and',
    'digital marketer', 'network engineer', 'data engineer',
    'video production', 'ux designer', 'ui designer',
    'it project manager', 'senior project manager', 'junior project manager',
    'associate project manager', 'technical project manager',
    'product manager', 'program manager', 'account manager',
    'marketing manager', 'operations manager', 'general manager',
    'business analyst', 'systems analyst', 'security guard',
    'warehouse associate', 'amazon warehouse', 'laboratory inventory',
}
# Common lowercase particles in names (allowed without uppercase)
_NAME_PARTICLES = {'de', 'van', 'von', 'al', 'el', 'la', 'le', 'du', 'da', 'di',
                   'bin', 'binti', 'ibn', 'ben', 'mac', 'mc'}


def _is_name_line(line: str) -> bool:
    """Return True if line looks like a person name."""
    s = line.strip()
    if not s:
        return False
    words = s.split()
    if not (2 <= len(words) <= 4):
        return False
    for w in words:
        clean = re.sub(r"[.\-']", '', w)
        if not clean.isalpha():
            return False
    if re.search(r'\d', s):
        return False
    if '@' in s:
        return False
    if _URL_RE.search(s):
        return False
    if {w.lower() for w in words} & _SECTION_KW:
        return False
    # Require ALL words start uppercase (or are name particles)
    for w in words:
        if not w[0].isupper() and w.lower() not in _NAME_PARTICLES:
            return False
    # Reject known non-name phrases
    if s.lower() in _NOT_NAMES:
        return False
    return True


class ContactParser:
    """
    Extract contact fields from resume text.
    Accepts full_width_text (tagged header), raw_text, sidebar_text.
    """

    def parse(self, full_width_text: str = "", raw_text: str = "",
              sidebar_text: str = "") -> Dict[str, Any]:
        combined = "\n".join(filter(None, [full_width_text, sidebar_text, raw_text]))
        return {
            "name":     self._extract_name(full_width_text, raw_text, sidebar_text),
            "email":    self._extract_email(combined),
            "phone":    self._extract_phone(combined),
            "linkedin": self._extract_linkedin(combined),
            "github":   self._extract_github(combined),
            "location": self._extract_location(combined),
        }

    def _extract_name(self, full_width_text: str, raw_text: str,
                       sidebar_text: str = "") -> Optional[str]:
        # Strategy 1: [NAME] tag from layout_extractor (most reliable)
        for text_src in [full_width_text, sidebar_text, raw_text]:
            m = re.search(r'\[NAME\](.*?)\[/NAME\]', text_src, re.DOTALL)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate.split()) >= 1:
                    # Strip title suffix: "MICHELLE LOPEZ, Fashion Designer" → "MICHELLE LOPEZ"
                    if ',' in candidate:
                        candidate = candidate.split(',')[0].strip()
                    return candidate

        # Strategy 2: heuristic — first line of sidebar (common in two-column)
        for text_src in [sidebar_text, raw_text]:
            if not text_src:
                continue
            lines = [l.strip() for l in text_src.split('\n') if l.strip()]
            for line in lines[:5]:
                clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
                if _is_name_line(clean):
                    return clean

        # Strategy 3: scan first 10 lines of raw_text (fallback)
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        for line in lines[:10]:
            clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
            if _is_name_line(clean):
                return clean

        # Strategy 4: ALL CAPS line in first 5 lines
        for line in lines[:5]:
            clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
            words = clean.split()
            if 2 <= len(words) <= 4 and clean.isupper() and not re.search(r'\d', clean):
                return clean.title()

        return None

    def _extract_email(self, text: str) -> Optional[str]:
        m = _EMAIL_RE.search(text)
        return m.group(0).lower() if m else None

    def _extract_phone(self, text: str) -> Optional[str]:
        patterns = [
            r'\+\d{1,3}[\s\-.]?\(?\d{3,5}\)?[\s\-.]?\d{3,5}[\s\-.]?\d{3,5}',
            r'\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}',
            r'\b\d{10}\b',
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                result = m.group(0).strip()
                if len(re.sub(r'\D', '', result)) >= 7:
                    return result
        return None

    def _extract_linkedin(self, text: str) -> Optional[str]:
        m = _LINKEDIN_RE.search(text)
        return f"linkedin.com/in/{m.group(1)}" if m else None

    def _extract_github(self, text: str) -> Optional[str]:
        m = _GITHUB_RE.search(text)
        if m:
            username = m.group(1)
            if username.lower() not in {'blob', 'tree', 'commit', 'pull', 'issues', 'wiki'}:
                return f"github.com/{username}"
        return None

    def _extract_location(self, text: str) -> Optional[str]:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        city_state_re = re.compile(
            r'\b([A-Z][a-zA-Z\s]{2,25}),\s*([A-Z]{2}|\b[A-Z][a-zA-Z]{3,20})\b'
        )
        for line in lines[:20]:
            if _EMAIL_RE.search(line) or _LINKEDIN_RE.search(line):
                continue
            m = city_state_re.search(line)
            if m:
                return m.group(0).strip()
        return None
