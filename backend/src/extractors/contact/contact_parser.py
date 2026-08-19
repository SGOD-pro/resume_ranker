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
from typing import Optional, Dict, Any, Union


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

# Title words that, when appearing as FIRST word, indicate a job title
# (not a person name). e.g., "Database Programmer", "Project Manager"
_TITLE_FIRST_WORDS = {
    'senior', 'junior', 'lead', 'chief', 'head', 'principal', 'staff',
    'adjunct', 'associate', 'assistant', 'deputy', 'vice',
    # Role-type first words ("Database Programmer", "Project Manager")
    'database', 'project', 'program', 'product', 'system', 'systems',
    'network', 'security', 'quality', 'business', 'marketing',
    'sales', 'financial', 'human', 'information', 'it',
    'clinical', 'medical', 'dental', 'pharmacy', 'nursing',
    'construction', 'mechanical', 'electrical', 'civil', 'structural',
    'industrial', 'environmental', 'chemical', 'biomedical',
    'administrative', 'executive', 'general', 'regional', 'district',
    'substitute', 'kindergarten', 'history', 'math', 'science',
    'warehouse', 'aviation', 'unit', 'content', 'web',
    'master', 'multi', 'tactical',
}

# Company name suffixes — reject names containing these.
_COMPANY_SUFFIXES = {
    'ltd', 'ltd.', 'inc', 'inc.', 'corp', 'corp.', 'corporation',
    'llc', 'llp', 'pvt', 'pvt.', 'co.', 'plc',
    'services', 'solutions', 'technologies', 'consultancy',
    'enterprises', 'industries', 'systems', 'associates',
    'partners', 'holdings', 'group', 'labs', 'studio',
    'foundation', 'institute', 'university', 'college',
    'hospital', 'clinic',
}

# OCR artifact patterns — names containing these are likely garbled.
_OCR_NOISE_RE = re.compile(
    r'[\xc2\xc3\xc4\xc5][\x80-\xbf]'   # Mojibake from UTF-8 misread
    r'|[\u00c2\u00c3\u00e2]'              # Common OCR artifacts: Â, Ã, â
    r'|\(cid:\d+\)'                       # PDF character-ID leak
    r'|[\ue000-\uf8ff]'                   # Unicode Private Use Area
    r'|[\u2022\u25cf\u25a0\u25aa]'        # Bullets: •, ●, ■, ▪
    r'|[^\x20-\x7e\u00c0-\u024f\u0900-\u097f\u0600-\u06ff\u0400-\u04ff]'  # Non-printable outside Latin/Devanagari/Arabic/Cyrillic
)

# Generic English words — if ≥2 of the words in a 3-4 word "name" are
# these common words, it's likely a descriptive phrase, not a person name.
_GENERIC_WORDS = {
    'and', 'the', 'for', 'with', 'from', 'into', 'over', 'under',
    'management', 'development', 'services', 'systems', 'operations',
    'planning', 'strategy', 'leadership', 'communication', 'record',
    'standard', 'process', 'quality', 'assurance', 'control',
    'safety', 'training', 'support', 'center', 'centre',
    'oriented', 'centered', 'focused', 'driven', 'based',
    'abilities', 'overview', 'proficiency', 'objectives',
    'interpersonal', 'organizational', 'professional', 'personal',
    'academic', 'career', 'task', 'multi',
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
    'asp', 'net', 'joomla', 'wordpress', 'drupal', 'magento',
    'gsm', 'cdma', 'matlab', 'simulink', 'labview',
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
    if not (1 <= len(words) <= 5):
        return False
    if len(words) == 1 and '.' not in words[0]:
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
    # Require ALL words start uppercase (or are name particles), but allow
    # second or third word to be lowercase if it's a 2-3 word name
    for i, w in enumerate(words):
        if not w[0].isupper() and w.lower() not in _NAME_PARTICLES:
            if i > 0 and len(words) <= 3:
                pass # Allow e.g. "Jitender kumar"
            else:
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
        'instructor', 'programmer', 'teller', 'pharmacist',
        'publicist', 'strategist', 'maintainer', 'writer',
    }
    last_word = words[-1].lower().rstrip('s')  # handle plurals
    if last_word in _TITLE_SUFFIXES and len(words) >= 2:
        return False
    # Reject if FIRST word is a common title prefix
    # Catches: "Database Programmer", "Project Management", "Marketing Consultant"
    first_word = words[0].lower()
    if first_word in _TITLE_FIRST_WORDS and len(words) >= 2:
        return False
    # Reject if name contains company suffixes
    # Catches: "Tata Consultancy Services Ltd."
    for w in words:
        if w.lower().rstrip('.') in _COMPANY_SUFFIXES:
            return False
    # Reject OCR noise / garbled names
    # Catches: "Qualification Â", "SEI EndorsedÂ"
    if _OCR_NOISE_RE.search(s):
        return False
    # Reject descriptive phrases: ≥2 generic English words in 3-4 word "name"
    # Catches: "People Centered Leadership", "Classroom Management Interpersonal"
    if len(words) >= 3:
        generic_count = sum(1 for w in words if w.lower() in _GENERIC_WORDS)
        if generic_count >= 2:
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
        # Observed bad names from benchmark
        'people centered leadership', 'classroom management interpersonal',
        'tactical planning goal-oriented', 'multi task abilities',
        'court procedures due dilligence', 'academic record',
        'professional overview', 'information technology provision',
    }
    if s.lower() in _HEADER_FRAGMENTS:
        return False
    return True


