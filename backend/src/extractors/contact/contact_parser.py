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
    # Medical
    'registered nurse', 'clinical director', 'medical officer',
    'staff nurse', 'charge nurse', 'nurse practitioner',
    'physician assistant', 'medical assistant', 'dental hygienist',
    'physical therapist', 'occupational therapist', 'speech therapist',
    'clinical researcher', 'lab technician', 'pharmacy technician',
    # Legal
    'attorney at law', 'legal counsel', 'senior partner',
    'managing partner', 'associate attorney', 'legal assistant',
    'court clerk', 'case manager', 'compliance officer',
    # Finance
    'financial analyst', 'investment banker', 'portfolio manager',
    'risk analyst', 'credit analyst', 'fund manager',
    'tax consultant', 'audit manager', 'budget analyst',
    # Education
    'assistant professor', 'teaching assistant', 'research assistant',
    'associate professor', 'adjunct professor', 'lab instructor',
    'academic advisor', 'department chair', 'dean of students',
    # Operations / Sales
    'sales representative', 'account executive', 'branch manager',
    'store manager', 'shift supervisor', 'district manager',
    'supply chain manager', 'logistics coordinator', 'fleet manager',
}
# Common lowercase particles in names (allowed without uppercase)
_NAME_PARTICLES = {'de', 'van', 'von', 'al', 'el', 'la', 'le', 'du', 'da', 'di',
                   'bin', 'binti', 'ibn', 'ben', 'mac', 'mc'}

# Hard blacklist: phrases that must NEVER become candidate names.
# These are section headers, resume sub-headings, and common title fragments.
_NAME_HARD_BLACKLIST = {
    # Section headers
    'summary', 'skills', 'projects', 'experience', 'education',
    'certifications', 'key achievements', 'strengths',
    'professional summary', 'career objective', 'core competencies',
    'technical skills', 'work experience', 'professional experience',
    'personal statement', 'career summary', 'executive summary',
    'employment history', 'academic background', 'professional profile',
    'key strengths', 'areas of expertise',
    # Sub-heading fragments (resume template noise)
    'javascript expertise', 'cross-functional teamwork', 'self-starter',
    'team player', 'problem solver', 'quick learner',
    'attention to detail', 'strong communication',
}

# Technology / skill terms — if ALL words in a candidate match these,
# it's a skill phrase, not a person name.
_TECH_WORDS = {
    'javascript', 'typescript', 'python', 'java', 'react', 'angular',
    'vue', 'node', 'express', 'django', 'flask', 'spring', 'docker',
    'kubernetes', 'aws', 'azure', 'gcp', 'mongodb', 'postgresql',
    'mysql', 'redis', 'sql', 'nosql', 'graphql', 'rest', 'api',
    'html', 'css', 'sass', 'less', 'webpack', 'babel', 'git', 'github',
    'ci', 'cd', 'devops', 'agile', 'scrum', 'kanban', 'jira',
    'expertise', 'proficiency', 'proficient', 'advanced', 'intermediate',
    'beginner', 'framework', 'frameworks', 'library', 'libraries',
    'tools', 'technologies', 'microservices', 'architecture',
    'redux', 'vuex', 'mobx', 'jest', 'mocha', 'cypress', 'selenium',
    'spark', 'hadoop', 'kafka', 'terraform', 'ansible', 'jenkins',
    'photoshop', 'illustrator', 'figma', 'sketch',
    'tensorflow', 'pytorch', 'keras', 'numpy', 'pandas', 'scikit',
    'bootstrap', 'tailwind', 'material', 'nextjs', 'nuxt',
    'junit', 'nunit', 'pyunit', 'testcafe', 'webgl',
    'c', 'cpp', 'golang', 'rust', 'swift', 'kotlin', 'scala',
    'ruby', 'rails', 'php', 'laravel', 'perl',
    'linux', 'unix', 'windows', 'macos',
    'networking', 'protocols', 'tcp', 'http', 'dns', 'ssl',
    'machine', 'learning', 'deep', 'neural', 'nlp', 'ai', 'ml',
    'data', 'analytics', 'visualization', 'tableau', 'excel',
    'seo', 'sem', 'marketing', 'design', 'ux', 'ui',
    'teamwork', 'leadership', 'communication', 'collaboration',
    'management', 'development', 'engineering', 'testing',
}

