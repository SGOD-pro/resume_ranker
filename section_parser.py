"""
Section Parser — Token-Based State Machine
==========================================
Consumes the tagged text produced by layout_extractor and builds
clean structured dicts. No raw tags ever appear in output.

Tag format from layout_extractor:
  [JOB_TITLE]Role, Company  ||LOC:City[/JOB_TITLE]
  [EDU_LINE]Degree in Field, Institution  ||LOC:City[/EDU_LINE]
  [DATE]Jan 2021 — Present[/DATE]
  [BULLET]• bullet text (may be truncated)[/BULLET]
  [SECTION NAME]          ← section separator (no closing tag)
  plain text              ← body / continuation lines

State machine per section:
  Employment  → JOB_TITLE → DATE → (BODY desc) → BULLETS → next JOB_TITLE
  Education   → EDU_LINE|JOB_TITLE(degree) → optional JOB_TITLE(inst cont.) → DATE
  Courses     → JOB_TITLE → DATE
  Accomplishments → BULLET + continuation BODY
  Sidebar     → merge continuation lines (lowercase start = continuation)
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Regex helpers
# ─────────────────────────────────────────────────────────────────────────────

DATE_RE = re.compile(
    r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})'
    r'\s*[–—\-]+\s*'
    r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now)',
    re.IGNORECASE
)

DEGREE_RE = re.compile(
    r'\b(Bachelors?|Masters?|Ph\.?D|MBA|M\.?S\.?|B\.?S\.?|B\.?A\.?|M\.?A\.?'
    r'|Associates?|Diploma|Certificate|Doctor)\b',
    re.IGNORECASE
)

# Match any open-close tag pair: [TAG_NAME]content[/TAG_NAME]
OPEN_CLOSE_TAG = re.compile(r'^\[([A-Z_]+)\](.+?)\[/\1\]$', re.DOTALL)

# Match section-separator tag: [SECTION NAME] (no slash, all caps + spaces)
SECTION_TAG = re.compile(r'^\[([A-Z][A-Z\s]+)\]$')


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer — converts tagged lines into typed tokens
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Token:
    kind: str        # SECTION | JOB_TITLE | EDU_LINE | DATE | BULLET | BODY
    raw: str         # cleaned text (no tags)
    location: Optional[str] = None   # from ||LOC:
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None


def tokenize(tagged_text: str) -> List[Token]:
    """
    Convert layout_extractor tagged text → list of typed Token objects.
    Every token has its tags stripped.
    """
    tokens: List[Token] = []

    for raw_line in tagged_text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue

        # ── Section separator: [SECTION NAME] ────────────────────────────
        m_sec = SECTION_TAG.match(line)
        if m_sec:
            tokens.append(Token(kind='SECTION', raw=m_sec.group(1).strip()))
            continue

        # ── Open/close tag pair: [TAG]content[/TAG] ──────────────────────
        m_tag = OPEN_CLOSE_TAG.match(line)
        if m_tag:
            tag_name = m_tag.group(1)
            content = m_tag.group(2).strip()

            # Extract ||LOC: from content
            loc = None
            if '||LOC:' in content:
                parts = content.split('||LOC:', 1)
                content = parts[0].strip().rstrip(',').strip()
                loc = parts[1].strip()

            if tag_name == 'JOB_TITLE':
                role, company = _split_role_company(content)
                tokens.append(Token(
                    kind='JOB_TITLE', raw=content,
                    role=role, company=company, location=loc
                ))

            elif tag_name == 'EDU_LINE':
                tokens.append(Token(
                    kind='EDU_LINE', raw=content, location=loc
                ))

            elif tag_name == 'DATE':
                dm = DATE_RE.search(content)
                if dm:
                    tokens.append(Token(
                        kind='DATE', raw=content,
                        date_start=dm.group('start'),
                        date_end=dm.group('end'),
                    ))
                else:
                    tokens.append(Token(kind='BODY', raw=content))

            elif tag_name in ('BULLET',):
                # Strip leading bullet character
                clean = re.sub(r'^[•·▪▸►✓✔\*\-]\s*', '', content).strip()
                tokens.append(Token(kind='BULLET', raw=clean))

            elif tag_name in ('NAME', 'TITLE'):
                pass  # handled by pipeline directly from full_width_text

            else:
                tokens.append(Token(kind='BODY', raw=content))

        else:
            # ── Plain text (body / continuation) ─────────────────────────
            tokens.append(Token(kind='BODY', raw=line))

    return tokens


def _split_role_company(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    'Nutritional Consultant (Part-Time) , WIC  Port Washington'
    → ('Nutritional Consultant (Part-Time)', 'WIC')

    'DaVita Delmas' (no comma, no role sep)
    → ('DaVita Delmas', None)
    """
    parts = re.split(r'\s*,\s*', text, maxsplit=1)
    if len(parts) == 2:
        role = parts[0].strip()
        # Company: take up to first 2-space gap (rest is location artefact)
        company = re.split(r'\s{2,}', parts[1])[0].strip()
        return role, company
    return text.strip(), None