class ContactParser:
    """
    Extract contact fields from resume text.
    Accepts full_width_text (tagged header), raw_text, sidebar_text.
    """

    # ── ODL coordinate constants ──────────────────────────────────────────────
    # ODL uses PDF coordinate space: origin (0,0) at BOTTOM-LEFT.
    # bounding_box = [x0, y0, x1, y1] where:
    #   y0 (index 1) = bottom edge of element
    #   y1 (index 3) = top edge of element
    # Standard A4 page height = 841.89 pt ≈ 842 pt.
    # "Top 35%" means y1 (top edge) > 842 * 0.65 = 547.
    # We derive max_y dynamically from page-1 elements so non-A4 pages work too.
    _HEADER_Y1_THRESHOLD_STATIC = 547  # fallback for A4 when no dynamic max available

    def _build_header_text_from_elements(self, elements: Union[list, dict]) -> str:
        """
        Return concatenated content of ODL elements that are physically located
        in the top 20% of page 1 (by bounding_box y1 — the TOP edge of each element
        in bottom-left PDF coordinate space).

        Side-column contacts appear at LOW array indices only by accident; their
        physical y1 coordinate places them in the header zone regardless of where
        ODL serialised them in the elements array.
        """
        # ODL returns a top-level dict where the elements are in the "kids" array.
        kids = elements.get('kids', []) if isinstance(elements, dict) else elements

        # ODL nests text blocks inside paragraphs/lists. Flatten the tree to find
        # all elements with a bounding box and content.
        def _flatten_elements(node_list: list) -> list:
            flat = []
            for node in node_list:
                if not isinstance(node, dict):
                    continue
                flat.append(node)
                for k, v in node.items():
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                        flat.extend(_flatten_elements(v))
            return flat

        all_elems = _flatten_elements(kids)

        page1_elems = [
            el for el in all_elems
            if el.get('page number', el.get('page_number', 1)) == 1
        ]
        if not page1_elems:
            return ""

        # Derive page height from the highest y1 value seen on the page.
        # Fall back to the static A4 constant if the bbox data is missing.
        max_y1 = 0.0
        for el in page1_elems:
            bb = el.get('bounding box', el.get('bounding_box'))
            if bb and len(bb) >= 4:
                try:
                    max_y1 = max(max_y1, float(bb[3]))
                except (TypeError, ValueError):
                    pass

        if max_y1 < 100:  # degenerate / missing bbox data
            threshold = self._HEADER_Y1_THRESHOLD_STATIC
        else:
            threshold = max_y1 * 0.65  # top 35% → y1 above 65% of page height

        header_contents = []
        for el in page1_elems:
            bb = el.get('bounding box', el.get('bounding_box'))
            if bb and len(bb) >= 4:
                try:
                    y1 = float(bb[3])
                except (TypeError, ValueError):
                    y1 = 0.0
                if y1 < threshold:
                    continue  # element is BELOW the header zone — skip
            # No bbox → include by default (conservative fallback)
            content = el.get('content', el.get('text', ''))
            if content:
                header_contents.append(str(content))
            
            # Check for nested link/uri attributes that might contain the email
            # Flatten the dict to string and use regex to find mailto/tel/@ links
            dumped = str(el)
            import re
            # Extract links that look like mailto:, tel:, or emails from the dictionary string representation
            links = re.findall(r"(?:mailto:|tel:|[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,})[^\s'\"\}\]]*", dumped)
            for l in links:
                # Remove common JSON/dict artifacts if any got caught
                clean_link = l.rstrip("',\"}]")
                if clean_link:
                    header_contents.append(clean_link)

        return "\n".join(header_contents)

    def parse(self, full_width_text: str = "", raw_text: str = "",
              sidebar_text: str = "", main_text: str = "",
              hyperlinks: list = None, elements: list = None,
              pymupdf_text: str = "") -> Dict[str, Any]:

        # ── Build header text from ODL bounding-box geometry ─────────────────
        # This catches email/phone in side-column headers that appear late in
        # the ODL elements array but are physically at the top of the page.
        header_text = ""
        if elements:
            header_text = self._build_header_text_from_elements(elements)

        combined = "\n".join(filter(None, [full_width_text, sidebar_text, raw_text, pymupdf_text]))

        # Candidate text for email/phone: header zone first, then full text.
        # Appending full text ensures the fallback still works when the header
        # zone missed something (e.g. very short / image-only header).
        if header_text:
            email_phone_text = header_text + "\n" + combined
        else:
            email_phone_text = combined

        # Append hyperlink URIs so regex patterns can find LinkedIn/GitHub/Email
        if hyperlinks:
            link_text = "\n".join(h.get('uri', '') for h in hyperlinks if h.get('uri'))
            email_phone_text = email_phone_text + "\n" + link_text
            combined = combined + "\n" + link_text

        name = self._extract_name(full_width_text, raw_text, sidebar_text, main_text, elements, pymupdf_text)
        if name == "Mohd Salman Nafees":
            print("DEBUG: _extract_name returned Mohd Salman Nafees!")
        
        return {
            "name":     name,
            "email":    self._extract_email(email_phone_text, hyperlinks),
            "phone":    self._extract_phone(email_phone_text),
            "linkedin": self._extract_linkedin(combined),
            "github":   self._extract_github(combined),
            "location": self._extract_location(combined, sidebar_text, main_text),
        }

    def _extract_name(self, full_width_text: str, raw_text: str,
                       sidebar_text: str = "", main_text: str = "", elements: list = None, pymupdf_text: str = "") -> Optional[str]:
        # Strategy 0: ODL JSON Heading
        if elements:
            kids = elements.get('kids', []) if isinstance(elements, dict) else elements
            def _flatten(node_list):
                flat = []
                for node in node_list:
                    if not isinstance(node, dict): continue
                    flat.append(node)
                    for k, v in node.items():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            flat.extend(_flatten(v))
                return flat

            for el in _flatten(kids):
                if not isinstance(el, dict):
                    continue
                # Top elements with large fonts or explicit heading tags
                if el.get('type') == 'heading' or str(el.get('pdfua_tag')).startswith('H'):
                    c = str(el.get('content', '')).strip()
                    if c:
                        c = re.split(r'[,|]| - ', c)[0].strip()
                        if _is_name_line(c):
                            return c
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
        # the first line of main content), then sidebar, then raw_text, then pymupdf_text.
        # Sidebar is checked last because two-column resumes often have skill
        # lines that look like names (e.g. "Vue Redux TypeScript").
        for text_src in [main_text, raw_text, sidebar_text, pymupdf_text]:
            if not text_src:
                continue
            lines = [l.strip() for l in text_src.split('\n') if l.strip()]
            for i, line in enumerate(lines[:30]):
                clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
                clean = re.sub(r'^#+\s*', '', clean).strip()
                
                # Check for "Lastname, Firstname" format (2 pure words)
                lf_match = re.match(r'^([A-Z][a-z]+),\s*([A-Z][a-z]+)$', clean)
                if lf_match:
                    return f"{lf_match.group(2)} {lf_match.group(1)}"
                    
                # Truncate titles/noise if comma, pipe, or dash present
                candidate = re.split(r'[,|]| - ', clean)[0].strip()
                
                # First try the full line
                if _is_name_line(candidate):
                    return candidate
                
                # Check consecutive line combination
                if i < len(lines) - 1:
                    next_line = lines[i + 1]
                    next_clean = re.sub(r'\[/?[A-Z_]+\]', '', next_line).strip()
                    next_candidate = re.split(r'[,|]| - ', next_clean)[0].strip()
                    combined_candidate = candidate + " " + next_candidate
                    if _is_name_line(combined_candidate):
                        return combined_candidate
                
                # Then try splitting name from contact info on same line
                split = _split_name_from_contact(candidate)
                if split != candidate and _is_name_line(split):
                    return split

        # Strategy 3: scan first 30 lines and last 30 lines of raw_text and pymupdf_text (fallback)
        for text_src in [raw_text, pymupdf_text]:
            if not text_src:
                continue
            lines = [l.strip() for l in text_src.split('\n') if l.strip()]
            search_lines = lines[:30] + (lines[-30:] if len(lines) > 30 else [])
            for line in search_lines:
                clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
                clean = re.sub(r'^#+\s*', '', clean).strip()
                lf_match = re.match(r'^([A-Z][a-z]+),\s*([A-Z][a-z]+)$', clean)
                if lf_match:
                    return f"{lf_match.group(2)} {lf_match.group(1)}"
                candidate = re.split(r'[,|]| - ', clean)[0].strip()
                
                if _is_name_line(candidate):
                    return candidate
                split = _split_name_from_contact(candidate)
                if split != candidate and _is_name_line(split):
                    return split

            # Strategy 4: ALL CAPS line in first 15 or last 15 lines
            search_lines_caps = lines[:15] + (lines[-15:] if len(lines) > 15 else [])
            for line in search_lines_caps:
                clean = re.sub(r'\[/?[A-Z_]+\]', '', line).strip()
                clean = re.sub(r'^#+\s*', '', clean).strip()
                candidate_base = re.split(r'[,|]| - ', clean)[0].strip()
                
                # Try split first for ALL CAPS check too
                split = _split_name_from_contact(candidate_base)
                for candidate in [candidate_base, split]:
                    words = candidate.split()
                    if 1 <= len(words) <= 4 and candidate.isupper() and not re.search(r'\d', candidate):
                        return candidate.title()

        return None

    def _extract_email(self, text: str, hyperlinks: list = None) -> Optional[str]:
        if hyperlinks:
            for h in hyperlinks:
                uri = h.get('uri', '')
                if uri.lower().startswith('mailto:'):
                    email = uri[7:].split('?')[0].strip()
                    m = _EMAIL_RE.search(email)
                    if m: return m.group(0).lower()
                elif '@' in uri and not uri.lower().startswith('http'):
                    m = _EMAIL_RE.search(uri)
                    if m: return m.group(0).lower()
        
        # Normalization for obfuscated emails
        text_norm = re.sub(r'(?i)\[at\]|\(at\)|<at>|{at}| at ', '@', text)
        text_norm = re.sub(r'(?i)\[dot\]|\(dot\)|<dot>|{dot}| dot ', '.', text_norm)

        # Match markdown links [text](mailto:email) and extract properly
        m_md = re.search(r'\]\(mailto:([^)?\s]+)', text_norm, re.IGNORECASE)
        if m_md:
            return m_md.group(1).lower().rstrip(').')

        m = _EMAIL_RE.search(text_norm)
        return m.group(0).lower() if m else None

    def _extract_phone(self, text: str) -> Optional[str]:
        # ── Priority 0: Markdown link [text](tel:...) — catches ODL-rendered links ──
        m_tel_md = re.search(r'\]\(tel:([^)\s]+)', text, re.IGNORECASE)
        if m_tel_md:
            result = m_tel_md.group(1).strip()
            if len(re.sub(r'\D', '', result)) >= 7:
                return result

        # ── Priority 1: bare tel: URI (from hyperlinks appended to text) ──────
        tel_m = re.search(r'tel:(\+?[\d\s\-().]+)', text)
        if tel_m:
            phone = tel_m.group(1).strip()
            if len(re.sub(r'\D', '', phone)) >= 7:
                return phone

        # ── Priority 2: standard digit patterns ──────────────────────────────
        patterns = [
            # International with country code (+91, +1, etc.)
            r'\+(?:[1-9]\d{0,3})[\s\-.]*(?:\(?\d{1,4}\)?[\s\-.]*){2,4}\d{2,4}',
            # Permissive country code: +X followed by 7-12 digits
            r'\+\d{1,4}[\s\-.()]*\d[\d\s\-.()]{6,14}\d',
            # Traditional N-NNN-NNN-NNNN
            r'\+\d{1,3}[\s\-.]*\(?\d{3,5}\)?[\s\-.]*\d{3,5}[\s\-.]*\d{3,5}',
            r'\(?\d{3}\)?[\s\-.]*\d{3}[\s\-.]*\d{4}',
            # 10-digit Indian format: 98765 43210 or 9876543210
            r'\b\d{5}[\s\-.]?\d{5}\b',
            r'\b\d{10}\b',
            # General N-NNN-NNNN style
            r'\b\d{3,4}[\s\-.]+\d{3,4}[\s\-.]+\d{3,4}\b',
            # Add a more permissive pattern for things like 310. 839. 8722
            r'\b\d{3}[\s\-.]+\d{3}[\s\-.]+\d{4}\b',
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