# Regex to split name from contact info on the same line
# Matches: Email, email, E-mail, Phone, Tel, Mobile, |, ●, •, ⎪, ·
_LINE_SPLIT_RE = re.compile(
    r'\s*(?:'
    r'[Ee]-?[Mm]ail\s*:?'          # Email : / email:
    r'|[Pp]hone\s*:?'              # Phone : / phone:
    r'|[Tt]el(?:ephone)?\s*:?'     # Tel : / Telephone:
    r'|[Mm]obile\s*:?'             # Mobile :
    r'|[Cc]ell\s*:?'               # Cell :
    r'|[Cc]ontact\s*:?'            # Contact :
    r'|\|'                          # | separator
    r'|●|•|⎪|·|◆|►'               # bullet separators
    r'|[\w._%+-]+@[\w.-]+\.\w{2,}' # raw email address
    r'|\+?\d[\d\s\-().]{7,}'       # phone number
    r'|https?://\S+'               # URL
    r'|www\.\S+'                   # www URL
    r')'
)


def _split_name_from_contact(line: str) -> str:
    """Extract name portion from a line that may contain contact info.

    Examples:
        'Kiran Malhotra Email : kiran@m.com' → 'Kiran Malhotra'
        'John Smith | john@x.com | 555-1234'  → 'John Smith'
        'Jane Doe • jane@x.com'               → 'Jane Doe'
        'Pure Name Line'                       → 'Pure Name Line'
    """
    m = _LINE_SPLIT_RE.search(line)
    if m:
        before = line[:m.start()].strip().rstrip(',').rstrip(':').strip()
        if before:
            return before
    return line.strip()


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
    # Reject known non-name phrases (hard blacklist)
    if s.lower() in _NOT_NAMES:
        return False
    if s.lower() in _NAME_HARD_BLACKLIST:
        return False
    # Reject if ALL words are known technology / skill terms
    # (e.g. "JavaScript Expertise", "Vue Redux TypeScript")
    lower_words = {w.lower() for w in words}
    if lower_words and lower_words.issubset(_TECH_WORDS):
        return False
    # Reject if it resolves to a known section header
    from src.registries.section_registry import resolve as _resolve_section
    if _resolve_section(s):
        return False
    # Reject if the name ends with a common job title suffix
    # e.g., "PIPING ENGINEER", "ART TEACHER", "PROJECT MANAGER"
    _TITLE_SUFFIXES = {
        'engineer', 'developer', 'manager', 'architect', 'consultant',
        'analyst', 'specialist', 'teacher', 'designer', 'director',
        'officer', 'coordinator', 'administrator', 'supervisor',
        'technician', 'associate', 'assistant', 'executive', 'intern',
        'planner', 'inspector', 'auditor', 'operator',
    }
    last_word = words[-1].lower().rstrip('s')  # handle plurals
    if last_word in _TITLE_SUFFIXES and len(words) >= 2:
        return False
    # Reject common section header fragments that pass other checks
    _HEADER_FRAGMENTS = {
        'career objectives', 'career objective', 'core accomplishments',
        'core competencies', 'career overview', 'career summary',
        'educational qualifications', 'academic qualifications',
        'professional qualifications', 'personal details',
        'professional details', 'position desire', 'position desired',
        'curriculum vitae', 'curriculam vitea', 'science education',
        'university departmental', 'microsoft office',
        'esteemed organization', 'career work', 'senior planning',
        'logistics and', 'finance minister',
    }
    if s.lower() in _HEADER_FRAGMENTS:
        return False
    return True


