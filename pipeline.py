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
        # Also grab skills from plain-text detection
        plain_skills_text = plain_sections.get('skills', '')
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
        projects = self.project_parser.parse(projects_raw_text)

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

        # ── Languages ─────────────────────────────────────────────────────
        languages = assembler_result.get('languages', [])
        lang_section_text = assembler_result.get('languages_section', '')
        lang_plain = plain_sections.get('languages', '')
        if not languages:
            languages = self._extract_languages(
                combined_text + '\n' + lang_section_text + '\n' + lang_plain
            )

        # ── Phase 10: Normalized JSON (with tag stripping) ────────────────
        return self._clean_output({
            "personal_info":   personal_info,
            "summary":         summary,
            "skills":          skills,
            "experience":      experience,
            "education":       education,
            "projects":        projects,
            "certifications":  certifications,
            "languages":       languages,
        })

    def _extract_languages(self, text: str) -> List[str]:
        """Find known human languages in text."""
        found = []
        for lang in _KNOWN_LANGUAGES:
            if re.search(r'\b' + re.escape(lang) + r'\b', text, re.I):
                found.append(lang.title())
        return found

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
            # Reject location if it contains the person's name
            if name and name.lower() in loc.lower():
                pi['location'] = None
            # Reject location if it looks like a job title or contains role keywords
            elif re.search(r'(?:Developer|Designer|Engineer|Manager|Associate|Consultant|'
                          r'Analyst|Director|Coordinator|Specialist|Assistant|Lawyer|'
                          r'Marketer|Accountant|Writer|Editor|Nurse|Teacher|Chef|'
                          r'Marketing|SEO|Sales|Recruitment|HR|Finance|Banking|'
                          r'Software|Senior|Junior|Lead|Head|Vice|President|'
                          r'Intern|Trainee|Executive|Officer|Producer|Production)',
                          loc, re.I):
                pi['location'] = None

        return cleaned

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