# ─────────────────────────────────────────────────────────────────────────────
# Individual section parsers — all work on Token lists
# ─────────────────────────────────────────────────────────────────────────────

class EmploymentParser:
    """
    State machine: JOB_TITLE → DATE → (BODY desc) → BULLETs → next JOB_TITLE
    Bullets merge continuation BODY lines.
    """

    def parse(self, tokens: List[Token]) -> List[Dict[str, Any]]:
        jobs: List[Dict] = []
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            if tok.kind != 'JOB_TITLE':
                i += 1
                continue

            job: Dict[str, Any] = {
                'role': tok.role,
                'company': tok.company,
                'location': tok.location,
                'start_date': None,
                'end_date': None,
                'description': None,
                'achievements': [],
            }
            i += 1

            # Immediately expect a DATE token
            if i < n and tokens[i].kind == 'DATE':
                job['start_date'] = tokens[i].date_start
                job['end_date'] = tokens[i].date_end
                i += 1

            # Collect description + bullets until next JOB_TITLE/SECTION
            desc_lines: List[str] = []
            raw_bullets: List[str] = []   # each entry = bullet text (may grow with continuations)
            in_bullet = False

            while i < n and tokens[i].kind not in ('JOB_TITLE', 'SECTION'):
                t = tokens[i]

                if t.kind == 'BULLET':
                    in_bullet = True
                    raw_bullets.append(t.raw)

                elif t.kind == 'BODY':
                    if in_bullet and raw_bullets:
                        # Continuation of previous bullet
                        raw_bullets[-1] = raw_bullets[-1].rstrip() + ' ' + t.raw.lstrip()
                    else:
                        # Description paragraph
                        desc_lines.append(t.raw)
                        in_bullet = False

                elif t.kind == 'DATE':
                    # Shouldn't happen mid-job, but handle gracefully
                    pass

                i += 1

            job['description'] = ' '.join(desc_lines).strip() or None
            job['achievements'] = [b.strip() for b in raw_bullets if b.strip()]

            if job['role'] or job['company']:
                jobs.append(job)

        return jobs


