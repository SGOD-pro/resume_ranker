"""
experience_parser.py — Phase 6: Date-anchored experience extraction
====================================================================
Uses date ranges as anchors (most reliable signal).
Supports: Role/Company/Date, Company/Role/Date, Role|Company/Date formats.
Wraps section_parser.EmploymentParser for tagged-text path.

v2 fixes:
  - Smart role/company disambiguation using title-like vs company-like scoring
  - Bullet-text-as-role guard (rejects descriptions misidentified as roles)
  - ||LOC: tag stripping from extracted fields
  - Improved year-only date range parsing
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# ── Date component patterns ──────────────────────────────────────────────
# Month names: full or abbreviated, with optional period
_MONTH = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'

# Start date patterns (order matters — most specific first)
_START_PATTERNS = '|'.join([
    _MONTH + r'\.?\s+\d{4}',           # January 2020, Jan. 2020, Jan 2020
    _MONTH + r'\.\d{4}',               # Jan.2020 (no space)
    _MONTH + r"'\d{2}",                 # Jan'20
    _MONTH + r'-\d{2,4}',              # Jan-20, Jan-2020
    r'\d{1,2}\s+' + _MONTH + r'\s+\d{4}',  # 1 June 2020, 15 January 2019
    r'\d{1,2}/\d{1,2}/\d{4}',          # DD/MM/YYYY or MM/DD/YYYY
    r'\d{1,2}-\d{1,2}-\d{4}',          # DD-MM-YYYY or MM-DD-YYYY
    r'\d{1,2}/\d{4}',                  # MM/YYYY
    r'\d{1,2}-\d{4}',                  # MM-YYYY
    r'\d{1,2}\.\d{4}',                 # MM.YYYY
    r'\d{4}/\d{1,2}',                  # YYYY/MM
    r'\d{4}',                          # YYYY
])

# End date patterns (same as start + Present/Current/Now/Till Date)
_END_PATTERNS = '|'.join([
    _MONTH + r'\.?\s+\d{4}',
    _MONTH + r'\.\d{4}',
    _MONTH + r"'\d{2}",
    _MONTH + r'-\d{2,4}',
    r'\d{1,2}\s+' + _MONTH + r'\s+\d{4}',
    r'\d{1,2}/\d{1,2}/\d{4}',
    r'\d{1,2}-\d{1,2}-\d{4}',
    r'\d{1,2}/\d{4}',
    r'\d{1,2}-\d{4}',
    r'\d{1,2}\.\d{4}',
    r'\d{4}/\d{1,2}',
    r'Present|Current|Now|Till\s+Date|Till\s+Now|To\s+Date|Ongoing',
    r'\d{4}',
])

# Separator between start–end: dashes, em-dashes, "to", "till"
_DATE_SEP = r'\s*(?:[–—\-–]+|to|till)\s*'

DATE_RANGE_RE = re.compile(
    r'(?P<start>' + _START_PATTERNS + r')'
    + _DATE_SEP +
    r'(?P<end>' + _END_PATTERNS + r')',
    re.I)

# "Since YYYY" / "From YYYY" → treated as YYYY – Present
SINCE_RE = re.compile(
    r'(?:Since|From)\s+(?P<start>\d{4})',
    re.I)

BULLET_RE = re.compile(r'^[•·▪▸►✓✔\*\-]\s+(.+)')
SEP_RE = re.compile(r'\s*[|/]\s*')

# ── Role / Company disambiguation patterns ────────────────────────────────

# Words strongly indicating a job title / role
_ROLE_KEYWORDS = re.compile(
    r'\b(?:Developer|Engineer|Manager|Designer|Analyst|Director|Consultant|'
    r'Teacher|Guard|Trainer|Coordinator|Officer|Specialist|Lead|Intern|'
    r'Assistant|Senior|Junior|Associate|Supervisor|Administrator|Architect|'
    r'Technician|Operator|Clerk|Representative|Accountant|Auditor|Advisor|'
    r'Producer|Editor|Writer|Chef|Nurse|Therapist|Counselor|Instructor|'
    r'Recruiter|Planner|Strategist|Scientist|Researcher|Pharmacist|Lawyer|'
    r'Attorney|Paralegal|Secretary|Receptionist|Dispatcher|Mechanic|'
    r'Electrician|Plumber|Carpenter|Driver|Pilot|Captain|Head|Chief|'
    r'Vice\s+President|VP|CTO|CEO|CFO|COO|CIO|CMO|President|Founder|'
    r'Co[\-\s]?Founder|Partner|Principal|Fellow|Freelance|Part[\-\s]?Time|'
    r'Full[\-\s]?Time|Contract|Temporary|Volunteer)\b',
    re.I
)

# Words strongly indicating a company / organization name
_COMPANY_KEYWORDS = re.compile(
    r'\b(?:Inc\.?|LLC|Ltd\.?|Corp(?:oration)?\.?|Co\.?|Group|Technologies|'
    r'Solutions|School|University|College|Institute|Hospital|Medical|'
    r'Consulting|Agency|Services|Studio|Foundation|Association|'
    r'International|Global|National|Federal|Government|Department|'
    r'Enterprises|Partners|Labs?|Dynamics|Industries|Systems|Networks|'
    r'Media|Entertainment|Publishing|Broadcasting|Fitness|Clinic|'
    r'Bank|Financial|Insurance|Holdings|Capital|Ventures|Fund)\b',
    re.I
)

# ── Cleaning helpers ──────────────────────────────────────────────────────

_LOC_TAG_RE = re.compile(r'\s*\|\|?LOC:[^\n]*', re.I)


def _clean_loc_tags(s: Optional[str]) -> Optional[str]:
    """Strip ||LOC:... tags from text."""
    if not s:
        return s
    return _LOC_TAG_RE.sub('', s).strip() or None


def _is_bullet_or_description(text: str) -> bool:
    """Check if text looks like a bullet point or description, not a role/company."""
    if not text:
        return False
    t = text.strip()
    # Starts with lowercase letter (roles/companies are title-case)
    if t[0].islower():
        return True
    # Contains percentage figures (description metrics)
    if re.search(r'\d+\s*%', t):
        return True
    # Too long for a role or company name
    if len(t) > 100:
        return True
    # Starts with bullet character
    if t[0] in '•·▪▸►✓✔*-' and len(t) > 2:
        return True
    # Looks like a full sentence (contains multiple verbs/objects)
    word_count = len(t.split())
    if word_count > 12:
        return True
    return False


def _role_score(text: str) -> float:
    """Score how much a text looks like a job title (0.0 to 1.0)."""
    if not text:
        return 0.0
    score = 0.0
    # Role keywords boost
    matches = _ROLE_KEYWORDS.findall(text)
    score += len(matches) * 0.4
    # Short text (roles are typically 1-6 words)
    words = text.split()
    if 1 <= len(words) <= 6:
        score += 0.3
    elif len(words) > 8:
        score -= 0.3
    # Title case boost
    if text[0].isupper():
        score += 0.1
    # Penalty for company keywords in a "role" candidate
    if _COMPANY_KEYWORDS.search(text):
        score -= 0.3
    return max(0.0, score)


def _company_score(text: str) -> float:
    """Score how much a text looks like a company name (0.0 to 1.0)."""
    if not text:
        return 0.0
    score = 0.0
    # Company keywords boost
    matches = _COMPANY_KEYWORDS.findall(text)
    score += len(matches) * 0.4
    # Moderate length (companies are typically 1-8 words)
    words = text.split()
    if 1 <= len(words) <= 8:
        score += 0.2
    elif len(words) > 10:
        score -= 0.2
    # Contains comma + location pattern (e.g., "FNB, Nong Phai")
    if re.search(r',\s*[A-Z]', text):
        score += 0.2
    # Title case
    if text[0].isupper():
        score += 0.1
    # Penalty for role keywords in a "company" candidate
    if _ROLE_KEYWORDS.search(text):
        score -= 0.2
    return max(0.0, score)


class ExperienceParser:
    """Parse work experience entries. Output: [{ role, company, start, end, description }]"""

    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        date_matches = list(DATE_RANGE_RE.finditer(text))
        if not date_matches:
            # Try "Since YYYY" / "From YYYY" patterns
            since_entries = self._parse_since(text)
            if since_entries:
                return since_entries
            return self._parse_year_only(text)

        entries = []
        for i, dm in enumerate(date_matches):
            ctx_start = max(0, dm.start() - 250)
            if i > 0:
                ctx_start = max(ctx_start, date_matches[i - 1].end())
            before = text[ctx_start:dm.start()].strip()
            after_end = date_matches[i + 1].start() if i + 1 < len(date_matches) else min(len(text), dm.end() + 800)
            after = text[dm.end():after_end].strip()

            role, company = self._extract_role_company(before, after)
            description, achievements = self._extract_description(after)

            # Clean ||LOC: tags from fields
            role = _clean_loc_tags(role)
            company = _clean_loc_tags(company)

            if role or company:
                entries.append({
                    "role": role, "company": company,
                    "start": dm.group('start').strip(),
                    "end": dm.group('end').strip(),
                    "description": description,
                    "achievements": achievements,
                })
        return entries

    def _extract_role_company(self, before: str, after: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract role and company from context around date range.
        
        Uses smart heuristics to determine which line is the role vs company:
        - Scores each candidate line for role-like vs company-like patterns
        - Rejects lines that look like bullet points or descriptions
        - Handles both Role/Company and Company/Role orderings
        """
        lines = [l.strip() for l in before.split('\n') if l.strip()]
        
        # Filter out lines that are clearly descriptions/bullets
        clean_lines = [l for l in lines if not _is_bullet_or_description(l)]
        
        if not clean_lines:
            # Try from after-text
            al = [l.strip() for l in after.split('\n') if l.strip()]
            if al:
                return self._split_role_company(al[0])
            return (None, None)

        last = clean_lines[-1]
        
        # Check for separator pattern: "Role | Company" or "Role / Company"
        if SEP_RE.search(last):
            parts = [p.strip() for p in SEP_RE.split(last, maxsplit=1)]
            if len(parts) == 2:
                # Determine which part is role vs company
                return self._disambiguate_role_company(parts[0], parts[1])

        if len(clean_lines) >= 2:
            candidate_role = last.rstrip(',').strip()
            candidate_company = clean_lines[-2].rstrip(',').strip()
            return self._disambiguate_role_company(candidate_role, candidate_company)
        
        # Only one line — try splitting by comma
        return self._split_role_company(last)

    def _disambiguate_role_company(self, line_a: str, line_b: str) -> Tuple[Optional[str], Optional[str]]:
        """Given two candidate lines, determine which is the role and which is the company.
        
        Uses scoring heuristics based on keyword patterns. The line with higher role score
        becomes the role, and the other becomes the company. If scores are tied or both
        equally ambiguous, falls back to the original ordering (line_a = role, line_b = company).
        """
        a_role = _role_score(line_a)
        b_role = _role_score(line_b)
        a_company = _company_score(line_a)
        b_company = _company_score(line_b)

        # Score each assignment direction
        # Assignment 1: line_a = role, line_b = company (original)
        score_original = a_role + b_company
        # Assignment 2: line_b = role, line_a = company (swapped)
        score_swapped = b_role + a_company

        if score_swapped > score_original + 0.2:  # Need meaningful margin to swap
            return line_b.rstrip(',').strip(), line_a.rstrip(',').strip()
        return line_a.rstrip(',').strip(), line_b.rstrip(',').strip()

    def _split_role_company(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        if ',' in line:
            p = line.split(',', 1)
            a, b = p[0].strip(), p[1].strip()
            return self._disambiguate_role_company(a, b)
        m = re.match(r'^(.+?)\s+at\s+(.+)$', line, re.I)
        if m:
            return self._disambiguate_role_company(
                m.group(1).strip(), m.group(2).strip()
            )
        return (line, None)

    def _extract_description(self, after: str) -> Tuple[Optional[str], List[str]]:
        bullets, desc = [], []
        for line in after.split('\n'):
            line = line.strip()
            if not line:
                continue
            m = BULLET_RE.match(line)
            if m:
                bullets.append(m.group(1).strip())
            elif DATE_RANGE_RE.search(line):
                break
            elif not bullets:
                desc.append(line)
        return ' '.join(desc).strip() or None, bullets

    def _parse_year_only(self, text: str) -> List[Dict[str, Any]]:
        yr = re.compile(
            r'(?P<start>20\d{2}|19\d{2})\s*[-–—]+\s*(?P<end>20\d{2}|19\d{2}|Present|Current)',
            re.I
        )
        entries = []
        for dm in yr.finditer(text):
            before = text[max(0, dm.start()-200):dm.start()].strip()
            lines = [l.strip() for l in before.split('\n') if l.strip()]
            # Filter out description-like lines
            clean_lines = [l for l in lines if not _is_bullet_or_description(l)]

            if len(clean_lines) >= 2:
                role, company = self._disambiguate_role_company(
                    clean_lines[-1], clean_lines[-2]
                )
            elif clean_lines:
                role, company = self._split_role_company(clean_lines[-1])
            else:
                continue

            # Clean ||LOC: tags
            role = _clean_loc_tags(role)
            company = _clean_loc_tags(company)

            if role or company:
                entries.append({
                    "role": role, "company": company,
                    "start": dm.group('start'), "end": dm.group('end'),
                    "description": None, "achievements": [],
                })
        return entries

    def _parse_since(self, text: str) -> List[Dict[str, Any]]:
        """Parse 'Since YYYY' / 'From YYYY' patterns as YYYY – Present."""
        entries = []
        for dm in SINCE_RE.finditer(text):
            before = text[max(0, dm.start()-200):dm.start()].strip()
            lines = [l.strip() for l in before.split('\n') if l.strip()]
            clean_lines = [l for l in lines if not _is_bullet_or_description(l)]

            if len(clean_lines) >= 2:
                role, company = self._disambiguate_role_company(
                    clean_lines[-1], clean_lines[-2]
                )
            elif clean_lines:
                role, company = self._split_role_company(clean_lines[-1])
            else:
                continue

            role = _clean_loc_tags(role)
            company = _clean_loc_tags(company)

            if role or company:
                entries.append({
                    "role": role, "company": company,
                    "start": dm.group('start'), "end": "Present",
                    "description": None, "achievements": [],
                })
        return entries
