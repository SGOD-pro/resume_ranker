"""
education_parser.py — Phase 7: Education extraction
=====================================================
Detects degree keywords as anchors:
  Bachelor, Master, B.Tech, M.Tech, MBA, B.Sc, M.Sc, PhD, Diploma, etc.

Wraps section_parser.EducationParser for tagged-text path.
Output: [{ degree, institution, start, end, grade }]

v2 fixes:
  - Strip ||LOC: tags from input text before parsing
  - Strip bullet prefixes and action verbs from degree text
  - Clean garbled institution names
"""

import re
from typing import List, Dict, Any, Optional, Tuple

# ── ||LOC: tag stripping ─────────────────────────────────────────────────────
_LOC_TAG_RE = re.compile(r'\s*\|\|?LOC:[^\n]*', re.I)

# Action verb prefixes that are not part of degree names
_ACTION_VERB_PREFIX_RE = re.compile(
    r'^\s*[•·▪▸►✓✔\*\-]?\s*'
    r'(?:Received|Completed|Earned|Awarded|Obtained|Achieved|Pursued|Finished)'
    r'\s+(?:a\s+|an\s+|the\s+)?',
    re.I
)


def _strip_loc_tags(text: str) -> str:
    """Remove all ||LOC:... tags from text."""
    return _LOC_TAG_RE.sub('', text)


def _clean_degree_text(text: str) -> str:
    """Clean degree text by removing bullet prefixes and action verbs."""
    if not text:
        return text
    # Strip leading bullet characters
    cleaned = re.sub(r'^\s*[•·▪▸►✓✔\*\-]\s*', '', text)
    # Strip action verb prefixes
    cleaned = _ACTION_VERB_PREFIX_RE.sub('', cleaned)
    return cleaned.strip()

# ── Degree keyword regex ─────────────────────────────────────────────────────
# Word boundaries on BOTH sides to prevent partial matches like
# MA→MARCH, Master→Majors/Management
DEGREE_RE = re.compile(
    r'\b('
    r'Bachelors?\s+of\s+\w+|Masters?\s+of\s+\w+|Doctor\s+of\s+\w+'
    r'|Bachelors?\s+Degree|Masters?\s+Degree|Associates?\s+Degree'
    r'|Ph\.?D\.?|MBA'
    r'|B\.?Tech\.?|M\.?Tech\.?|B\.?E\.?|M\.?E\.?'
    r'|B\.S\.?c?\.?|M\.S\.?c?\.?'  # B.S., B.S, B.Sc., M.S., M.S, M.Sc.
    r'|B\.?Sc\.?|M\.?Sc\.?'         # BSc, B.Sc, MSc, M.Sc
    r'|B\.?SC\.?|M\.?SC\.?'         # BSC, MSC uppercase
    r'|B\.?A\.?|M\.?A\.?'
    r'|B\.?Com\.?|M\.?Com\.?'
    r'|Bachelor|Master|Associate|Diploma|Certificate'
    r'|Higher\s+Secondary'
    r'|(?:Class|Grade)\s+1[0-2]'
    r'|1[0-2]th'
    r')\b', re.I)

# Looser degree pattern for institution-first layouts (matches on next line)
# This catches "Science 12" or "Computer Science B.SC" on the line after an institution
_DEGREE_LOOSE_RE = re.compile(
    r'\b('
    r'B\.?S\.?C\.?|M\.?S\.?C\.?|B\.?A\.?|M\.?A\.?|B\.?Com|M\.?Com|'
    r'B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?|Ph\.?D|MBA|'
    r'Bachelor|Master|Diploma|Certificate|'
    r'(?:Science|Arts|Commerce)\s+(?:1[0-2])'
    r')\b', re.I)


DATE_RE = re.compile(
    r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})'
    r'\s*[–—\-]+\s*'
    r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|\d{4})',
    re.I)
