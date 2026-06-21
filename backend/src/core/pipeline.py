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

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

# ── Extractor imports (relocated to src/extractors/) ──────────────────────
from src.extractors.layout.layout_extractor import LayoutAwarePDFExtractor
from src.extractors.layout.block_detector   import BlockDetector
from src.extractors.layout.section_detector import SectionDetector
from src.extractors.layout.section_parser   import ResumeAssembler
from src.extractors.layout.domain_detector  import DomainDetector
from src.extractors.contact.contact_parser  import ContactParser
from src.extractors.skills.skills_parser    import SkillsParser
from src.extractors.projects.project_parser import ProjectParser
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.education.education_parser   import EducationParser as EduParser

# ── Core modules ──────────────────────────────────────────────────────────
from src.core.quality_scoring import (
    compute_quality,
    compute_text_quality,
    compute_semantic_quality,
    remove_duplicate_blocks,
)
from src.core.output_cleaning import (
    strip_tags,
    clean_text_for_ranking,
    recursive_strip,
)

# ── Schemas ───────────────────────────────────────────────────────────────
from src.schemas.extraction import ExtractionResult, SectionContent



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

        # Build section blocks for structured section analysis
        doc.build_section_blocks()

        # ── Step 3: Text quality + dedup ──────────────────────────────────
        combined_text = doc.full_width_text + '\n' + doc.main_text + '\n' + doc.sidebar_text
        # Clean (cid:XX) artifacts from combined text
        combined_text = re.sub(r'\(cid:\d+\)', '', combined_text)
        # Compute text quality before any processing
        text_quality_score = self._compute_text_quality(combined_text)
        # Remove duplicate blocks
        combined_text = self._remove_duplicate_blocks(combined_text)

        # ── Step 4: Domain detection ──────────────────────────────────────
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

        # ── Step 4b: Fallback header detection ────────────────────────────
        # When layout-based parsing finds no real sections (only __PREAMBLE__),
        # scan combined text for section header lines using registry matching.
        real_sections = [k for k in main_sections if k != '__PREAMBLE__']
        fallback_used = False
        fallback_candidates = []
        if not real_sections and domain.domain == 'resume':
            fallback_sections, fallback_candidates = self._fallback_detect_sections(
                combined_text, doc=doc
            )
            if fallback_sections:
                main_sections = fallback_sections
                fallback_used = True

        # ── Step 5: Field extraction ──────────────────────────────────────
        if domain.domain == 'resume':
            fields = self._extract_resume_fields(
                doc, main_sections, sidebar_sections, combined_text,
                fallback_used=fallback_used,
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
        # Use actual page count from PyMuPDF (via DocumentStructure)
        page_count = doc.page_count if doc.page_count > 0 else (
            len(set(round(l.top / 800) for l in doc.classified_lines)) or 1
        )

        # ── Semantic quality scoring ──────────────────────────────────────
        semantic_quality_score = self._compute_semantic_quality(combined_text)
        # Flag for OCR if either score is very low, or if both are borderline
        mark_for_ocr = (
            text_quality_score < 0.5
            or semantic_quality_score < 0.5
            or (text_quality_score < 0.75 and semantic_quality_score < 0.9)
        )

        # ── Extraction telemetry ──────────────────────────────────────────
        from src.registries.section_registry import CANONICAL_SECTIONS
        sections_found = []
        sections_missing = []
        section_sources = {}

        if domain.domain == 'resume':
            # Merge tagged + plain sections to see coverage
            plain_for_telemetry = self.section_detector.detect(doc.main_text)
            tagged_for_telemetry = self.section_detector.detect_from_tagged(main_sections)
            merged_telemetry = self._merge_sections(tagged_for_telemetry, plain_for_telemetry)

            for sec in CANONICAL_SECTIONS:
                if sec in merged_telemetry and merged_telemetry[sec].strip():
                    sections_found.append(sec)
                    if fallback_used and sec in tagged_for_telemetry:
                        section_sources[sec] = "fallback"
                    elif sec in tagged_for_telemetry:
                        section_sources[sec] = "layout"
                    else:
                        section_sources[sec] = "section_detector"
                else:
                    sections_missing.append(sec)

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
                "pdf_path":             pdf_path,
                "domain_signals":       domain.signals[:5],
                "layout_type":          layout_type,
                "text_quality_score":   text_quality_score,
                "semantic_quality_score": semantic_quality_score,
                "mark_for_ocr":         mark_for_ocr,
                "extraction_engine":    doc.extraction_metadata.get("extractor", "unknown"),
                "blocks": {
                    "header_len":       len(blocks.get("header", "")),
                    "sidebar_len":      len(blocks.get("sidebar", "")),
                    "main_len":         len(blocks.get("main", "")),
                    "footer":           blocks.get("footer", ""),
                },
                # Extraction telemetry
                "section_count":        len(sections_found),
                "sections_found":       sections_found,
                "sections_missing":     sections_missing,
                "section_sources":      section_sources,
                "fallback_detector_used": fallback_used,
                "header_candidates":    len(fallback_candidates),
                # Field-level telemetry (for debugging)
                "summary_found":        bool(fields.get('summary')) if isinstance(fields, dict) else False,
                "skills_count":         len(fields.get('skills', [])) if isinstance(fields, dict) else 0,
                "experience_count":     len(fields.get('experience', [])) if isinstance(fields, dict) else 0,
                "education_count":      len(fields.get('education', [])) if isinstance(fields, dict) else 0,
                "certifications_count": len(fields.get('certifications', [])) if isinstance(fields, dict) else 0,
            },
        )

    def _extract_resume_fields(
        self,
        doc,
        main_sections: Dict[str, str],
        sidebar_sections: Dict[str, list],
        combined_text: str,
        fallback_used: bool = False,
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

        # Plain-text section detection: always run (needed for run-both-score-both)
        # Strategy: try main text → sidebar text → sidebar-header-split-main
        plain_sections: Dict[str, str] = {}

        # Strategy 1: detect sections in main text
        plain_sections = self.section_detector.detect(doc.main_text)

        # Strategy 2: if main text yielded few sections, try sidebar
        # (some two-column resumes put headers + content in sidebar)
        if len(plain_sections) < 2 and doc.sidebar_text.strip():
            sidebar_plain = self.section_detector.detect(doc.sidebar_text)
            if len(sidebar_plain) > len(plain_sections):
                # Merge: sidebar sections fill gaps, but only if content
                # is substantial (not just dates/labels from header column)
                for k, v in sidebar_plain.items():
                    if k not in plain_sections and len(v.strip()) > 100:
                        plain_sections[k] = v

        # Strategy 3: sidebar has headers only (no content), main has
        # content only (no headers). Use sidebar headers as boundary
        # markers to split the combined text.
        if len(plain_sections) < 2 and doc.sidebar_text.strip():
            combined_for_detect = doc.sidebar_text + '\n' + doc.main_text
            combined_plain = self.section_detector.detect(combined_for_detect)
            total_combined_len = sum(len(v) for v in combined_plain.values())
            if len(combined_plain) > len(plain_sections):
                # Only use combined sections with substantial content
                # AND not disproportionately large (likely entire text dumped)
                for k, v in combined_plain.items():
                    content_len = len(v.strip())
                    is_proportional = (
                        total_combined_len == 0
                        or content_len / total_combined_len < 0.6
                    )
                    if (k not in plain_sections
                            and content_len > 100
                            and is_proportional):
                        plain_sections[k] = v

        # Strategy 4: sidebar-ordered section splitting
        # When sidebar has section headers and main has content,
        # use sidebar header ORDER to split main content into sections.
        # ONLY use for summary — proportional splitting is too noisy for
        # structured sections (experience, education) that need exact content.
        quality_sections = sum(
            1 for v in plain_sections.values() if len(v.strip()) > 100
        )
        if quality_sections < 2 and doc.sidebar_text.strip():
            sidebar_split = self._split_main_by_sidebar_headers(
                doc.sidebar_text, doc.main_text, doc.full_width_text)
            if sidebar_split:
                # Only inject summary from sidebar split (reliable first section)
                if 'summary' in sidebar_split and 'summary' not in plain_sections:
                    summary_text = sidebar_split['summary']
                    if len(summary_text.strip()) > 40:
                        plain_sections['summary'] = summary_text

        # ── Build unified sections (preserves tagged + plain text) ────────
        fallback_secs = main_sections if fallback_used else None
        unified = self._build_unified_sections(
            main_sections, plain_sections, fallback_sections=fallback_secs
        )

        # ── Phase 4: Contact (regex-only, no NER) ────────────────────────
        contact = self.contact_parser.parse(
            full_width_text = doc.full_width_text,
            raw_text        = combined_text,
            sidebar_text    = doc.sidebar_text,
            main_text       = doc.main_text,
            hyperlinks      = getattr(doc, 'hyperlinks', []),
        )
        asm_info = assembler_result.get('personal_info', {})

        # Prefer contact_parser name (it does comma stripping and _NOT_NAMES filtering)
        raw_name = contact.get('name') or asm_info.get('name')

        # Strip any remaining tags from name
        if raw_name:
            raw_name = self._strip_tags(raw_name)

        # Reject name if it's a section header
        from src.extractors.layout.section_detector import resolve_section_name
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
                    from src.extractors.contact.contact_parser import _is_name_line
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
                from src.extractors.contact.contact_parser import _is_name_line
                if _is_name_line(candidate):
                    raw_name = candidate

        # Clean name: strip title suffixes
        if raw_name and ',' in raw_name:
            raw_name = raw_name.split(',')[0].strip()

        # Fallback: try first 2-3 words from first line of main_text
        if not raw_name:
            from src.extractors.contact.contact_parser import _is_name_line
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
        # Also grab skills from unified sections (combines all sources)
        skills_unified = unified.get('skills')
        unified_skills_text = skills_unified.plain_text if skills_unified else ''
        all_skills_text = '\n'.join(filter(None, [
            skills_section_text, sidebar_skills_text, unified_skills_text
        ]))
        skills = self.skills_parser.parse(
            skills_section=all_skills_text,
            full_text=combined_text,
            also_scan_fulltext=True,
        )

        # ── Phase 6: Experience (run both → score both → pick best) ─────
        exp_assembler = []
        exp_standalone = []

        # Path A: Assembler on tagged text
        if asm_has_experience:
            exp_assembler = [
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

        # Path B: Standalone parser on plain text from unified sections
        exp_section = unified.get('experience')
        if exp_section and exp_section.plain_text.strip():
            exp_standalone = self.experience_parser.parse(exp_section.plain_text)

        # If standalone found nothing, try date-tag patterns in main_text
        if not exp_standalone:
            exp_standalone = self._parse_date_tag_experience(doc.main_text)

        # Score both and pick best
        score_asm = self._score_experience_entries(exp_assembler)
        score_std = self._score_experience_entries(exp_standalone)
        experience = exp_assembler if score_asm > score_std else exp_standalone

        # ── Experience fallback: parse INTERNSHIP & TRAINING from full_width_text ──
        internship_entries = self._extract_internship_training(doc.full_width_text)
        if internship_entries:
            experience = experience + internship_entries

        # ── Experience fallback 1.5: tagged section with minimal content ──
        # When main_sections has an experience-mapped section but parsers found nothing
        if not experience:
            from src.registries.section_registry import resolve as _resolve_fb
            for raw_key, content in main_sections.items():
                if _resolve_fb(raw_key) == 'experience' and content.strip():
                    clean = re.sub(r'\[/?[A-Z_]+\]', '', content).strip()
                    clean = re.sub(r'^[•·▪\-\*]\s*', '', clean).strip()
                    if clean and len(clean) > 10:
                        # Extract duration if present: "(2 months)"
                        dur_m = re.search(r'\(([^)]+)\)\s*$', clean)
                        duration = dur_m.group(1) if dur_m else None
                        desc = re.sub(r'\([^)]+\)\s*$', '', clean).strip() if dur_m else clean
                        experience.append({
                            "role": "Intern",
                            "company": None,
                            "start": None,
                            "end": None,
                            "location": None,
                            "description": desc,
                            "achievements": [],
                            "duration": duration,
                            "type": "internship",
                        })
                    break

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

        # ── Phase 7: Education (run both → score both → pick best) ─────
        edu_assembler = []
        edu_standalone = []

        # Path A: Assembler on tagged text
        if asm_has_education:
            edu_assembler = [
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

        # Path B: Standalone parser on plain text from unified sections
        edu_section = unified.get('education')
        if edu_section and edu_section.plain_text.strip():
            edu_standalone = self.edu_parser.parse(edu_section.plain_text)

        # Score both and pick best
        score_asm = self._score_education_entries(edu_assembler)
        score_std = self._score_education_entries(edu_standalone)
        education = edu_assembler if score_asm > score_std else edu_standalone

        # ── Education fallback: parse from sidebar [EDUCATION] section ────
        if not education:
            education = self._parse_sidebar_education(doc.sidebar_text)

        # ── Education fallback 2: parse sidebar text via section_detector ─
        if not education:
            # Strip layout tags AND Unicode PUA icons (common in template PDFs)
            clean_sidebar = re.sub(r'[\ue000-\uf8ff]', '', self._strip_tags(doc.sidebar_text))
            sidebar_sections_detected = self.section_detector.detect(clean_sidebar)
            edu_text = sidebar_sections_detected.get('education', '')
            if edu_text:
                education = self.edu_parser.parse(edu_text)

        # ── Education fallback 3: extract from [EDU_LINE] tags ────────────
        if not education:
            edu_line_matches = re.findall(
                r'\[EDU_LINE\](.*?)\[/EDU_LINE\]', doc.main_text)
            if edu_line_matches:
                edu_text_from_tags = '\n'.join(edu_line_matches)
                education = self.edu_parser.parse(edu_text_from_tags)

        # ── Education fallback 4: degree keywords in raw text ─────────────
        if not education:
            clean_main = self._strip_tags(doc.main_text)
            degree_pattern = re.compile(
                r"((?:Bachelor|Master|Associate|Doctor|PhD|MBA|B\.?S\.?c?|M\.?S\.?c?|"
                r"B\.?A\.?|M\.?A\.?|B\.?C\.?A\.?|M\.?C\.?A\.?|Diploma|LLB|LLM|MBBS|MD)"
                r"[^.\n]{5,80})",
                re.IGNORECASE,
            )
            edu_matches = degree_pattern.findall(clean_main)
            if edu_matches:
                edu_text_raw = '\n'.join(edu_matches)
                education = self.edu_parser.parse(edu_text_raw)

        # ── Phase 8: Projects ─────────────────────────────────────────────
        # Use whichever source has more content
        proj_asm_text = assembler_result.get('projects_raw_text', '').strip()
        proj_section = unified.get('projects')
        proj_plain_text = proj_section.plain_text.strip() if proj_section else ''
        projects_raw_text = proj_asm_text if len(proj_asm_text) > len(proj_plain_text) else proj_plain_text
        projects = self.project_parser.parse(
            projects_raw_text,
            hyperlinks=getattr(doc, 'hyperlinks', [])
        )

        # ── Summary ───────────────────────────────────────────────────────
        summary = assembler_result.get('profile')
        if not summary:
            summary_section = unified.get('summary')
            if summary_section and summary_section.plain_text.strip():
                summary = summary_section.plain_text

        # Fallback 1: Profile tagged as [TITLE] in full_width_text
        # (some layouts misclassify Profile as a title due to font size)
        if not summary:
            title_profile_m = re.search(
                r'\[TITLE\]\s*(?:Profile|Summary|Professional\s+Summary|'
                r'Career\s+Objective|Objective|About\s+Me)\s*\[/TITLE\]\s*'
                r'(\[TITLE\](.*?)\[/TITLE\])',
                doc.full_width_text,
                re.DOTALL | re.IGNORECASE,
            )
            if title_profile_m:
                candidate = title_profile_m.group(2).strip()
                # Must be a substantial paragraph (not just a name or section title)
                if len(candidate) > 40:
                    summary = candidate

        # Fallback 2: Profile in sidebar as plain labeled text
        # (two-column resumes where sidebar has "Profile\n<content>")
        if not summary and doc.sidebar_text.strip():
            sidebar_sections_for_summary = self.section_detector.detect(
                doc.sidebar_text)
            sidebar_summary = sidebar_sections_for_summary.get('summary', '')
            if sidebar_summary and len(sidebar_summary.strip()) > 40:
                summary = sidebar_summary.strip()

        # Fallback 3: [TITLE] content after [NAME] in full_width_text
        # (resumes with name + profile in full_width header band, no label)
        if not summary:
            name_end_m = re.search(r'\[/NAME\]', doc.full_width_text)
            if name_end_m:
                after_name = doc.full_width_text[name_end_m.end():]
                # Collect all [TITLE]...[/TITLE] blocks that follow
                title_blocks = re.findall(
                    r'\[TITLE\](.*?)\[/TITLE\]', after_name, re.DOTALL)
                # Filter out section headers, job titles, etc.
                profile_lines = []
                for block in title_blocks:
                    block = block.strip()
                    # Skip if it resolves to a section header
                    from src.registries.section_registry import resolve
                    if resolve(block):
                        break
                    # Skip if it's a section-like keyword
                    if re.match(r'^(?:Employment|Education|Skills|Projects|'
                                r'Certifications|Courses|Languages)', block, re.I):
                        break
                    profile_lines.append(block)
                if profile_lines:
                    candidate = ' '.join(profile_lines)
                    if len(candidate) > 40:
                        summary = candidate

        # ── Certifications ────────────────────────────────────────────────
        courses_raw = assembler_result.get('courses', [])
        certifications = [
            {"name": c.get('name', ''), "issuer": c.get('issuer'), "date": c.get('start_date')}
            for c in (courses_raw or [])
        ] if courses_raw else []

        # Fallback: parse from unified sections
        if not certifications:
            # Check certifications, awards, achievements from unified
            cert_section = unified.get('certifications')
            cert_text = cert_section.plain_text if cert_section else ''
            for fallback_key in ('awards', 'achievements'):
                extra_section = unified.get(fallback_key)
                extra = extra_section.plain_text if extra_section else ''
                if extra:
                    cert_text = (cert_text + '\n' + extra).strip() if cert_text else extra
            if cert_text:
                certifications = self._parse_certifications_text(cert_text)

        # ── Languages ─────────────────────────────────────────────────────
        languages = assembler_result.get('languages', [])
        lang_section_text = assembler_result.get('languages_section', '')
        lang_section = unified.get('languages')
        lang_unified = lang_section.plain_text if lang_section else ''
        if not languages:
            languages = self._extract_languages(
                combined_text + '\n' + lang_section_text + '\n' + lang_unified
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

    def _split_main_by_sidebar_headers(
        self,
        sidebar_text: str,
        main_text: str,
        full_width_text: str,
    ) -> Dict[str, str]:
        """Split main content into sections using sidebar header order.

        For two-column layouts where the sidebar has ONLY section labels
        (PROFILE, EMPLOYMENT HISTORY, EDUCATION, SKILLS) and the main
        column has the actual content without any headers.

        Algorithm:
        1. Extract ordered section headers from sidebar
        2. Strip tags from main text
        3. Use content heuristics to find section boundaries in main text
        4. Map content blocks to sidebar headers by order

        Returns:
            Dict of canonical_section → content_text
        """
        from src.registries.section_registry import resolve

        # Step 1: Find ordered headers in sidebar
        ordered_headers: List[str] = []
        for line in sidebar_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            canonical = resolve(stripped)
            if canonical and canonical not in [h for h, _ in ordered_headers]:
                ordered_headers.append((canonical, stripped))

        if len(ordered_headers) < 2:
            return {}

        # Step 2: Clean main text (strip layout tags)
        clean_main = self._strip_tags(main_text)
        # Also include full_width_text if it has substantial content
        clean_full = self._strip_tags(full_width_text)

        # Combine: full_width first (often has name + profile), then main
        all_content = (clean_full + '\n' + clean_main).strip()
        content_lines = all_content.split('\n')

        if not content_lines:
            return {}

        # Step 3: Try to find section keywords in the content as boundaries
        # Some content lines may contain the section keywords themselves
        section_starts: List[tuple] = []  # (line_idx, canonical)
        for i, line in enumerate(content_lines):
            stripped = line.strip()
            canonical = resolve(stripped)
            if canonical:
                section_starts.append((i, canonical))

        # If we found section markers in content, use them directly
        if len(section_starts) >= 2:
            result: Dict[str, str] = {}
            for idx in range(len(section_starts)):
                start_line = section_starts[idx][0] + 1  # skip the header line
                end_line = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(content_lines)
                section_text = '\n'.join(content_lines[start_line:end_line]).strip()
                if section_text:
                    canonical = section_starts[idx][1]
                    if canonical not in result:
                        result[canonical] = section_text
                    else:
                        result[canonical] += '\n' + section_text
            return result

        # Step 4: No section markers in content → split by proportional
        # content length relative to sidebar header positions.
        # Heuristic: distribute content lines evenly among sections
        header_canonicals = [h for h, _ in ordered_headers]
        n_sections = len(header_canonicals)
        n_lines = len(content_lines)

        # Skip first few lines (usually name, contact info)
        skip_lines = 0
        for i, line in enumerate(content_lines[:8]):
            stripped = line.strip()
            # Contact-like lines (email, phone, address patterns)
            if re.search(r'@|phone|license|driving|nationality|\d{4,}', stripped, re.I):
                skip_lines = i + 1
            # Common resume noise
            elif re.search(r'make this resume|resume templates|build this', stripped, re.I):
                skip_lines = i + 1

        remaining_lines = content_lines[skip_lines:]
        if not remaining_lines:
            return {}

        # Split evenly
        lines_per_section = max(1, len(remaining_lines) // n_sections)
        result: Dict[str, str] = {}
        for i, canonical in enumerate(header_canonicals):
            start = i * lines_per_section
            end = (i + 1) * lines_per_section if i < n_sections - 1 else len(remaining_lines)
            section_text = '\n'.join(remaining_lines[start:end]).strip()
            if section_text:
                result[canonical] = section_text

        return result

    def _merge_sections(
        self,
        tagged_sections: Dict[str, str],
        plain_sections: Dict[str, str],
    ) -> Dict[str, str]:
        """Merge tagged (layout) and plain-text (detector) sections.

        Prefer tagged sections when available (higher priority because they
        come from layout analysis with font/position signals). Fill gaps
        from plain-text detection.

        Args:
            tagged_sections: Sections from layout_extractor, keyed by canonical name
            plain_sections: Sections from section_detector, keyed by canonical name

        Returns:
            Dict keyed by canonical section names with best-available text.
        """
        merged: Dict[str, str] = {}

        # 1. Add tagged sections (higher priority — from layout analysis)
        for canonical, content in tagged_sections.items():
            if content and content.strip():
                if canonical not in merged or len(content) > len(merged[canonical]):
                    merged[canonical] = content

        # 2. Fill gaps from plain-text detection
        for canonical, content in plain_sections.items():
            if canonical not in merged and content and content.strip():
                merged[canonical] = content

        return merged

    def _build_unified_sections(
        self,
        main_sections: Dict[str, str],
        plain_sections: Dict[str, str],
        fallback_sections: Optional[Dict[str, str]] = None,
    ) -> Dict[str, 'SectionContent']:
        """Build unified section map preserving both tagged and plain text.

        For each canonical section:
        - tagged_text = from layout extractor (has [JOB_TITLE], [DATE], [BULLET] tags)
        - plain_text  = from section_detector OR tag-stripped version of tagged_text
        - source      = which path found this section

        Both standalone parsers (ExperienceParser, EducationParser) and the
        assembler (EmploymentParser, EducationParser) can operate on their
        native input format without quality degradation.
        """
        from src.registries.section_registry import resolve

        unified: Dict[str, SectionContent] = {}

        # 1. Layout-extracted tagged sections → tagged_text
        for raw_key, content in main_sections.items():
            if raw_key == '__PREAMBLE__' or not content or not content.strip():
                continue
            canonical = resolve(raw_key)
            if not canonical:
                continue
            if canonical not in unified:
                unified[canonical] = SectionContent(
                    tagged_text=content,
                    plain_text=self._strip_tags(content),
                    source="layout",
                )
            elif len(content) > len(unified[canonical].tagged_text):
                # Longer content wins for same canonical
                unified[canonical].tagged_text = content
                unified[canonical].plain_text = self._strip_tags(content)
                unified[canonical].source = "layout"

        # 2. Plain-text sections → fill plain_text gaps or upgrade with longer content
        for canonical, content in plain_sections.items():
            if not content or not content.strip():
                continue
            if canonical not in unified:
                unified[canonical] = SectionContent(
                    plain_text=content,
                    tagged_text="",  # No tagged version available
                    source="section_detector",
                )
            elif len(content.strip()) > len(unified[canonical].plain_text.strip()):
                # Section detector found more content → use it for plain_text
                # (keeps tagged_text from layout for assembler)
                unified[canonical].plain_text = content

        # 3. Fallback-detected sections → fill remaining gaps
        if fallback_sections:
            for raw_key, content in fallback_sections.items():
                if not content or not content.strip():
                    continue
                canonical = resolve(raw_key)
                if not canonical:
                    continue
                if canonical not in unified:
                    unified[canonical] = SectionContent(
                        plain_text=content,
                        tagged_text="",
                        source="fallback",
                    )
                elif not unified[canonical].plain_text.strip():
                    unified[canonical].plain_text = content

        return unified

    @staticmethod
    def _score_experience_entries(entries: List[Dict]) -> float:
        """Score experience extraction quality.

        Per-entry scoring:
          complete_role:    +2.0  (non-empty, non-generic role)
          complete_company: +2.0  (non-empty company)
          complete_dates:   +1.0  (has start date)
          has_description:  +0.5  (has description or achievements)

        Total = sum(per_entry_scores) + entry_count * 0.5
        """
        if not entries:
            return 0.0

        total = 0.0
        generic_roles = {'intern', 'trainee', 'employee', 'worker', 'staff'}

        for entry in entries:
            score = 0.0
            role = (entry.get('role') or '').strip()
            company = (entry.get('company') or '').strip()
            start = (entry.get('start') or '').strip()
            desc = (entry.get('description') or '').strip()
            achievements = entry.get('achievements', [])

            if role and role.lower() not in generic_roles:
                score += 2.0
            if company:
                score += 2.0
            if start:
                score += 1.0
            if desc or achievements:
                score += 0.5

            total += score

        # Bonus for having multiple entries
        total += len(entries) * 0.5

        return total

    @staticmethod
    def _score_education_entries(entries: List[Dict]) -> float:
        """Score education extraction quality.

        Per-entry scoring:
          complete_degree:      +2.0
          complete_institution: +2.0
          complete_dates:       +1.0
          has_grade:            +0.5

        Total = sum(per_entry_scores) + entry_count * 0.5
        """
        if not entries:
            return 0.0

        total = 0.0

        for entry in entries:
            score = 0.0
            degree = (entry.get('degree') or '').strip()
            institution = (entry.get('institution') or '').strip()
            start = (entry.get('start') or entry.get('end') or '').strip()
            grade = (entry.get('grade') or '').strip()

            if degree:
                score += 2.0
            if institution:
                score += 2.0
            if start:
                score += 1.0
            if grade:
                score += 0.5

            total += score

        total += len(entries) * 0.5

        return total

    def _fallback_detect_sections(
        self,
        text: str,
        doc=None,
    ) -> tuple:
        """Fallback section detection when layout-based parsing finds nothing.

        Strategy 1 (preferred): If doc is provided, scan classified lines for
        sidebar_value entries that match section registry. Collect right-column
        content between matching headers into sections.

        Strategy 2 (text-only): Scan combined text line-by-line for section
        header candidates using registry matching + scoring.

        Only called when sections_found == 0.

        Returns:
            (sections_dict, candidates_list)
            sections_dict: Dict[str, str] keyed by raw section header name
            candidates_list: List of candidate dicts for telemetry
        """
        from src.registries.section_registry import resolve

        # Strategy 1: Use classified lines from layout extraction
        if doc and hasattr(doc, 'classified_lines') and doc.classified_lines:
            sections, candidates = self._fallback_from_classified_lines(
                doc.classified_lines
            )
            if sections:
                return sections, candidates

        # Strategy 2: Text-based fallback
        return self._fallback_from_text(text)

    def _fallback_from_classified_lines(self, classified_lines) -> tuple:
        """Detect sections from classified lines when headers are in sidebar.

        Scans for sidebar_value lines that resolve to known sections,
        then collects right-column (main) content between those headers.
        """
        from src.registries.section_registry import resolve

        # Find sidebar header candidates
        candidates = []
        for i, cl in enumerate(classified_lines):
            if cl.column != 'left':
                continue
            canonical = resolve(cl.text.strip())
            if not canonical:
                continue
            score = self._score_header_candidate(
                cl.text.strip(), canonical, i, len(classified_lines)
            )
            candidates.append({
                'text': cl.text.strip(),
                'canonical': canonical,
                'y_pos': cl.top,
                'line_idx': i,  # index in classified_lines (preserves page order)
                'score': score,
            })

        if not candidates:
            return {}, []

        # Sort by line index (preserves multi-page ordering, unlike y-position)
        candidates.sort(key=lambda c: c['line_idx'])

        # Collect content between each pair of header positions (by line index)
        # Include: right-column lines + left-column date lines (not headers)
        import re as _re
        _DATE_RE = _re.compile(
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}',
            _re.I
        )
        # Build set of header line indices to exclude
        header_idxs = set(c['line_idx'] for c in candidates)

        sections: Dict[str, str] = {}
        for idx, cand in enumerate(candidates):
            start_idx = cand['line_idx']
            end_idx = candidates[idx + 1]['line_idx'] if idx + 1 < len(candidates) else len(classified_lines)

            # Collect content lines in this index range
            content_lines = []
            for li in range(start_idx, end_idx):
                cl = classified_lines[li]
                if li in header_idxs:
                    continue  # skip the header line itself

                if cl.column in ('right', 'full'):
                    content_lines.append(cl.text)
                elif cl.column == 'left' and _DATE_RE.search(cl.text):
                    # Include left-column date lines (e.g., "Jan 2021 — Present")
                    content_lines.append(cl.text)

            content = '\n'.join(content_lines).strip()
            if content:
                sections[cand['text']] = content

        return sections, candidates

    def _fallback_from_text(self, text: str) -> tuple:
        """Text-only fallback: scan for section headers by line."""
        from src.registries.section_registry import resolve

        lines = text.split('\n')
        candidates = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) < 3:
                continue

            clean = re.sub(r'\[/?[A-Z_]+\]', '', stripped).strip()
            if not clean or len(clean) < 3:
                continue

            words = clean.split()
            if len(words) > 5:
                continue

            canonical = resolve(clean)
            score = self._score_header_candidate(clean, canonical, i, len(lines))

            if score >= 0.5:
                candidates.append({
                    'text': clean,
                    'line_num': i,
                    'canonical': canonical,
                    'score': score,
                })

        if not candidates:
            return {}, []

        sections: Dict[str, str] = {}
        candidates.sort(key=lambda c: c['line_num'])

        for idx, cand in enumerate(candidates):
            start = cand['line_num'] + 1
            end = candidates[idx + 1]['line_num'] if idx + 1 < len(candidates) else len(lines)
            content = '\n'.join(lines[start:end]).strip()
            if content:
                sections[cand['text']] = content

        return sections, candidates

    @staticmethod
    def _score_header_candidate(
        text: str,
        canonical: Optional[str],
        line_idx: int,
        total_lines: int,
    ) -> float:
        """Score a line as a potential section header.

        Scoring factors:
        - registry_match: +0.5 (strongest signal)
        - uppercase_ratio: +0.15 if fully uppercase
        - line_length: +0.15 if short (≤30 chars)
        - position: +0.1 if not in first 3 lines (preamble)
        - word_count: +0.1 if 1-3 words

        Returns 0.0-1.0 score. Threshold: ≥ 0.5
        """
        score = 0.0

        # Registry match — strongest signal
        if canonical:
            score += 0.5

        # Uppercase ratio
        alpha = [c for c in text if c.isalpha()]
        if alpha and all(c.isupper() for c in alpha):
            score += 0.15

        # Line length (headers are short)
        if len(text) <= 30:
            score += 0.15
        elif len(text) <= 50:
            score += 0.05

        # Position (skip preamble lines)
        if line_idx >= 3:
            score += 0.1

        # Word count (headers are 1-3 words)
        words = text.split()
        if 1 <= len(words) <= 3:
            score += 0.1

        return min(1.0, score)

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
        """Delegated to src.core.output_cleaning."""
        return clean_text_for_ranking(text)

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
        """Delegated to src.core.quality_scoring."""
        return compute_quality(personal_info, skills, experience, education)

    @staticmethod
    def _compute_text_quality(text: str) -> float:
        """Delegated to src.core.quality_scoring."""
        return compute_text_quality(text)

    @staticmethod
    def _compute_semantic_quality(text: str) -> float:
        """Delegated to src.core.quality_scoring."""
        return compute_semantic_quality(text)

    @staticmethod
    def _remove_duplicate_blocks(text: str) -> str:
        """Delegated to src.core.quality_scoring."""
        return remove_duplicate_blocks(text)


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
        """Delegated to src.core.output_cleaning."""
        return strip_tags(text)

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
        # Import skills dictionary for bypass check — if a skill is in the
        # dictionary, it was explicitly matched and is guaranteed valid.
        from src.extractors.skills.skills_parser import _SKILLS_LOWER

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

            # ── Dictionary bypass: known skills skip heuristic filters ────
            # This prevents the consonant-cluster and alpha-ratio rules from
            # killing legitimate tech skills like Python, MySQL, C++, GraphQL.
            if sk.lower() in _SKILLS_LOWER:
                fixed.append(sk)
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
                'LLM', 'RAG', 'GPT', 'NPM', 'GIT', 'JWT', 'ORM', 'SPA',
                'MVC', 'PR',
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

        # ── Post-processing: remove unsplit skill lines ───────────────────
        # Lines like "Mocha Jest Scrum Agile GIT" where the raw section
        # wasn't split by spaces. If a skill has 3+ words AND every word
        # individually matches an already-extracted single-word skill,
        # it's an unsplit line — drop it.
        singles_lower = {s.lower() for s in fixed if len(s.split()) == 1}
        fixed = [
            s for s in fixed
            if len(s.split()) < 3
            or not all(w.lower() in singles_lower or w.lower() in _SKILLS_LOWER
                       for w in s.split())
        ]

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
        """Delegated to src.core.output_cleaning."""
        return recursive_strip(obj)

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
            quality = fields.get('extraction_quality', 1.0)
            if quality < 0.3:
                warnings.append("Limited structured data extracted — PDF may need OCR or manual review")
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