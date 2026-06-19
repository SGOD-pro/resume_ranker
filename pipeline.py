"""
PDF Extraction Pipeline v3 — Layout-First, No-NER Resume Pipeline
===================================================================
PDF → Layout Analysis → Block Detection → Section Detection →
Field Extraction → Normalized JSON

Final output includes ExtractionResult wrapper:
  document_id, domain, domain_confidence, extraction_strategy,
  page_count, fields, warnings, metadata

The `fields` key contains the normalized resume JSON:
  personal_info, summary, skills, experience, education,
  projects, certifications, languages
"""

import json, sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from layout_extractor   import LayoutAwarePDFExtractor
from block_detector     import BlockDetector
from section_detector   import SectionDetector
from section_parser     import ResumeAssembler
from domain_detector    import DomainDetector
from contact_parser     import ContactParser
from skills_parser      import SkillsParser
from project_parser     import ProjectParser
from experience_parser  import ExperienceParser
from education_parser   import EducationParser as EduParser
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field


# ─────────────────────────────────────────────────────────────────────────────
# ExtractionResult — final output schema
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    """Final output schema — wraps normalized fields with PDF metadata."""
    document_id: str
    domain: str
    domain_confidence: float
    extraction_strategy: str
    page_count: int
    layout_type: str
    fields: Dict[str, Any]
    warnings: List[str]
    metadata: Dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Known human languages for extraction
# ─────────────────────────────────────────────────────────────────────────────

_KNOWN_LANGUAGES = [
    "english", "french", "spanish", "german", "mandarin", "chinese",
    "arabic", "hindi", "portuguese", "russian", "japanese", "italian",
    "korean", "dutch", "swedish", "norwegian", "danish", "polish",
    "turkish", "ukrainian", "bengali", "urdu", "tagalog", "vietnamese",
    "tamil", "telugu", "kannada", "malayalam", "marathi", "gujarati",
    "thai", "indonesian", "malay", "czech", "romanian", "hungarian",
    "greek", "hebrew", "persian", "finnish", "swahili",
]

# Section keywords to filter when searching for names in sidebar tags
_SECTION_KW_FOR_NAME = {
    'profile', 'summary', 'objective', 'experience', 'education', 'skills',
    'projects', 'certifications', 'languages', 'references', 'achievements',
    'employment', 'contact', 'about', 'address', 'phone', 'email', 'linkedin',
    'github', 'resume', 'cv', 'portfolio', 'details', 'links', 'hobbies',
    'interests', 'courses', 'training', 'awards', 'publications',
    'professional', 'academic', 'personal', 'disclaimer', 'declaration',
    'wbbse', 'cbse', 'icse', 'board', 'info', 'information',
    'nationality', 'driving', 'license', 'gender', 'marital', 'religion',
    'date', 'place', 'birth', 'status', 'phone', 'address', 'email',
}


# ─────────────────────────────────────────────────────────────────────────────

