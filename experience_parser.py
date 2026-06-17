"""
experience_parser.py — Phase 6: Date-anchored experience extraction
====================================================================
Uses date ranges as anchors (most reliable signal).
Supports: Role/Company/Date, Company/Role/Date, Role|Company/Date formats.
Wraps section_parser.EmploymentParser for tagged-text path.
"""

import re
from typing import List, Dict, Any, Optional, Tuple

DATE_RANGE_RE = re.compile(
    r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})'
    r'\s*[–—\-–]+\s*'
    r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now|\d{4})',
    re.I)
BULLET_RE = re.compile(r'^[•·▪▸►✓✔\*\-]\s+(.+)')
SEP_RE = re.compile(r'\s*[|/]\s*')


class ExperienceParser:
    """Parse work experience entries. Output: [{ role, company, start, end, description }]"""

    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        date_matches = list(DATE_RANGE_RE.finditer(text))
        if not date_matches:
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

            if role or company:
                entries.append({
                    "role": role, "company": company,
                    "start": dm.group('start').strip(),
                    "end": dm.group('end').strip(),
                    "description": description,
                    "achievements": achievements,
                })
        return entries

    def parse_from_tokens(self, tokens: list) -> List[Dict[str, Any]]:
        """Wrap section_parser.EmploymentParser with normalized keys."""
        from section_parser import EmploymentParser
        return [
            {"role": j.get("role"), "company": j.get("company"),
             "start": j.get("start_date"), "end": j.get("end_date"),
             "description": j.get("description"), "achievements": j.get("achievements", [])}
            for j in EmploymentParser().parse(tokens)
        ]

    def _extract_role_company(self, before: str, after: str) -> Tuple[Optional[str], Optional[str]]:
        lines = [l.strip() for l in before.split('\n') if l.strip()]
        if not lines:
            al = [l.strip() for l in after.split('\n') if l.strip()]
            return self._split_role_company(al[0]) if al else (None, None)
        last = lines[-1]
        if SEP_RE.search(last):
            parts = [p.strip() for p in SEP_RE.split(last, maxsplit=1)]
            if len(parts) == 2:
                return parts[0], parts[1]
        role = last.rstrip(',').strip()
        company = lines[-2].rstrip(',').strip() if len(lines) >= 2 else None
        return role, company

    def _split_role_company(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        if ',' in line:
            p = line.split(',', 1)
            return p[0].strip(), p[1].strip()
        m = re.match(r'^(.+?)\s+at\s+(.+)$', line, re.I)
        return (m.group(1).strip(), m.group(2).strip()) if m else (line, None)

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
        yr = re.compile(r'(?P<start>20\d{2}|19\d{2})\s*[-–—]+\s*(?P<end>20\d{2}|19\d{2}|Present|Current)', re.I)
        entries = []
        for dm in yr.finditer(text):
            before = text[max(0, dm.start()-200):dm.start()].strip()
            lines = [l.strip() for l in before.split('\n') if l.strip()]
            role = lines[-1] if lines else None
            company = lines[-2] if len(lines) >= 2 else None
            if role or company:
                entries.append({"role": role, "company": company,
                                "start": dm.group('start'), "end": dm.group('end'),
                                "description": None, "achievements": []})
        return entries