class ContactParser:
    """
    Extract contact fields from resume text.
    Accepts full_width_text (tagged header), raw_text, sidebar_text.
    """

    def parse(self, full_width_text: str = "", raw_text: str = "",
              sidebar_text: str = "", main_text: str = "",
              hyperlinks: list = None) -> Dict[str, Any]:
        combined = "\n".join(filter(None, [full_width_text, sidebar_text, raw_text]))
        # Append hyperlink URIs so regex patterns can find LinkedIn/GitHub
        if hyperlinks:
            link_text = "\n".join(h.get('uri', '') for h in hyperlinks if h.get('uri'))
            combined = combined + "\n" + link_text
        return {
            "name":     self._extract_name(full_width_text, raw_text, sidebar_text, main_text),
            "email":    self._extract_email(combined),
            "phone":    self._extract_phone(combined),
            "linkedin": self._extract_linkedin(combined),
            "github":   self._extract_github(combined),
            "location": self._extract_location(combined, sidebar_text, main_text),
        }

    def _extract_name(self, full_width_text: str, raw_text: str,
                       sidebar_text: str = "", main_text: str = "") -> Optional[str]:
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

        # Strategy 2: heuristic — check main_text FIRST (name is almost always
        # the first line of main content), then sidebar, then raw_text.
        # Sidebar is checked last because two-column resumes often have skill
        # lines that look like names (e.g. "Vue Redux TypeScript").
        for text_src in [main_text, raw_text, sidebar_text]:
            if not text_src:
                continue
            lines = [l.strip() for l in text_src.split('\n') if l.strip()]
            for line in lines[:5]:
                clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
                # First try the full line
                if _is_name_line(clean):
                    return clean
                # Then try splitting name from contact info on same line
                # e.g. "Kiran Malhotra Email : kiran@m.com" → "Kiran Malhotra"
                split = _split_name_from_contact(clean)
                if split != clean and _is_name_line(split):
                    return split

        # Strategy 3: scan first 10 lines of raw_text (fallback)
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
        for line in lines[:10]:
            clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
            if _is_name_line(clean):
                return clean
            split = _split_name_from_contact(clean)
            if split != clean and _is_name_line(split):
                return split

        # Strategy 4: ALL CAPS line in first 5 lines
        for line in lines[:5]:
            clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
            # Try split first for ALL CAPS check too
            split = _split_name_from_contact(clean)
            for candidate in [clean, split]:
                words = candidate.split()
                if 2 <= len(words) <= 4 and candidate.isupper() and not re.search(r'\d', candidate):
                    return candidate.title()

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
        # Fallback: extract from tel: hyperlink URIs
        tel_m = re.search(r'tel:(\+?[\d\s\-().]+)', text)
        if tel_m:
            phone = tel_m.group(1).strip()
            if len(re.sub(r'\D', '', phone)) >= 7:
                return phone
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

    def _extract_location(self, text: str, sidebar_text: str = "",
                           main_text: str = "") -> Optional[str]:
        # First search sidebar text (often has location early)
        if sidebar_text:
            result = self._extract_location_from_text(sidebar_text)
            if result:
                return result
        # Second: search main_text header area (address blocks in main column)
        if main_text:
            result = self._extract_location_from_text(main_text)
            if result:
                return result
        return self._extract_location_from_text(text)

    def _extract_location_from_text(self, text: str) -> Optional[str]:
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Strategy 1: "City, ST" pattern (US format) — only in header area
        city_state_re = re.compile(
            r'\b([A-Z][a-zA-Z\s]{2,25}),\s*([A-Z]{2}|\b[A-Z][a-zA-Z]{3,20})\b'
        )
        # Section headers/keywords that should NOT be searched for locations
        _section_kw_re = re.compile(
            r'(?:programming|languages?|frameworks?|libraries|tools|skills|'
            r'databases?|education|experience|projects|certific)[:\s]', re.I)
        # Job entry patterns — skip these for location extraction
        _job_entry_re = re.compile(
            r'\b(?:at|@)\s+[A-Z]|'   # "at Company" pattern
            r'\b(?:Engineer|Developer|Manager|Designer|Teacher|Nurse|'
            r'Analyst|Associate|Assistant|Coordinator)\b', re.I)
        _tag_re = re.compile(r'\[/?[A-Z_]+\]')

        # First pass: prefer lines with street address or zip code
        for line in lines[:15]:
            if _LINKEDIN_RE.search(line):
                continue
            if _section_kw_re.search(line) or _job_entry_re.search(line):
                continue
            if re.search(r'\[(?:JOB_TITLE|NAME|TITLE)\]', line):
                continue
            clean_line = _tag_re.sub('', line).strip()
            if not clean_line:
                continue
            # Strip email and phone from line before matching
            clean_line = _EMAIL_RE.sub('', clean_line)
            clean_line = re.sub(r'[\(\)]*\d[\d\s\-\.]{6,15}', '', clean_line)
            clean_line = clean_line.strip(' ,;|')
            if not clean_line:
                continue
            # Prefer address lines with zip codes or street numbers
            if re.search(r'\d{5}|\d+\s+(?:Ave|St|Blvd|Dr|Rd|Lane|Way)', clean_line, re.I):
                m = city_state_re.search(clean_line)
                if m:
                    return m.group(0).strip()

        # Second pass: any City, ST match
        for line in lines[:15]:
            if _LINKEDIN_RE.search(line):
                continue
            if _section_kw_re.search(line) or _job_entry_re.search(line):
                continue
            if re.search(r'\[(?:JOB_TITLE|NAME|TITLE)\]', line):
                continue
            clean_line = _tag_re.sub('', line).strip()
            if not clean_line:
                continue
            # Strip email and phone before matching
            clean_line = _EMAIL_RE.sub('', clean_line)
            clean_line = re.sub(r'[\(\)]*\d[\d\s\-\.]{6,15}', '', clean_line)
            clean_line = clean_line.strip(' ,;|')
            if not clean_line:
                continue
            m = city_state_re.search(clean_line)
            if m:
                return m.group(0).strip()

        # Strategy 1.5: "Street, City, ZIP, Country" or "City, ZIP" format
        # Catches addresses like "9 Wall St, New York, 10005, USA"
        addr_re = re.compile(
            r'(?:\d+\s+[A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Lane|Way|Street|Avenue),\s*)?'
            r'([A-Z][a-zA-Z\s]{2,20}),\s*(?:\d{5}|[A-Z]{2,3})',
        )
        for line in lines[:15]:
            if _LINKEDIN_RE.search(line):
                continue
            if _section_kw_re.search(line) or _job_entry_re.search(line):
                continue
            if re.search(r'\[(?:JOB_TITLE|NAME|TITLE)\]', line):
                continue
            clean_line = _tag_re.sub('', line).strip()
            if not clean_line:
                continue
            # Strip email and phone before matching
            clean_line = _EMAIL_RE.sub('', clean_line)
            clean_line = re.sub(r'[\(\)]*\d[\d\s\-\.]{6,15}', '', clean_line)
            clean_line = clean_line.strip(' ,;|')
            if not clean_line:
                continue
            m = addr_re.search(clean_line)
            if m:
                city = m.group(1).strip()
                if len(city) > 2:
                    return city

        # Strategy 2: Nationality/Place of Birth/Address labels
        # Use inline (?i:...) for keywords only; capture group is case-sensitive
        label_re = re.compile(
            r'(?i:Nationality|Place\s+of\s+Birth|Address|Location|City)'
            r'\s*[:\|\s]\s*([A-Z][a-zA-Z\s,]+)')
        for line in lines[:30]:
            # Strip tags first
            clean = _tag_re.sub('', line).strip()
            m = label_re.search(clean)
            if m:
                val = m.group(1).strip().rstrip(',').strip()
                # Remove trailing noise like "Driving license Full"
                val = re.sub(r'\s+Driving\s+license.*$', '', val, flags=re.I).strip()
                # Remove trailing dates/numbers
                val = re.sub(r'\s+\d{4}.*$', '', val).strip()
                if val and 3 < len(val) < 60:
                    return val

        # Strategy 3: Sidebar [ADDRESS] or [PLACE] section
        addr_section_re = re.compile(
            r'\[(ADDRESS|PLACE|LOCATION|NATIONALITY|CITY)\]\s*\n(.+?)(?:\n\[|$)',
            re.I | re.DOTALL)
        m = addr_section_re.search(text)
        if m:
            addr_lines = [l.strip() for l in m.group(2).strip().split('\n') if l.strip()]
            if addr_lines:
                return ', '.join(addr_lines[:2])  # first 2 lines as location

        # Strategy 4: contact line with pipe/bar separator containing a place name
        # e.g., "email@email.com | 938212857 | Mejia"
        for line in lines[:5]:
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                for part in parts:
                    # Skip emails, numbers, URLs, and known link text
                    if (_EMAIL_RE.search(part) or part.isdigit() or
                        _URL_RE.search(part) or part.lower() in
                        {'github', 'linkedin', 'portfolio', 'website', 'link'}):
                        continue
                    # Must be 1-3 words, starts with uppercase, no digits
                    words = part.split()
                    if (1 <= len(words) <= 3 and words[0][0:1].isupper()
                            and not any(c.isdigit() for c in part)
                            and len(part) > 2):
                        return part

        return None