class PDFPipelineV3:

    def __init__(self):
        self.layout_extractor = LayoutAwarePDFExtractor()
        self.block_detector   = BlockDetector()
        self.section_detector = SectionDetector()
        self.domain_detector  = DomainDetector()
        self.contact_parser   = ContactParser()
        self.skills_parser    = SkillsParser()
        self.project_parser   = ProjectParser()
        self.experience_parser = ExperienceParser()
        self.edu_parser       = EduParser()
        self.resume_assembler = ResumeAssembler()

    def extract(self, pdf_path: str) -> ExtractionResult:
        """
        Full pipeline: PDF → normalized JSON.
        """
        # ── Step 1: Layout extraction → DocumentStructure ─────────────────
        doc = self.layout_extractor.extract(pdf_path)
        layout_type = doc.layout_type

        # ── Step 2: Block detection ───────────────────────────────────────
        blocks = self.block_detector.detect(doc)

        # ── Step 3: Domain detection ──────────────────────────────────────
        combined_text = doc.full_width_text + '\n' + doc.main_text + '\n' + doc.sidebar_text
        # Clean (cid:XX) artifacts from combined text
        combined_text = re.sub(r'\(cid:\d+\)', '', combined_text)
        domain = self.domain_detector.detect(combined_text)

        # Override: force resume if strong resume structure signals are present
        if domain.domain != 'resume':
            resume_signals = [
                r'\b(?:employment\s+history|work\s+experience|professional\s+experience)\b',
                r'\b(?:education|academic\s+background)\b',
                r'\[NAME\]',
                r'\b(?:career\s+objective|professional\s+summary)\b',
            ]
            signal_count = sum(
                1 for pat in resume_signals
                if re.search(pat, combined_text, re.I)
            )
            if signal_count >= 2:
                domain = type(domain)(
                    domain='resume',
                    confidence=max(domain.confidence, 0.6),
                    signals=domain.signals + ['override:structure_detected']
                )

        # ── Step 4: Section parsing via layout tags ───────────────────────
        main_sections    = self.layout_extractor.parse_sections(doc)
        sidebar_sections = self.layout_extractor.parse_sidebar(doc)

        # ── Step 5: Field extraction ──────────────────────────────────────
        if domain.domain == 'resume':
            fields = self._extract_resume_fields(
                doc, main_sections, sidebar_sections, combined_text
            )
        else:
            # Non-resume: return raw sections
            fields = {
                'main_sections':    main_sections,
                'sidebar_sections': sidebar_sections,
            }

        # ── Step 6: Warnings ──────────────────────────────────────────────
        warnings = self._generate_warnings(fields, domain.domain)

        # ── Step 7: Build ExtractionResult ────────────────────────────────
        page_count = len(set(
            round(l.top / 800) for l in doc.classified_lines
        )) or 1  # estimate page count from y-positions

        return ExtractionResult(
            document_id=os.path.basename(pdf_path),
            domain=domain.domain,
            domain_confidence=domain.confidence,
            extraction_strategy="layout_first_v3",
            page_count=page_count,
            layout_type=layout_type,
            fields=fields,
            warnings=warnings,
            metadata={
                "pdf_path":       pdf_path,
                "domain_signals": domain.signals[:5],
                "layout_type":    layout_type,
                "blocks": {
                    "header_len":  len(blocks.get("header", "")),
                    "sidebar_len": len(blocks.get("sidebar", "")),
                    "main_len":    len(blocks.get("main", "")),
                    "footer":      blocks.get("footer", ""),
                },
            },
        )

    def _extract_resume_fields(
        self,
        doc,
        main_sections: Dict[str, str],
        sidebar_sections: Dict[str, list],
        combined_text: str,
    ) -> Dict[str, Any]:
        """
        Phase 4-10: Extract all resume fields into normalized schema.
        No NER — regex + layout + sections + dictionaries only.

        Two paths:
          A) Tagged text from layout_extractor (two-column, bold headers)
          B) Plain-text fallback via section_detector (single-column, no bold)
        """
        # ── section_parser.ResumeAssembler for tagged-text parsing ────────
        assembler_result = self.resume_assembler.assemble(
            full_width_text  = doc.full_width_text,
            sidebar_sections = sidebar_sections,
            main_sections    = main_sections,
        )

        # ── Detect if assembler found anything useful ─────────────────────
        asm_has_experience = bool(assembler_result.get('employment_history'))
        asm_has_education  = bool(assembler_result.get('education'))
        asm_has_projects   = bool(assembler_result.get('projects_raw_text', '').strip())

        # Plain-text fallback: use section_detector on raw main text
        plain_sections: Dict[str, str] = {}
        if not (asm_has_experience and asm_has_education):
            plain_sections = self.section_detector.detect(doc.main_text)

        # ── Phase 4: Contact (regex-only, no NER) ────────────────────────
        contact = self.contact_parser.parse(
            full_width_text = doc.full_width_text,
            raw_text        = combined_text,
            sidebar_text    = doc.sidebar_text,
            hyperlinks      = getattr(doc, 'hyperlinks', []),
        )
        asm_info = assembler_result.get('personal_info', {})

        # Prefer contact_parser name (it does comma stripping and _NOT_NAMES filtering)
        raw_name = contact.get('name') or asm_info.get('name')

        # Strip any remaining tags from name
        if raw_name:
            raw_name = self._strip_tags(raw_name)

        # Reject name if it's a section header
        from section_detector import resolve_section_name
        if raw_name and resolve_section_name(raw_name):
            raw_name = None

        # Fallback: try first [JOB_TITLE] in main_text that looks like "Name, Title"
        if not raw_name:
            import re as _re
            jt_m = _re.search(r'\[JOB_TITLE\](.*?)\[/JOB_TITLE\]', doc.main_text)
            if jt_m:
                candidate = jt_m.group(1).strip()
                if ',' in candidate:
                    name_part = candidate.split(',')[0].strip()
                    from contact_parser import _is_name_line
                    if _is_name_line(name_part):
                        raw_name = name_part

        # Fallback: detect name from sidebar single-word tags like [EMILY] [DAVIES]
        if not raw_name and doc.sidebar_text:
            # Match single-word alpha-only bracket tags
            name_tags = re.findall(r'\[([A-Za-z]+)\]', doc.sidebar_text)
            # Filter out known section keywords
            name_tags = [t for t in name_tags
                        if t.lower() not in _SECTION_KW_FOR_NAME
                        and len(t) >= 2 and t.isalpha()]
            if len(name_tags) >= 2:
                candidate = ' '.join(t.title() for t in name_tags[:3])
                from contact_parser import _is_name_line
                if _is_name_line(candidate):
                    raw_name = candidate

        # Clean name: strip title suffixes
        if raw_name and ',' in raw_name:
            raw_name = raw_name.split(',')[0].strip()

        # Fallback: try first 2-3 words from first line of main_text
        if not raw_name:
            from contact_parser import _is_name_line
            for text_src in [doc.main_text, doc.sidebar_text]:
                if not text_src:
                    continue
                first_line = self._strip_tags(text_src.split('\n')[0]).strip()
                if not first_line:
                    continue
                words = first_line.split()
                # Try 2 words, then 3 words
                for n in [2, 3]:
                    if len(words) >= n:
                        candidate = ' '.join(words[:n])
                        if _is_name_line(candidate):
                            raw_name = candidate
                            break
                if raw_name:
                    break

        # ── Extract DOB from [PERSONAL INFO] section or full text ─────────
        dob = self._extract_dob(main_sections, combined_text)

        personal_info = {
            "name":     raw_name,
            "email":    contact.get('email') or asm_info.get('email'),
            "phone":    contact.get('phone') or asm_info.get('phone'),
            "linkedin": contact.get('linkedin'),
            "github":   contact.get('github'),
            "location": contact.get('location') or asm_info.get('address'),
            "dob":      dob,
        }
        # Fix: if location looks like a skill list, clear it
        if personal_info.get('location') and any(
            kw in personal_info['location'].lower()
            for kw in ['python', 'java', 'react', 'node', 'django', 'html', 'css']
        ):
            personal_info['location'] = None

        # ── Phase 5: Skills (dictionary matching, no NER) ─────────────────
        skills_section_text = assembler_result.get('skills_section_text', '')
        sidebar_skills = assembler_result.get('skills_raw', [])
        sidebar_skills_text = '\n'.join(sidebar_skills) if sidebar_skills else ''
        # Also grab skills from plain-text detection (strip tags first)
        plain_skills_text = self._strip_tags(plain_sections.get('skills', ''))
        all_skills_text = '\n'.join(filter(None, [
            skills_section_text, sidebar_skills_text, plain_skills_text
        ]))
        skills = self.skills_parser.parse(
            skills_section=all_skills_text,
            full_text=combined_text,
            also_scan_fulltext=True,
        )

        # ── Phase 6: Experience ───────────────────────────────────────────
        if asm_has_experience:
            experience = [
                {
                    "role":         j.get("role"),
                    "company":      j.get("company"),
                    "start":        j.get("start_date"),
                    "end":          j.get("end_date"),
                    "location":     j.get("location"),
                    "description":  j.get("description"),
                    "achievements": j.get("achievements", []),
                }
                for j in assembler_result['employment_history']
            ]
        else:
            # Try DATE-tag experience first (handles [DATE]...role[/DATE] patterns)
            experience = self._parse_date_tag_experience(doc.main_text)
            if not experience:
                exp_text = plain_sections.get('experience', '')
                experience = self.experience_parser.parse(exp_text)

        # ── Experience fallback: parse INTERNSHIP & TRAINING from full_width_text ──
        internship_entries = self._extract_internship_training(doc.full_width_text)
        if internship_entries:
            experience = experience + internship_entries

        # ── Experience fallback 2: parse sidebar text if still empty ──────
        if not experience:
            sidebar_sections_detected = self.section_detector.detect(
                self._strip_tags(doc.sidebar_text))
            exp_text = sidebar_sections_detected.get('experience', '')
            if exp_text:
                experience = self.experience_parser.parse(exp_text)

        # ── Experience fallback 3: pattern-based from main_text ───────────
        if not experience:
            experience = self._extract_experience_by_pattern(
                self._strip_tags(doc.main_text)
            )

        # ── Phase 7: Education ────────────────────────────────────────────
        if asm_has_education:
            education = [
                {
                    "degree":      ' '.join(filter(None, [
                        e.get('degree_type'),
                        ('in ' + e['field_of_study']) if e.get('field_of_study') else None
                    ])) or None,
                    "institution": e.get('institution'),
                    "start":       e.get('start_date'),
                    "end":         e.get('end_date'),
                    "grade":       None,
                }
                for e in assembler_result['education']
            ]
        else:
            edu_text = plain_sections.get('education', '')
            education = self.edu_parser.parse(edu_text)

        # ── Education fallback: parse from sidebar [EDUCATION] section ────
        if not education:
            education = self._parse_sidebar_education(doc.sidebar_text)

        # ── Education fallback 2: parse sidebar text via section_detector ─
        if not education:
            sidebar_sections_detected = self.section_detector.detect(
                self._strip_tags(doc.sidebar_text))
            edu_text = sidebar_sections_detected.get('education', '')
            if edu_text:
                education = self.edu_parser.parse(edu_text)

        # ── Phase 8: Projects ─────────────────────────────────────────────
        if asm_has_projects:
            projects_raw_text = assembler_result['projects_raw_text']
        else:
            projects_raw_text = plain_sections.get('projects', '')
        projects = self.project_parser.parse(
            projects_raw_text,
            hyperlinks=getattr(doc, 'hyperlinks', [])
        )

        # ── Summary ───────────────────────────────────────────────────────
        summary = assembler_result.get('profile')
        if not summary:
            summary = plain_sections.get('summary')

        # ── Certifications ────────────────────────────────────────────────
        courses_raw = assembler_result.get('courses', [])
        certifications = [
            {"name": c.get('name', ''), "issuer": c.get('issuer'), "date": c.get('start_date')}
            for c in (courses_raw or [])
        ] if courses_raw else []

        # Fallback: parse from plain-text section detection
        if not certifications:
            cert_text = plain_sections.get('certifications', '')
            if cert_text:
                certifications = self._parse_certifications_text(cert_text)

        # ── Languages ─────────────────────────────────────────────────────
        languages = assembler_result.get('languages', [])
        lang_section_text = assembler_result.get('languages_section', '')
        lang_plain = plain_sections.get('languages', '')
        if not languages:
            languages = self._extract_languages(
                combined_text + '\n' + lang_section_text + '\n' + lang_plain
            )

        # ── Build raw text fallback for ranking ────────────────────────────
        raw_text_sections = self._build_raw_fallback(
            plain_sections, combined_text, doc.sidebar_text)

        # ── Compute extraction quality score ───────────────────────────────
        extraction_quality = self._compute_quality(
            personal_info, skills, experience, education)

        # ── Phase 10: Normalized JSON (with tag stripping) ────────────────
        return self._clean_output({
            "personal_info":     personal_info,
            "summary":           summary,
            "skills":            skills,
            "experience":        experience,
            "education":         education,
            "projects":          projects,
            "certifications":    certifications,
            "languages":         languages,
            "raw_text_sections": raw_text_sections,
            "extraction_quality": extraction_quality,
        })

    def _extract_languages(self, text: str) -> List[str]:
        """Find known human languages in text."""
        found = []
        for lang in _KNOWN_LANGUAGES:
            if re.search(r'\b' + re.escape(lang) + r'\b', text, re.I):
                found.append(lang.title())
        return found

    def _parse_certifications_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse certifications from plain-text section content."""
        certs = []
        # Split by bullet markers or newlines
        lines = re.split(r'\n|[•·▪▸►✓✔]', text)
        for line in lines:
            line = line.strip().lstrip('-* ').strip()
            if not line or len(line) < 5:
                continue
            # Skip pure dates or numbers
            if re.match(r'^[\d\s/\-.]+$', line):
                continue
            # Try to split "Name - Issuer" or "Name, Issuer"
            name, issuer = line, None
            for sep in [' - ', ' – ', ' — ', ', ']:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts[0]) > 5 and len(parts[1]) > 2:
                        name = parts[0].strip()
                        issuer = parts[1].strip()
                        break
            certs.append({"name": name, "issuer": issuer, "date": None})
        return certs

    @staticmethod
    def _clean_text_for_ranking(text: str) -> str:
        """Clean text for ranking fallback: remove tags, emojis, special chars."""
        if not text:
            return ''
        # Remove tags like [SECTION], [/SECTION]
        text = re.sub(r'\[/?[A-Z_]+\]', '', text)
        # Remove (cid:XX) artifacts
        text = re.sub(r'\(cid:\d+\)', '', text)
        # Remove emojis and non-ASCII special chars (keep basic accented letters)
        text = re.sub(r'[^\x20-\x7E\n\t]', ' ', text)
        # Remove excessive special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,;:!?\-\'\"()/&@#+%]', ' ', text)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _build_raw_fallback(self, plain_sections: Dict[str, str],
                            combined_text: str, sidebar_text: str) -> Dict[str, str]:
        """Build cleaned raw text sections for ranking fallback.
        This ensures even poorly-structured PDFs contribute keywords for TF-IDF."""
        raw = {}
        for section_name in ['summary', 'skills', 'experience', 'education',
                             'projects', 'certifications', 'languages']:
            text = plain_sections.get(section_name, '')
            if text:
                raw[section_name] = self._clean_text_for_ranking(text)

        # Always include full cleaned text for TF-IDF fallback
        full = self._clean_text_for_ranking(combined_text)
        if sidebar_text:
            full += '\n' + self._clean_text_for_ranking(sidebar_text)
        raw['full_text'] = full

        return raw

    @staticmethod
    def _compute_quality(personal_info: dict, skills: list,
                         experience: list, education: list) -> float:
        """Compute extraction quality score (0.0 to 1.0).
        Higher = more structured data was successfully extracted.
        Used by ranker to decide how much to weight structured vs raw text."""
        score = 0.0
        total = 6.0

        # Name (most basic field)
        if personal_info.get('name'):
            score += 1.0

        # Email
        if personal_info.get('email'):
            score += 1.0

        # Skills (critical for ranking)
        if skills and len(skills) >= 3:
            score += 1.0
        elif skills:
            score += 0.5

        # Experience
        if experience and len(experience) >= 1:
            # Check quality: at least one entry has both role and company
            good = any(e.get('role') and e.get('company') for e in experience)
            score += 1.0 if good else 0.5

        # Education
        if education and len(education) >= 1:
            good = any(e.get('degree') and e.get('institution') for e in education)
            score += 1.0 if good else 0.5

        # Location or phone (supporting info)
        if personal_info.get('location') or personal_info.get('phone'):
            score += 1.0

        return round(score / total, 2)

    def _extract_dob(self, main_sections: Dict[str, str], combined_text: str) -> Optional[str]:
        """
        Extract Date of Birth from:
          1. [PERSONAL INFO] tagged section (e.g., "• Date of Birth : 14th October, 2003")
          2. Full text fallback
        """
        # Check tagged sections for PERSONAL INFO
        for key in ('PERSONAL INFO', 'PERSONAL INFORMATION', 'PERSONAL DETAILS'):
            section_text = main_sections.get(key, '')
            if section_text:
                dob = self._find_dob_in_text(section_text)
                if dob:
                    return dob

        # Fallback: scan combined text
        return self._find_dob_in_text(combined_text)

    def _find_dob_in_text(self, text: str) -> Optional[str]:
        """Find DOB pattern in text."""
        # Pattern: "Date of Birth : 14th October, 2003" or "DOB: 1989/20/03" or "D.O.B: ..."
        dob_patterns = [
            # "Date of Birth : 14th October, 2003"
            r'(?:date\s+of\s+birth|d\.?o\.?b\.?|dob)\s*[:\-]\s*(.+?)(?:\n|$)',
            # "Born: 14 Oct 2003" or "Born on 14/10/2003"
            r'(?:born\s+(?:on)?)\s*[:\-]?\s*(.+?)(?:\n|$)',
        ]
        for pat in dob_patterns:
            m = re.search(pat, text, re.I)
            if m:
                dob_raw = m.group(1).strip()
                # Clean: remove bullet chars, trailing punctuation
                dob_raw = re.sub(r'^[•·▪\-\*]\s*', '', dob_raw)
                dob_raw = re.sub(r'\[/?[A-Z_]+\]', '', dob_raw).strip()
                # Remove trailing section content after the date
                # e.g., "14th October, 2003[/BULLET]" or "14th October, 2003 Gender"
                dob_raw = re.split(r'\s*(?:gender|marital|religion|nationality|place)',
                                   dob_raw, flags=re.I)[0].strip()
                if dob_raw and len(dob_raw) > 4:
                    return dob_raw
        return None

    def _extract_internship_training(self, full_width_text: str) -> List[Dict[str, Any]]:
        """
        Parse internship & training entries from full_width_text.
        These appear as [NAME]INTERNSHIP & TRAINING[/NAME] followed by
        [TITLE]• description (duration)[/TITLE] lines.
        """
        entries = []
        # Find INTERNSHIP & TRAINING section in full_width_text
        # Patterns: [NAME]INTERNSHIP & TRAINING[/NAME], [NAME]INTERNSHIP[/NAME],
        #           [NAME]TRAINING[/NAME], [JOB_TITLE]Internship[/JOB_TITLE]
        internship_re = re.compile(
            r'\[NAME\]\s*(INTERNSHIP\s*(?:&|AND)?\s*TRAINING|INTERNSHIP|TRAINING)\s*\[/NAME\]',
            re.I
        )
        m = internship_re.search(full_width_text)
        if not m:
            # Also check for JOB_TITLE tag
            internship_re2 = re.compile(
                r'\[JOB_TITLE\]\s*(Internship\s*(?:&|And)?\s*Training|Internship|Training)\s*\[/JOB_TITLE\]',
                re.I
            )
            m = internship_re2.search(full_width_text)

        if not m:
            return []

        # Get text after the internship header
        after_text = full_width_text[m.end():]

        # Find all [TITLE]...[/TITLE] lines until the next [NAME] section
        next_name = re.search(r'\[NAME\]', after_text)
        if next_name:
            section_text = after_text[:next_name.start()]
        else:
            section_text = after_text

        # Parse bullet items from TITLE tags
        title_items = re.findall(r'\[TITLE\](.*?)\[/TITLE\]', section_text, re.DOTALL)
        if not title_items:
            # Fallback: plain text bullets (only if no TITLE tags found)
            title_items = re.findall(r'[•·▪\-\*]\s*(.+)', section_text)

        all_items = title_items

        for item in all_items:
            clean = re.sub(r'^[•·▪\-\*]\s*', '', item).strip()
            if not clean:
                continue

            # Try to extract duration: "(2 months)", "(6 weeks)", "(Jan 2023 - Mar 2023)"
            duration_m = re.search(r'\(([^)]+)\)\s*$', clean)
            duration = duration_m.group(1) if duration_m else None
            description = re.sub(r'\([^)]+\)\s*$', '', clean).strip() if duration_m else clean

            entries.append({
                "role":         "Intern" if 'internship' in m.group(1).lower() else "Trainee",
                "company":      None,
                "start":        None,
                "end":          None,
                "location":     None,
                "description":  description,
                "achievements": [],
                "duration":     duration,
                "type":         "internship" if 'internship' in m.group(1).lower() else "training",
            })

        return entries

    def _parse_sidebar_education(self, sidebar_text: str) -> List[Dict[str, Any]]:
        """
        Parse education from raw sidebar text.
        Handles formats like:
          MBA: DIATM, MAKAUT (PURSUING)
          BCA: MID, MAKAUT
          CGPA: 7.0
          Class 12th: RANIGANJ HIGH SCHOOL, [WBBSE]
          GPA: 81%
        Parses raw text instead of dict to avoid losing data at [WBBSE] boundaries.
        """
        if not sidebar_text or not sidebar_text.strip():
            return []

        # Find education section in raw sidebar text
        edu_start = re.search(r'\[EDUCATION\]', sidebar_text, re.I)
        if not edu_start:
            return []

        # Find the end: next section tag that isn't WBBSE/CBSE/ICSE (board tags are part of education)
        after = sidebar_text[edu_start.end():]
        end_m = re.search(r'\[(SKILLS|LANGUAGES|HOBBIES|INTERESTS|LINKS|CONTACT|CERTIFICATIONS)\]',
                          after, re.I)
        if end_m:
            all_edu_text = after[:end_m.start()]
        else:
            all_edu_text = after

        # Strip board tags — they're just labels within education, not section boundaries
        all_edu_text = re.sub(r'\[/?(?:WBBSE|CBSE|ICSE|ISC|BOARD)\]', '', all_edu_text)

        entries = []
        lines = [l.strip() for l in all_edu_text.split('\n') if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]

            # Pattern: "MBA: DIATM, MAKAUT (PURSUING)" or "BCA: MID, MAKAUT"
            degree_inst_m = re.match(
                r'^(MBA|BCA|B\.?Tech|M\.?Tech|B\.?Sc|M\.?Sc|B\.?Com|M\.?Com|'
                r'B\.?A|M\.?A|B\.?E|M\.?E|Ph\.?D|Diploma|Certificate)\s*:\s*(.+)',
                line, re.I
            )
            if degree_inst_m:
                degree = degree_inst_m.group(1).strip()
                institution = degree_inst_m.group(2).strip()
                # Check for (PURSUING) marker
                pursuing = '(pursuing)' in institution.lower()
                institution = re.sub(r'\s*\(pursuing\)', '', institution, flags=re.I).strip()

                # Look ahead for CGPA/GPA
                grade = None
                if i + 1 < len(lines):
                    grade_m = re.match(r'(?:CGPA|GPA|Grade|Percentage|Score)[:\s]*([\d.]+%?)',
                                       lines[i + 1], re.I)
                    if grade_m:
                        grade = grade_m.group(1)
                        i += 1  # skip grade line

                entries.append({
                    "degree":      degree + (" (Pursuing)" if pursuing else ""),
                    "institution": institution,
                    "start":       None,
                    "end":         "Present" if pursuing else None,
                    "grade":       grade,
                })
                i += 1
                continue

            # Pattern: "Class 12th:" or "Class 10th:" or "12th Standard"
            class_m = re.match(
                r'^(?:Class\s+)?(10th|12th|X|XII|10|12)(?:\s*(?:Standard|Class))?\s*:?\s*(.*)',
                line, re.I
            )
            if class_m:
                class_name = class_m.group(1)
                rest = class_m.group(2).strip()

                # Institution might be on the same line or next line
                institution = rest or None
                if not institution and i + 1 < len(lines):
                    # Next line might be the school name
                    next_line = lines[i + 1].rstrip(',').strip()
                    if not re.match(r'(?:GPA|CGPA|Grade|Percentage|Score)', next_line, re.I):
                        institution = next_line
                        i += 1

                # Look ahead for board (WBBSE, CBSE, etc.)
                if i + 1 < len(lines):
                    board_line = lines[i + 1].strip()
                    if board_line.upper() in ('WBBSE', 'CBSE', 'ICSE', 'ISC', 'STATE BOARD'):
                        if institution:
                            institution += f", {board_line}"
                        else:
                            institution = board_line
                        i += 1

                # Look ahead for GPA/percentage
                grade = None
                if i + 1 < len(lines):
                    grade_m = re.match(r'(?:GPA|CGPA|Grade|Percentage|Score)[:\s]*([\d.]+%?)',
                                       lines[i + 1], re.I)
                    if grade_m:
                        grade = grade_m.group(1)
                        i += 1

                entries.append({
                    "degree":      f"Class {class_name}",
                    "institution": institution,
                    "start":       None,
                    "end":         None,
                    "grade":       grade,
                })
                i += 1
                continue

            i += 1

        return entries

    def _parse_date_tag_experience(self, text: str) -> List[Dict[str, Any]]:
        """Parse experience from [DATE]...role[/DATE] patterns in raw text.
        Example: [DATE]Jan 2025 - Present Senior Retail Assistant / Floor Supervisor[/DATE]
        Next line: Macy's, Chicago, IL
        """
        if not text:
            return []

        # Find all [DATE]...[/DATE] blocks that contain a role after the date range
        date_tag_re = re.compile(
            r'\[DATE\]'
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})'
            r'\s*[-–—]+\s*'
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|\d{4})'
            r'\s+'
            r'(.+?)'
            r'\[/DATE\]',
            re.I
        )

        entries = []
        lines = text.split('\n')
        text_joined = text  # keep original for regex matching

        for m in date_tag_re.finditer(text_joined):
            start = m.group(1).strip()
            end = m.group(2).strip()
            role = m.group(3).strip()

            # Find the line after the [DATE] tag to get company
            match_end_pos = m.end()
            after_text = text_joined[match_end_pos:match_end_pos + 200]
            after_lines = [l.strip() for l in after_text.split('\n') if l.strip()]

            company = None
            description_lines = []
            achievements = []

            for i, line in enumerate(after_lines):
                if i == 0:
                    # First non-empty line after DATE tag = company
                    company = line.rstrip(',').strip()
                elif line.startswith(('•', '-', '*', '·')):
                    achievements.append(re.sub(r'^[•·*\-]\s*', '', line).strip())
                elif re.match(r'\[DATE\]', line):
                    break  # Next experience entry
                elif not achievements:
                    description_lines.append(line)

            if role:
                entries.append({
                    "role": role,
                    "company": company,
                    "start": start,
                    "end": end,
                    "description": ' '.join(description_lines).strip() or None,
                    "achievements": achievements,
                })

        return entries

    def _extract_experience_by_pattern(self, text: str) -> List[Dict[str, Any]]:
        """
        Pattern-based experience extraction for resumes without section headers.
        Looks for: Role [at|,] Company, Location\\nDATE_RANGE\\n bullets
        """
        if not text:
            return []

        entries = []
        lines = text.split('\n')

        # Date pattern: "January 2020 — February 2022" or "Jan 2020 - Present"
        date_re = re.compile(
            r'(?:(?:January|February|March|April|May|June|July|August|September|'
            r'October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'\s+\d{4})\s*[—–\-]+\s*'
            r'(?:(?:January|February|March|April|May|June|July|August|September|'
            r'October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
            r'\s+\d{4}|Present|Current)',
            re.I
        )

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Check if this line or the next line has a date range
            date_match = None
            date_line_idx = None

            # Check current line for embedded date
            dm = date_re.search(line)
            if dm:
                date_match = dm.group(0)
                date_line_idx = i
            # Check next line for date
            elif i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                dm2 = date_re.search(next_line)
                if dm2:
                    date_match = dm2.group(0)
                    date_line_idx = i + 1

            if not date_match:
                i += 1
                continue

            # Parse the date range
            parts = re.split(r'\s*[—–\-]+\s*', date_match, maxsplit=1)
            start_date = parts[0].strip() if len(parts) > 0 else None
            end_date = parts[1].strip() if len(parts) > 1 else None

            # The role/company line
            role_line = line if date_line_idx == i + 1 else line.replace(date_match, '').strip()
            role_line = date_re.sub('', role_line).strip().rstrip(',').strip()

            # Parse role and company
            role, company, location = None, None, None
            at_match = re.match(r'^(.+?)\s+at\s+(.+?)(?:,\s*(.+))?$', role_line, re.I)
            if at_match:
                role = at_match.group(1).strip()
                company = at_match.group(2).strip()
                location = at_match.group(3).strip() if at_match.group(3) else None
            elif ',' in role_line:
                role_parts = [p.strip() for p in role_line.split(',')]
                role = role_parts[0]
                company = role_parts[1] if len(role_parts) > 1 else None
                location = role_parts[2] if len(role_parts) > 2 else None
            else:
                role = role_line

            # Collect description bullets
            desc_lines = []
            j = (date_line_idx or i) + 1
            while j < len(lines):
                bl = lines[j].strip()
                if not bl:
                    j += 1
                    continue
                if date_re.search(bl):
                    break
                if (not bl.startswith(('•', '-', '·', '*', '–', '►'))
                        and re.match(r'^[A-Z][a-z].*(?:at|,)\s+[A-Z]', bl)):
                    break
                desc_lines.append(re.sub(r'^[•\-·▪►✓✔\*]\s*', '', bl))
                j += 1

            description = ' '.join(desc_lines).strip() if desc_lines else None

            entries.append({
                "role": role,
                "company": company,
                "start": start_date,
                "end": end_date,
                "location": location,
                "description": description,
                "achievements": [],
            })

            i = j

        return entries

    @staticmethod
    def _strip_tags(text: str) -> str:
        """Remove all [TAG]...[/TAG] markup from text, keeping inner content."""
        if not text:
            return text
        # Remove closing tags: [/NAME], [/TITLE], [/BULLET], [/DATE], etc.
        text = re.sub(r'\[/[A-Z_]+\]', '', text)
        # Remove opening tags: [NAME], [TITLE], [BULLET], [DATE], [JOB_TITLE], [EDU_LINE], etc.
        text = re.sub(r'\[[A-Z][A-Z_]*\]', '', text)
        # Remove mixed-case section tags: [Employment History], [PROFILE], [PERSONAL INFO]
        text = re.sub(r'\[[A-Z][A-Za-z\s&]+\]', '', text)
        return text.strip()

    def _clean_output(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively strip tags from all string values and fix bad values."""
        cleaned = self._recursive_strip(fields)

        # Fix location: reject if it contains the person's name or job title patterns
        pi = cleaned.get('personal_info', {})
        loc = pi.get('location')
        name = pi.get('name', '') or ''
        if loc:
            if name and name.lower() in loc.lower():
                pi['location'] = None
            elif re.search(r'(?:Developer|Designer|Engineer|Manager|Associate|Consultant|'
                          r'Analyst|Director|Coordinator|Specialist|Assistant|Lawyer|'
                          r'Marketer|Accountant|Writer|Editor|Nurse|Teacher|Chef|'
                          r'Marketing|SEO|Sales|Recruitment|HR|Finance|Banking|'
                          r'Software|Senior|Junior|Lead|Head|Vice|President|'
                          r'Intern|Trainee|Executive|Officer|Producer|Production)',
                          loc, re.I):
                pi['location'] = None

        # ── Fix experience entries ──────────────────────────────────────
        cleaned['experience'] = self._fix_experience(cleaned.get('experience', []))

        # ── Fix education entries ───────────────────────────────────────
        cleaned['education'] = self._fix_education(cleaned.get('education', []))

        # ── Fix certifications ──────────────────────────────────────────
        cleaned['certifications'] = self._fix_certifications(
            cleaned.get('certifications', []))

        # ── Fix skills: remove garbled entries ──────────────────────────
        cleaned['skills'] = self._fix_skills(cleaned.get('skills', []))

        # ── Fix summary: remove noise from start ────────────────────────
        cleaned['summary'] = self._fix_summary(cleaned.get('summary'))

        return cleaned

    @staticmethod
    def _fix_summary(summary: Optional[str]) -> Optional[str]:
        """Remove noise from the beginning of summary text."""
        if not summary:
            return None
        # Remove leading lines that are location/metadata noise
        lines = summary.split('\n')
        clean_lines = []
        started = False
        for line in lines:
            stripped = line.strip()
            # Skip leading noise lines
            if not started:
                if re.match(r'^(?:Place\s+of\s+birth|Nationality|Driving\s+license|'
                           r'Date\s+of\s+birth|Gender|Marital|Address|\d{4}/)',
                           stripped, re.I):
                    continue
                if stripped and len(stripped) > 15:
                    started = True
            if started:
                clean_lines.append(line)
        result = '\n'.join(clean_lines).strip()
        return result if result else None

    @staticmethod
    def _fix_skills(skills: list) -> list:
        """Remove garbled or invalid skills."""
        _VALID_SINGLE = {'C', 'R'}  # Known single-char programming languages
        # Non-skill words that leak from section headers
        _NON_SKILLS = {
            'hobbies', 'interests', 'activities', 'references',
            'languages', 'details', 'profile', 'summary',
            'objective', 'declaration', 'disclaimer',
        }
        fixed = []
        for sk in skills:
            # Must be string
            if not isinstance(sk, str):
                continue
            sk = sk.strip()

            # Skip empty
            if not sk:
                continue

            # Skip single-char unless it's a known language
            if len(sk) == 1 and sk not in _VALID_SINGLE:
                continue

            # Skip non-skill words
            if sk.lower() in _NON_SKILLS:
                continue

            # Skip if contains non-printable or garbled chars
            if re.search(r'[^\x20-\x7E]', sk):
                continue

            # Skip if mostly special chars (garbled text)
            alpha_count = sum(1 for c in sk if c.isalpha())
            if alpha_count < len(sk) * 0.4:
                continue

            # Skip very short multi-char skills that aren't valid
            if len(sk) <= 3 and sk not in _VALID_SINGLE and sk not in {
                'AI', 'CI', 'CD', 'ML', 'NLP', 'AWS', 'GCP', 'SQL', 'PHP',
                'CSS', 'C++', 'C#', 'Go', 'UX', 'UI', 'API', 'ETL', 'SEM',
                'SEO', 'CAD', 'ERP', 'SAP', 'GIS', 'RPA', 'IoT', 'VPN',
                'TCP', 'DNS', 'SSH', 'Git', 'SVN', 'VBA', '5S', 'CPR',
            }:
                continue

            # Skip skills starting with special chars (garbled)
            if sk[0] in ('+', '=', '*', '/', '\\', '<', '>', '~', '`'):
                continue

            # Skip cipher-font garbled text detection
            if len(sk) > 4:
                words = sk.split()

                # Multi-word skill starting with lowercase = likely garbled
                if len(words) > 1 and sk[0].islower():
                    continue

                # Digits at start of word (not tech versions) e.g., "9ogdegd"
                if re.search(r'\b\d[a-zA-Z]{2,}', sk):
                    continue

                # Digits mixed into word body e.g., "E39omm"
                if re.search(r'[a-zA-Z]\d[a-zA-Z]', sk) and not re.match(
                    r'^[A-Z][a-z]*\d+$', sk):
                    continue

                # High uppercase ratio in multi-word strings
                upper_count = sum(1 for c in sk if c.isupper())
                if len(words) > 1 and upper_count > len(sk) * 0.35:
                    if not re.match(r'^[A-Z]{2,5}(\s|$)', sk):
                        continue

                # Parentheses in multi-word skill name (garbled text)
                if '(' in sk and len(words) > 1:
                    continue

                # Unusual consonant clusters that don't appear in English
                # e.g., "dFa", "gCe", "pgl", "tneF"
                if re.search(r'[bcdfghjklmnpqrstvwxyz]{4,}', sk, re.I):
                    continue

            # Two-word skill where first word is lowercase and very short
            # e.g., 'es E' — garbled fragment
            if len(sk) <= 5 and ' ' in sk and sk[0].islower():
                continue

            fixed.append(sk)
        return fixed

    def _fix_experience(self, entries: list) -> list:
        """Clean up experience entries: split 'Role at Company, City' patterns,
        fix empty roles/companies, clean bullet markers."""
        fixed = []
        for exp in entries:
            role = (exp.get('role') or '').strip()
            company = (exp.get('company') or '').strip()

            # Fix: company starts with bullet marker or description text
            company = re.sub(r'^[•·▪▸►✓✔*\-]\s*', '', company)

            # Fix: company is actually a description (starts with verb phrase)
            if company and re.match(r'^(?:onboarding|reducing|improving|managing|'
                                    r'assisted|supervised|maintaining|developed|'
                                    r'implemented|responsible|maintained|provided|'
                                    r'operated|organized|coordinated|resolved|'
                                    r'requirements|performed|facilitated)', company, re.I):
                if not exp.get('description'):
                    exp['description'] = company
                company = ''

            # Fix: "Role at Company, City" in the role field
            if role and not company:
                m = re.match(r'^(.+?)\s+at\s+(.+)$', role, re.I)
                if m:
                    role = m.group(1).strip()
                    company = m.group(2).strip()

            # Fix: "Role, Company, City" all in role (with comma separators)
            if role and not company and role.count(',') >= 1:
                parts = [p.strip() for p in role.split(',')]
                if len(parts) >= 2:
                    role = parts[0]
                    company = ', '.join(parts[1:])

            # Fix: "Role at Company, City" in the company field (role is empty)
            if not role and company:
                m = re.match(r'^(.+?)\s+at\s+(.+)$', company, re.I)
                if m:
                    role = m.group(1).strip()
                    company = m.group(2).strip()

            # Fix: company is too long (likely includes description)
            if company and len(company) > 80:
                cut = re.search(r'[.\n]', company)
                if cut:
                    company = company[:cut.start()].strip()

            # Skip entries that look like education, not experience
            if role and re.search(r'\b(?:Bachelor|Master|Associate|Diploma|Certificate'
                                  r'|B\.?S\.?C|M\.?S\.?C|B\.?A\.?|M\.?A\.?|Ph\.?D'
                                  r'|Hospitality\s*&|Tourism\s+Management)\b',
                                  role, re.I):
                continue

            # Skip entries that look like certifications, not experience
            if role and re.search(r'\b(?:Certified\s+Expert|Certification|Licensed)\b',
                                  role, re.I):
                continue

            # Skip entries that look like language courses
            if role and re.match(r'^(?:Spanish|French|German|Italian|Mandarin|Chinese|'
                                r'Portuguese|Russian|Japanese|Korean|Arabic|Hindi'
                                r')(?:\s+and\s+\w+)?$', role, re.I):
                continue

            # Skip entries with garbled/ALL-CAPS city names as role (no real job title)
            if role and role.isupper() and len(role.split()) == 1 and not company:
                continue

            # Skip entries that look like just a place name (no job title words)
            # e.g., 'San Jacinto' with no company
            if role and not company and len(role.split()) <= 2:
                has_job_word = re.search(
                    r'(?:Engineer|Developer|Designer|Manager|Analyst|Consultant|'
                    r'Assistant|Associate|Director|Specialist|Coordinator|Agent|'
                    r'Guard|Teacher|Trainer|Nurse|Chef|Writer|Editor|Intern|'
                    r'Officer|Administrator|Supervisor|Operator|Technician|'
                    r'Marketer|Accountant|Lawyer|Programmer)', role, re.I)
                if not has_job_word:
                    continue

            # Clean up: strip trailing commas, periods
            role = role.rstrip(',.').strip() if role else None
            company = company.rstrip(',.').strip() if company else None

            exp['role'] = role or None
            exp['company'] = company or None

            # Only keep entries that have at least role or company
            if role or company:
                fixed.append(exp)
        return fixed

    def _fix_education(self, entries: list) -> list:
        """Clean up education entries: fix garbled degrees, remove prefixes,
        fix degree/institution swaps."""
        fixed = []
        seen = set()
        for edu in entries:
            degree = (edu.get('degree') or '').strip()
            institution = (edu.get('institution') or '').strip()

            # Fix: "Bachelor in 's Degree" → "Bachelor's Degree"
            degree = re.sub(r"(\w+)\s+in\s+'s\s+Degree", r"\1's Degree", degree)

            # Fix: "Master in 's Degree in ..." → "Master's Degree in ..."
            degree = re.sub(r"(\w+)\s+in\s+'s\s+", r"\1's ", degree)

            # Fix: "Degree: Bachelor's Degree" → "Bachelor's Degree"
            degree = re.sub(r'^Degree:\s*', '', degree, flags=re.I)

            # Fix: truncated "ravel and Tourism" → "Travel and Tourism"
            if degree.startswith('ravel'):
                degree = 'T' + degree

            # Fix: degree starts with year prefix "2015 – Advanced Course..."
            degree = re.sub(r'^\d{4}\s*[–—\-]\s*', '', degree).strip()

            # Fix: degree field has multiple comma-separated items
            # e.g. "Security Guard Certificate Program (SOCP), ASIS International, North Naples"
            if degree and ',' in degree and not institution:
                parts = [p.strip() for p in degree.split(',')]
                if re.search(r'(?:Certificate|Degree|Diploma|Training|Program|BA|BS|MA|MS)',
                            parts[0], re.I):
                    degree = parts[0]
                    institution = ', '.join(parts[1:])

            # Fix: degree has institution embedded (multiple items with commas)
            if degree and institution and ',' in degree:
                parts = [p.strip() for p in degree.split(',')]
                if len(parts) >= 2 and re.search(
                    r'(?:University|College|School|Institute|Academy|International)',
                    degree, re.I):
                    deg_parts = []
                    inst_parts = []
                    for p in parts:
                        if re.search(r'(?:University|College|School|Institute|Academy|'
                                    r'International)', p, re.I):
                            inst_parts.append(p)
                        else:
                            deg_parts.append(p)
                    if deg_parts:
                        degree = ', '.join(deg_parts)
                    if inst_parts:
                        institution = ', '.join(inst_parts) + (', ' + institution if institution else '')

            # Fix: institution has degree embedded (swap detection)
            if institution and not degree:
                if re.search(r'(?:Certificate|Degree|Diploma|Course|Training|Bachelor|Master)',
                            institution, re.I):
                    degree = institution
                    institution = None

            # Fix: institution contains year prefixes like "2015 –"
            institution = re.sub(r'^\d{4}\s*[–—\-]\s*', '', institution).strip() if institution else ''

            # Clean brackets/tags from institution
            institution = re.sub(r'\[/?[A-Z_]+\]', '', institution).strip() if institution else ''

            # Dedup key: normalize by stripping year prefixes and lowercasing
            norm_deg = re.sub(r'^\d{4}\s*[–—\-]\s*', '', degree).strip().lower()
            norm_inst = institution.lower() if institution else ''
            key = (norm_deg, norm_inst)
            if key in seen:
                continue
            seen.add(key)

            edu['degree'] = degree or None
            edu['institution'] = institution or None

            if degree or institution:
                fixed.append(edu)
        return fixed

    def _fix_certifications(self, entries: list) -> list:
        """Clean up certifications: remove noise, limit count, clean special chars."""
        fixed = []
        # Patterns that indicate this is an achievement/description, not a cert
        _noise_re = re.compile(
            r'(?:theft|reduced|improved|managed|responsible|ensuring|'
            r'improving|installed|detection|monitoring|procedures|'
            r'techniques|introduced|inventive|entrance|exit|building|'
            r'announcement|notification|declined|employees?|'
            r'vigilance|strategies|aisles|storerooms|scanning|'
            r'cameras|having \d|turnover|onboarding)\s', re.I)
        for cert in entries:
            name = (cert.get('name') or '').strip()

            # Skip very short or obviously wrong entries
            if len(name) < 5:
                continue

            # Skip entries that are just dates like "May 2011"
            if re.match(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}$', name, re.I):
                continue

            # Skip entries that look like experience descriptions, not certs
            if _noise_re.search(name):
                continue

            # Skip if starts with a lowercase word (achievement text)
            if name[0].islower():
                continue

            # Skip garbled/cipher-font encoded cert names
            # e.g., "CertiPcate in Hootsuite Social Marketing Udemy Online MaJ U2U2"
            if re.search(r'[a-zA-Z]\d[a-zA-Z]', name) or \
               re.search(r'\b\d[a-zA-Z]{2,}', name) or \
               re.search(r'[A-Z]{2,}[a-z][A-Z]', name):
                continue

            # Clean garbled characters (cid artifacts already cleaned)
            name = re.sub(r'[^\w\s\-&/+.#(),:\'\"]', '', name).strip()

            # Truncate overly long cert names
            if len(name) > 120:
                cut = name.find('•')
                if cut > 10:
                    name = name[:cut].strip()
                else:
                    name = name[:120].strip()

            if len(name) >= 5:
                cert['name'] = name
                fixed.append(cert)
        return fixed

    def _recursive_strip(self, obj):
        """Recursively strip tags from strings in dict/list structures."""
        if isinstance(obj, str):
            return self._strip_tags(obj)
        elif isinstance(obj, dict):
            return {k: self._recursive_strip(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._recursive_strip(item) for item in obj]
        return obj

    def _generate_warnings(self, fields: Dict, domain: str) -> List[str]:
        warnings = []
        if domain == 'resume':
            pi = fields.get('personal_info', {})
            if not pi.get('name'):
                warnings.append("Could not extract name — check PDF formatting")
            if not pi.get('email'):
                warnings.append("No email found")
            if not fields.get('experience'):
                warnings.append("No experience entries found")
            if not fields.get('skills'):
                warnings.append("No skills detected")
            if not fields.get('projects'):
                warnings.append("No projects section found (developer resumes should have this)")
        return warnings


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    pdf  = sys.argv[1] if len(sys.argv) > 1 else 'resume/souvik.pdf'
    show = sys.argv[2] if len(sys.argv) > 2 else 'all'

    p      = PDFPipelineV3()
    result = p.extract(pdf)

    if show == 'fields':
        print(json.dumps(result.fields, indent=2, ensure_ascii=False, default=str))
    elif show == 'raw':
        print(json.dumps(result.metadata, indent=2, ensure_ascii=False, default=str))
    else:
        out = asdict(result)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))