YEAR_RE = re.compile(r'\b(20\d{2}|19\d{2})\b')
INST_RE = re.compile(
    r'\b(university|universty|unversity|universtiy|univeristy|'
    r'college|institute|institution|school|academy|'
    r'polytechnic|iit|nit|bits|iim|iiser|iiit)\b', re.I)
GRADE_RE = re.compile(
    r'(?:gpa|cgpa|grade|percentage|score|marks?)[:\s]*([\d.]+(?:\s*/\s*[\d.]+)?(?:\s*%)?)', re.I)

# Detect Majors/Minors lines that should be merged into a preceding entry
MAJOR_MINOR_RE = re.compile(r'^\s*(?:Majors?|Minors?|Concentration|Specialization)\s*:', re.I)

# Detect lines that are ONLY a date (e.g., "MARCH 2007") — not a degree
DATE_ONLY_RE = re.compile(
    r'^\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})\s*$', re.I)


class EducationParser:
    """Parse education entries from plain section text."""

    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        # Strip ||LOC: tags from input (defense-in-depth)
        text = _strip_loc_tags(text)

        # First pass: line-based structured parsing
        entries = self._parse_by_lines(text)
        if entries:
            return self._dedup(entries)

        # Fallback: anchor-based parsing using degree keyword matches
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

    def _parse_by_lines(self, text: str) -> List[Dict[str, Any]]:
        """
        Line-based structured parsing.
        Walk through lines, detect degree lines OR institution-first lines,
        gather associated institution, dates, grades.
        Handles two patterns:
          A) Degree line first: "Bachelor of Science in CS" then institution below
          B) Institution first: "TDB College" then "Computer Science B.SC 2022-2025"
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        entries: List[Dict[str, Any]] = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip pure date-only lines (e.g., "MARCH 2007")
            if DATE_ONLY_RE.match(line):
                i += 1
                continue

            # Check if this line is a Majors/Minors line → merge into last entry
            if MAJOR_MINOR_RE.match(line):
                if entries:
                    last = entries[-1]
                    if last.get('degree'):
                        last['degree'] = last['degree'] + ' | ' + line
                    else:
                        last['degree'] = line
                i += 1
                continue

            # ── Pattern A: Line contains a degree keyword ────────────────────
            if DEGREE_RE.search(line):
                degree, institution = self._split_degree_institution(line)

                # Check for inline dates on the same degree line
                start, end, grade = None, None, None
                dm = DATE_RE.search(line)
                if dm:
                    start = dm.group('start').strip()
                    end = dm.group('end').strip()

                # Look ahead for more info
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]

                    # Stop if we hit another degree line, Majors/Minors, or
                    # another institution line (start of next entry)
                    if DEGREE_RE.search(next_line) or MAJOR_MINOR_RE.match(next_line):
                        break
                    if INST_RE.search(next_line) and institution is not None:
                        break

                    dm = DATE_RE.search(next_line)
                    if dm and start is None:
                        start = dm.group('start').strip()
                        end = dm.group('end').strip()
                        j += 1
                        continue

                    if DATE_ONLY_RE.match(next_line) and end is None:
                        years = YEAR_RE.findall(next_line)
                        if years:
                            end = years[0]
                        j += 1
                        continue

                    gm = GRADE_RE.search(next_line)
                    if gm and grade is None:
                        grade = gm.group(1).strip()
                        j += 1
                        continue

                    if institution is None and INST_RE.search(next_line):
                        institution = DATE_RE.sub('', next_line).strip().rstrip(',').strip()
                        j += 1
                        continue

                    j += 1

                if degree or institution:
                    entries.append({
                        "degree": degree,
                        "institution": institution,
                        "start": start,
                        "end": end,
                        "grade": grade,
                    })
                i = j if j > i + 1 else i + 1
                continue

            # ── Pattern B: Institution-first line ────────────────────────────
            # Line has institution keyword but NO degree keyword.
            # Look ahead: next line should have a degree/class info.
            if INST_RE.search(line) and not DEGREE_RE.search(line):
                institution = DATE_RE.sub('', line).strip().rstrip(',').strip()
                degree, start, end, grade = None, None, None, None

                j = i + 1
                while j < len(lines):
                    next_line = lines[j]

                    # Check for degree on next line (using loose pattern too)
                    if degree is None and (DEGREE_RE.search(next_line) or
                                           _DEGREE_LOOSE_RE.search(next_line)):
                        degree = DATE_RE.sub('', next_line).strip()
                        # Also extract inline dates from degree line
                        dm = DATE_RE.search(next_line)
                        if dm and start is None:
                            start = dm.group('start').strip()
                            end = dm.group('end').strip()
                            degree = DATE_RE.sub('', degree).strip()
                        j += 1
                        continue

                    # Stop if we hit a new institution line (next entry)
                    if INST_RE.search(next_line) and degree is not None:
                        break
                    if INST_RE.search(next_line) and j > i + 2:
                        break

                    dm = DATE_RE.search(next_line)
                    if dm and start is None:
                        start = dm.group('start').strip()
                        end = dm.group('end').strip()
                        j += 1
                        continue

                    gm = GRADE_RE.search(next_line)
                    if gm and grade is None:
                        grade = gm.group(1).strip()
                        j += 1
                        continue

                    if DATE_ONLY_RE.match(next_line):
                        j += 1
                        continue

                    # Unknown line — skip but don't go too far
                    if j > i + 4:
                        break
                    j += 1

                if degree or institution:
                    entries.append({
                        "degree": degree,
                        "institution": institution,
                        "start": start,
                        "end": end,
                        "grade": grade,
                    })
                i = j if j > i + 1 else i + 1
                continue

            i += 1

        return entries

    def _split_degree_institution(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Split a line like 'TESOL Masters Degree, Cambridge University, Online'
        into degree and institution parts.
        If institution keywords are found, split at the comma before them.
        """
        # Remove dates, grades, and ||LOC: tags first
        clean = DATE_RE.sub('', line)
        clean = GRADE_RE.sub('', clean)
        clean = _strip_loc_tags(clean).strip().rstrip(',').strip()

        if not clean or len(clean) <= 3:
            return None, None

        # Clean action verb prefixes from degree text
        clean = _clean_degree_text(clean)

        # Try to find where the institution starts (by institution keyword)
        inst_match = INST_RE.search(clean)
        if inst_match:
            # Find the comma that separates degree from institution
            # Walk backwards from the institution match to find a comma
            before_inst = clean[:inst_match.start()]
            comma_pos = before_inst.rfind(',')
            if comma_pos > 0:
                degree = clean[:comma_pos].strip().rstrip(',').strip()
                institution = clean[comma_pos + 1:].strip().rstrip(',').strip()
                return degree or None, institution or None

        # No institution keyword found — the whole line is the degree
        return clean, None

    def _extract_degree(self, ctx: str) -> Optional[str]:
        for line in ctx.split('\n'):
            line_stripped = line.strip()
            # Skip date-only lines
            if DATE_ONLY_RE.match(line_stripped):
                continue
            # Skip Majors/Minors lines
            if MAJOR_MINOR_RE.match(line_stripped):
                continue
            if DEGREE_RE.search(line_stripped):
                degree, _ = self._split_degree_institution(line_stripped)
                return degree
        return None

    def _extract_institution(self, lines: List[str]) -> Optional[str]:
        for line in lines:
            if INST_RE.search(line):
                clean = DATE_RE.sub('', line)
                clean = GRADE_RE.sub('', clean).strip().rstrip(',').strip()
                if clean and len(clean.split()) <= 10:
                    # If the line also has a degree keyword, extract only the
                    # institution part
                    if DEGREE_RE.search(line):
                        _, inst = self._split_degree_institution(line)
                        if inst:
                            return inst
                        # If split didn't find institution, fall through
                        continue
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