class EducationParser:
    """
    Handles three tag patterns for education entries:
      Pattern A: [EDU_LINE] → optional [JOB_TITLE](inst continuation) → [DATE]
      Pattern B: [JOB_TITLE](has degree keyword) → optional [JOB_TITLE](short) → [DATE]

    Institution extraction:
      From EDU_LINE: text after last comma (before ||LOC stripped by tokenizer)
        minus the location string → institution part 1
      From following JOB_TITLE (1-3 words, no degree, immediately after): append → full institution
    """

    def parse(self, tokens: List[Token]) -> List[Dict[str, Any]]:
        edu_list: List[Dict] = []
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            is_edu_token = (
                tok.kind == 'EDU_LINE'
                or (tok.kind == 'JOB_TITLE' and DEGREE_RE.search(tok.raw or ''))
            )

            if not is_edu_token:
                i += 1
                continue

            # Parse the degree line
            degree_type, field_of_study, inst_part1 = self._parse_degree_line(tok.raw)
            location = tok.location

            i += 1

            # Check for institution continuation: JOB_TITLE immediately following
            # with short text, no degree keyword, no date
            inst_part2 = None
            if (i < n
                    and tokens[i].kind == 'JOB_TITLE'
                    and not DEGREE_RE.search(tokens[i].raw or '')
                    and len((tokens[i].role or '').split()) <= 4):
                # This is "University" or "State University" — continuation of institution
                inst_part2 = (tokens[i].role or tokens[i].raw or '').strip()
                i += 1

            # Build full institution name
            institution = self._build_institution(inst_part1, inst_part2, location)

            # Expect DATE
            start_date, end_date = None, None
            if i < n and tokens[i].kind == 'DATE':
                start_date = tokens[i].date_start
                end_date = tokens[i].date_end
                i += 1

            edu_list.append({
                'degree_type': degree_type,
                'field_of_study': field_of_study,
                'institution': institution,
                'location': location,
                'start_date': start_date,
                'end_date': end_date,
            })

        return edu_list

    def _parse_degree_line(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Input: 'Master of Science in Dietary Education, Golden Valley'
        Output: ('Master of Science', 'Dietary Education', 'Golden Valley')

        Input: 'Associates Degree in Nutrition, St. Louis University Louisville'
        Output: ('Associates Degree', 'Nutrition', 'St. Louis University Louisville')
        """
        if not text:
            return None, None, None

        # Degree type: everything up to and including the degree keyword
        dm = DEGREE_RE.search(text)
        if not dm:
            return None, None, text.split(',')[-1].strip() if ',' in text else None

        # Degree type = "Master of Science" or "Bachelor of Science" etc.
        # Find the word after the degree keyword
        prefix = text[:dm.end()].strip()
        after_degree = text[dm.end():].strip()

        # "of Science" or "in Food Sciences" may follow → get the qualifier
        qual_m = re.match(r'^(?:of\s+\w+)', after_degree)
        if qual_m:
            degree_type = f"{prefix} {qual_m.group(0)}".strip()
            after_degree = after_degree[qual_m.end():].strip()
        else:
            degree_type = prefix

        # Field of study: "in X" or "of X" or "Degree in X"
        field_m = re.match(r'^(?:Degree\s+)?(?:in\s+|of\s+)?([^,]+?)(?:,|$)', after_degree, re.IGNORECASE)
        field = field_m.group(1).strip() if field_m else None
        # Remove leading "in"/"of"/"Degree in" if field starts with it
        field = re.sub(r"^(?:Degree\s+)?(?:in|of)\s+", "", field or "", flags=re.IGNORECASE).strip() or None

        # Institution: text after last comma
        if ',' in text:
            inst_raw = text.rsplit(',', 1)[-1].strip()
        else:
            inst_raw = None

        return degree_type, field, inst_raw

    def _build_institution(
        self,
        part1: Optional[str],
        part2: Optional[str],
        location: Optional[str],
    ) -> Optional[str]:
        """
        Combine inst_part1 + inst_part2, then remove location from the result.
        'Golden Valley' + 'University' → 'Golden Valley University'
        Then remove city 'Golden Valley' if it duplicates → keep 'Golden Valley University'
        """
        if not part1 and not part2:
            return None

        combined = ' '.join(filter(None, [part1, part2])).strip()

        # Remove location string from the institution if it's a trailing duplicate
        if location:
            loc_words = location.strip()
            # If institution ends with the location words, remove them
            # e.g. "St. Louis University Louisville" → remove "Louisville" → "St. Louis University"
            # But NOT "Golden Valley University" → DON'T remove "Golden Valley" (it's part of the name)
            if combined.endswith(loc_words) and not combined == loc_words:
                trimmed = combined[:-len(loc_words)].strip().rstrip(',').strip()
                # Only remove if remaining part looks like a university name
                if len(trimmed) > 3:
                    combined = trimmed

        return combined.strip() or None


class CoursesParser:
    """JOB_TITLE → DATE pattern."""

    def parse(self, tokens: List[Token]) -> List[Dict]:
        """
        Collect all JOB_TITLE + BODY tokens until DATE = one course entry.
        Handles multi-line course names like:
          [JOB_TITLE]Certified Head Nutrition Consultant , Food Sciences[/JOB_TITLE]
          [JOB_TITLE]Council[/JOB_TITLE]
          [DATE]Jul 2021 — Jul 2021[/DATE]
        """
        courses: List[Dict] = []
        i = 0
        n = len(tokens)

        while i < n:
            tok = tokens[i]

            if tok.kind not in ('JOB_TITLE', 'BODY'):
                i += 1
                continue

            # Accumulate name parts until DATE or SECTION
            name_parts: List[str] = []
            loc = None

            while i < n and tokens[i].kind in ('JOB_TITLE', 'BODY'):
                t = tokens[i]
                if t.kind == 'JOB_TITLE':
                    parts = [t.role, t.company]
                    chunk = ' '.join(p for p in parts if p).strip() or t.raw
                    name_parts.append(chunk)
                    if t.location:
                        loc = t.location
                else:
                    name_parts.append(t.raw.strip())
                i += 1

            if not name_parts:
                continue

            # Now expect DATE
            start_date = end_date = None
            if i < n and tokens[i].kind == 'DATE':
                start_date = tokens[i].date_start
                end_date   = tokens[i].date_end
                i += 1

            # Join name parts — remove trailing comma before joining
            name = ' '.join(p.rstrip(',') for p in name_parts if p).strip()

            courses.append({
                'name':       name,
                'issuer':     loc,
                'start_date': start_date,
                'end_date':   end_date,
            })

        return courses


class AccomplishmentsParser:
    """BULLET + continuation BODY → merge. Each bullet = one accomplishment."""

    def parse(self, tokens: List[Token]) -> List[str]:
        results: List[str] = []
        current: Optional[str] = None

        for tok in tokens:
            if tok.kind == 'BULLET':
                if current:
                    results.append(current.strip())
                current = tok.raw
            elif tok.kind == 'BODY' and current is not None:
                # Continuation of previous bullet
                current = current.rstrip() + ' ' + tok.raw.lstrip()
            # SECTION / DATE / etc. → ignore in accomplishments

        if current:
            results.append(current.strip())

        return results


class SidebarExtractor:
    """
    Parses sidebar sections dict from layout_extractor.parse_sidebar().
    Handles:
      - Multi-line skill values (continuation = starts lowercase)
      - Email / phone detection (may live in __PREAMBLE__ or labelled section)
      - Link filtering (remove template/builder links)
    """

    # Known contact labels from sidebar
    CONTACT_LABELS = {
        'ADDRESS', 'PHONE', 'EMAIL', 'MOBILE', 'TEL',
        'PLACE OF BIRTH', 'DRIVING LICENSE', 'DATE OF BIRTH',
        'NATIONALITY', 'WEBSITE',
    }
    LINK_LABELS = {'LINKS', 'SOCIAL', 'LINKEDIN', 'GITHUB'}
    SKIP_LINKS = {'resume templates', 'build this template', 'pinterest', 'resumeviking'}

    def extract(self, sections: Dict[str, List[str]]) -> Dict[str, Any]:
        all_lines = [l for lines in sections.values() for l in lines]
        joined = '\n'.join(all_lines)

        return {
            'address':          self._address(sections, joined),
            'phone':            self._regex_find(joined, r'\b\d{7,15}\b'),
            'email':            self._regex_find(joined, r'\b[\w._%+\-]+@[\w.\-]+\.[a-z]{2,}\b'),
            'place_of_birth':   self._section_value(sections, ['PLACE OF BIRTH']),
            'driving_license':  self._section_value(sections, ['DRIVING LICENSE']),
            'links':            self._links(sections),
            'skills':           self._merge_skills(sections),
            'hobbies':          self._list_section(sections, ['HOBBIES']),
            'languages':        self._list_section(sections, ['LANGUAGES']),
        }

    def _address(self, sections, joined_text):
        lines = sections.get('ADDRESS', [])
        if lines:
            return ', '.join(l.strip() for l in lines if l.strip())
        # Fallback: scan for address pattern
        addr_lines = []
        for line in joined_text.split('\n'):
            if re.match(r'^\d{3,5}\s+\w', line):
                addr_lines.append(line)
            elif re.search(r'\b(CA|NY|TX|FL|IL|WA|PA|OH|GA|NC|AZ|[A-Z]{2})\s+\d{5}\b', line):
                addr_lines.append(line)
            elif line.strip() in ('United States', 'United Kingdom', 'Canada', 'India'):
                addr_lines.append(line)
        return ', '.join(addr_lines) if addr_lines else None

    def _regex_find(self, text, pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(0) if m else None

    def _section_value(self, sections, keys):
        for k in keys:
            v = sections.get(k, [])
            if v:
                return ' '.join(v).strip()
        return None

    def _links(self, sections):
        links = []
        for k in list(self.LINK_LABELS) + ['LINKS']:
            for l in sections.get(k, []):
                if l.lower().strip() not in self.SKIP_LINKS:
                    links.append(l.strip())
        # Deduplicate
        seen = set()
        return [l for l in links if not (l.lower() in seen or seen.add(l.lower()))]

    def _merge_skills(self, sections) -> List[str]:
        """
        Merge continuation lines.
        'Kitchen equipment\\noperation' → 'Kitchen equipment operation'
        A line is a continuation if it starts with a lowercase letter
        AND no sidebar section header was between it and previous line.
        """
        raw_lines = sections.get('SKILLS', [])
        merged: List[str] = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            # Continuation: starts lowercase
            if merged and line[0].islower():
                merged[-1] = merged[-1].rstrip() + ' ' + line
            else:
                # Could be comma-separated multi-skills on one line
                if ',' in line:
                    merged.extend(s.strip() for s in line.split(',') if s.strip())
                else:
                    merged.append(line)
        return merged

    def _list_section(self, sections, keys) -> List[str]:
        for k in keys:
            lines = sections.get(k, [])
            if lines:
                result = []
                for line in lines:
                    for item in re.split(r'[,;]', line):
                        item = item.strip()
                        if item:
                            result.append(item)
                return result
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Resume Assembler — top-level entry point
# ─────────────────────────────────────────────────────────────────────────────

# Known section names → canonical key
SECTION_ALIASES = {
    # Employment
    'EMPLOYMENT HISTORY': 'employment',
    'EXPERIENCE': 'employment',
    'WORK EXPERIENCE': 'employment',
    'PROFESSIONAL EXPERIENCE': 'employment',
    'CAREER HISTORY': 'employment',
    'WORK HISTORY': 'employment',
    'JOB HISTORY': 'employment',
    'RELEVANT EXPERIENCE': 'employment',
    # Education
    'EDUCATION': 'education',
    'ACADEMIC BACKGROUND': 'education',
    'QUALIFICATIONS': 'education',
    'ACADEMIC HISTORY': 'education',
    'EDUCATIONAL BACKGROUND': 'education',
    # Profile
    'PROFILE': 'profile',
    'SUMMARY': 'profile',
    'OBJECTIVE': 'profile',
    'ABOUT ME': 'profile',
    'ABOUT': 'profile',
    'PROFESSIONAL SUMMARY': 'profile',
    'CAREER OBJECTIVE': 'profile',
    'PERSONAL STATEMENT': 'profile',
    'OVERVIEW': 'profile',
    # Courses / Certifications
    'COURSES': 'courses',
    'CERTIFICATIONS': 'courses',
    'CERTIFICATES': 'courses',
    'TRAINING': 'courses',
    'LICENSES': 'courses',
    'CREDENTIALS': 'courses',
    'PROFESSIONAL DEVELOPMENT': 'courses',
    # Accomplishments
    'ACCOMPLISHMENTS': 'accomplishments',
    'ACHIEVEMENTS': 'accomplishments',
    'KEY ACHIEVEMENTS': 'accomplishments',
    'AWARDS': 'accomplishments',
    'HONORS': 'accomplishments',
    # Projects
    'PROJECTS': 'projects',
    'PERSONAL PROJECTS': 'projects',
    'OPEN SOURCE': 'projects',
    'PROJECT EXPERIENCE': 'projects',
    'KEY PROJECTS': 'projects',
    'NOTABLE PROJECTS': 'projects',
    'PORTFOLIO': 'projects',
    'SIDE PROJECTS': 'projects',
    'TECHNICAL PROJECTS': 'projects',
    'ACADEMIC PROJECTS': 'projects',
    # Skills
    'SKILLS': 'skills',
    'TECHNICAL SKILLS': 'skills',
    'CORE COMPETENCIES': 'skills',
    'COMPETENCIES': 'skills',
    'EXPERTISE': 'skills',
    'TECHNOLOGIES': 'skills',
    'TOOLS': 'skills',
    'TOOLS & TECHNOLOGIES': 'skills',
    # Languages
    'LANGUAGES': 'languages',
    'LANGUAGE SKILLS': 'languages',
}

class ProjectsSectionParser:
    """
    Extract raw project text from tagged tokens.
    Returns the concatenated text of all BODY/BULLET/JOB_TITLE tokens
    so ProjectParser (project_parser.py) can do the detailed parsing.
    """

    def parse(self, tokens: List[Token]) -> str:
        parts = []
        for tok in tokens:
            if tok.kind in ('JOB_TITLE', 'BODY', 'BULLET'):
                parts.append(tok.raw)
            elif tok.kind == 'DATE':
                parts.append(tok.raw)
        return '\n'.join(parts).strip()


class SkillsSectionParser:
    """
    Extract raw skills text from tokens.
    Returns the concatenated text for SkillsParser to process.
    """

    def parse(self, tokens: List[Token]) -> str:
        parts = []
        for tok in tokens:
            if tok.kind in ('BODY', 'BULLET', 'JOB_TITLE'):
                parts.append(tok.raw)
        return '\n'.join(parts).strip()


class ResumeAssembler:
    """
    Takes DocumentStructure from layout_extractor and produces clean resume JSON.
    Flow:
      1. Tokenize main_text
      2. Split tokens by section
      3. Route each section's tokens to the right parser
      4. Extract contact from sidebar
      5. Assemble final dict
    """

    def __init__(self):
        self.sidebar_extractor = SidebarExtractor()
        self.employment_parser = EmploymentParser()
        self.education_parser  = EducationParser()
        self.courses_parser    = CoursesParser()
        self.accomplishments_parser = AccomplishmentsParser()
        self.projects_parser   = ProjectsSectionParser()
        self.skills_parser     = SkillsSectionParser()

    def assemble(
        self,
        full_width_text: str,
        sidebar_sections: Dict[str, List[str]],
        main_sections: Dict[str, str],   # raw tagged text per section
    ) -> Dict[str, Any]:

        # ── Personal info from header ──────────────────────────────────────
        name, title = self._parse_header(full_width_text)

        # ── Contact from sidebar ───────────────────────────────────────────
        contact = self.sidebar_extractor.extract(sidebar_sections)

        # ── Tokenize and route main sections ──────────────────────────────
        section_tokens = self._split_into_sections(main_sections)

        profile_text   = self._get_profile(main_sections)
        employment     = self._parse_section(section_tokens, 'employment', self.employment_parser)
        education      = self._parse_section(section_tokens, 'education', self.education_parser)
        courses        = self._parse_section(section_tokens, 'courses', self.courses_parser)
        accomplishments = self._parse_section(section_tokens, 'accomplishments', self.accomplishments_parser)

        # Projects: extract raw text for ProjectParser
        projects_raw_text = ""
        if 'projects' in section_tokens and section_tokens['projects']:
            projects_raw_text = self.projects_parser.parse(section_tokens['projects'])

        # Skills from main section tokens (returns raw text for SkillsParser)
        skills_section_text = ""
        if 'skills' in section_tokens and section_tokens['skills']:
            skills_section_text = self.skills_parser.parse(section_tokens['skills'])

        # Languages from section tokens
        languages_raw_text = ""
        if 'languages' in section_tokens and section_tokens['languages']:
            languages_raw_text = '\n'.join(t.raw for t in section_tokens['languages'])

        return {
            'personal_info': {
                'name':            name,
                'title':           title,
                'address':         contact.get('address'),
                'phone':           contact.get('phone'),
                'email':           contact.get('email'),
                'place_of_birth':  contact.get('place_of_birth'),
                'driving_license': contact.get('driving_license'),
                'links':           contact.get('links', []),
            },
            'profile':             profile_text,
            'skills_raw':          contact.get('skills', []),         # sidebar skills (list)
            'skills_section_text': skills_section_text,               # main-column skills raw text
            'hobbies':             contact.get('hobbies', []),
            'languages':           contact.get('languages', []),
            'languages_section':   languages_raw_text,
            'employment_history':  employment,
            'education':           education,
            'courses':             courses,
            'accomplishments':     accomplishments,
            'projects_raw_text':   projects_raw_text,                 # for ProjectParser
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _parse_header(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract name and title from [NAME]...[/NAME] [TITLE]...[/TITLE] tagged text."""
        name_m  = re.search(r'\[NAME\](.*?)\[/NAME\]', text, re.DOTALL)
        title_m = re.search(r'\[TITLE\](.*?)\[/TITLE\]', text, re.DOTALL)
        name  = name_m.group(1).strip()  if name_m  else None
        title = title_m.group(1).strip() if title_m else None
        return name, title

    def _split_into_sections(self, main_sections: Dict[str, str]) -> Dict[str, List[Token]]:
        """
        main_sections comes from layout_extractor._parse_tagged_text(),
        which splits on [SECTION NAME] tags.
        Keys are already section names. Values are the tagged text of each section.
        Tokenize each value and map to canonical section key.
        """
        result: Dict[str, List[Token]] = {}
        for raw_key, tagged_text in main_sections.items():
            canonical = SECTION_ALIASES.get(raw_key.upper())
            if canonical:
                tokens = tokenize(tagged_text)
                # Merge into canonical (multiple raw keys may map to same canonical)
                if canonical in result:
                    result[canonical].extend(tokens)
                else:
                    result[canonical] = tokens
        return result

    def _get_profile(self, main_sections: Dict[str, str]) -> Optional[str]:
        """Profile is plain text — strip any stray tags and return."""
        for key in ('PROFILE', 'SUMMARY', 'OBJECTIVE', 'ABOUT ME', 'ABOUT',
                     'PROFESSIONAL SUMMARY', 'CAREER OBJECTIVE', 'OVERVIEW'):
            raw = main_sections.get(key, '')
            if raw:
                # Strip all tags, return clean text
                clean = re.sub(r'\[[A-Z_]+\].*?\[/[A-Z_]+\]', '', raw, flags=re.DOTALL)
                clean = re.sub(r'\[[^\]]+\]', '', clean)
                return clean.strip() or None
        return None

    def _parse_section(self, section_tokens, canonical_key, parser):
        """Route a section's tokens to the appropriate parser."""
        tokens = section_tokens.get(canonical_key, [])
        if not tokens:
            return [] if hasattr(parser, '__iter__') else None
        return parser.parse(tokens)