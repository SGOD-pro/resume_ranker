"""
education_parser.py — Phase 7: Education extraction
=====================================================
Detects degree keywords as anchors:
  Bachelor, Master, B.Tech, M.Tech, MBA, B.Sc, M.Sc, PhD, Diploma, etc.

Wraps section_parser.EducationParser for tagged-text path.
Output: [{ degree, institution, start, end, grade }]
"""

import re
from typing import List, Dict, Any, Optional, Tuple

DEGREE_RE = re.compile(
    r'\b('
    r'Bachelors?\s+of\s+\w+|Masters?\s+of\s+\w+|Doctor\s+of\s+\w+|'
    r'Ph\.?D\.?|MBA|B\.?Tech\.?|M\.?Tech\.?|B\.?E\.?|M\.?E\.?|'
    r'B\.?Sc\.?|M\.?Sc\.?|B\.?A\.?|M\.?A\.?|B\.?Com\.?|M\.?Com\.?|'
    r'Bachelor|Master|Associate|Diploma|Certificate'
    r')', re.I)
DATE_RE = re.compile(
    r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})'
    r'\s*[–—\-]+\s*'
    r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|\d{4})',
    re.I)
YEAR_RE = re.compile(r'\b(20\d{2}|19\d{2})\b')
INST_RE = re.compile(
    r'\b(university|college|institute|institution|school|academy|'
    r'polytechnic|iit|nit|bits|iim|iiser|iiit)\b', re.I)
GRADE_RE = re.compile(
    r'(?:gpa|cgpa|grade|percentage|score|marks?)[:\s]*([\d.]+(?:\s*/\s*[\d.]+)?(?:\s*%)?)', re.I)


class EducationParser:
    """Parse education entries from plain section text."""

    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        matches = list(DEGREE_RE.finditer(text))
        if not matches:
            return []

        entries = []
        for i, dm in enumerate(matches):
            ctx_start = max(0, dm.start() - 50)
            ctx_end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), dm.end() + 400)
            context = text[ctx_start:ctx_end]
            lines = [l.strip() for l in context.split('\n') if l.strip()]

            degree = self._extract_degree(context)
            institution = self._extract_institution(lines)
            start, end = self._extract_dates(context)
            grade = self._extract_grade(context)

            if degree or institution:
                entries.append({"degree": degree, "institution": institution,
                                "start": start, "end": end, "grade": grade})
        return self._dedup(entries)

    def parse_from_tokens(self, tokens: list) -> List[Dict[str, Any]]:
        """Wrap section_parser.EducationParser with normalized keys."""
        from section_parser import EducationParser as _EP
        result = []
        for edu in _EP().parse(tokens):
            parts = filter(None, [edu.get("degree_type"),
                                  ("in " + edu["field_of_study"]) if edu.get("field_of_study") else None])
            result.append({
                "degree": " ".join(parts) or None,
                "institution": edu.get("institution"),
                "start": edu.get("start_date"), "end": edu.get("end_date"),
                "grade": None})
        return result

    def _extract_degree(self, ctx: str) -> Optional[str]:
        for line in ctx.split('\n'):
            if DEGREE_RE.search(line):
                clean = DATE_RE.sub('', line)
                clean = GRADE_RE.sub('', clean).strip().rstrip(',').strip()
                if len(clean) > 3:
                    return clean
        return None

    def _extract_institution(self, lines: List[str]) -> Optional[str]:
        for line in lines:
            if INST_RE.search(line):
                clean = DATE_RE.sub('', line)
                clean = GRADE_RE.sub('', clean).strip().rstrip(',').strip()
                if clean and len(clean.split()) <= 10:
                    return clean
        return None

    def _extract_dates(self, ctx: str) -> Tuple[Optional[str], Optional[str]]:
        m = DATE_RE.search(ctx)
        if m:
            return m.group('start').strip(), m.group('end').strip()
        years = YEAR_RE.findall(ctx)
        if len(years) >= 2:
            return years[0], years[1]
        if years:
            return None, years[0]
        return None, None

    def _extract_grade(self, ctx: str) -> Optional[str]:
        m = GRADE_RE.search(ctx)
        return m.group(1).strip() if m else None

    def _dedup(self, entries: List[Dict]) -> List[Dict]:
        seen = set()
        result = []
        for e in entries:
            key = ((e.get('degree') or '')[:30].lower(), (e.get('institution') or '')[:30].lower())
            if key not in seen:
                seen.add(key)
                result.append(e)
        return result
