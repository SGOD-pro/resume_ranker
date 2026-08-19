from typing import Dict, Any, List
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.skills.skills_parser import SkillsParser
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.education.education_parser import EducationParser
from src.extractors.projects.project_parser import ProjectParser
class MarkdownExtractionService:
    """
    Applies deterministic regex parsers to clean Markdown text.

    NOTE: These parsers were originally written for the V1 PDF pipeline but are
    now the canonical extraction layer for the V2 API pipeline (ExtractionPipeline).
    They are NOT the old PDFPipelineV3 — they have been refactored and are
    maintained here under src/extraction/ going forward.

    Output is a flat dict with top-level keys: name, email, phone, location,
    skills, experience, education, projects. This is the format the scorer expects.
    """
    def __init__(self):
        self.contact_parser = ContactParser()
        self.skills_parser = SkillsParser()
        self.experience_parser = ExperienceParser()
        self.edu_parser = EducationParser()
        self.project_parser = ProjectParser()
        
    def extract(self, markdown_text: str, hyperlinks: list = None, elements: list = None, pymupdf_markdown: str = "") -> Dict[str, Any]:
        """
        Runs V1 ported regex parsers on the clean Markdown.
        Returns resolved fields and a list of unresolved chunks.
        """
        # Run parsers
        contact = self.contact_parser.parse(
            raw_text=markdown_text, 
            hyperlinks=hyperlinks, 
            elements=elements,
            pymupdf_text=pymupdf_markdown
        )
        skills = self.skills_parser.parse(full_text=markdown_text + "\n" + pymupdf_markdown, also_scan_fulltext=True)
        experience = self.experience_parser.parse(markdown_text, elements=elements)
        if not experience and pymupdf_markdown:
            experience = self.experience_parser.parse(pymupdf_markdown, elements=[])
        education = self.edu_parser.parse(markdown_text)
        projects = self.project_parser.parse(markdown_text)
        
        fields = {
            "name": contact.get("name"),
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "skills": skills,
            "experience": experience,
            "education": education,
            "projects": projects,
        }
        
        flags = []
        if not fields["email"] or not fields["phone"]:
            flags.append("missing_contact_info")
            
        fields["flags"] = flags
        
        # Only trigger LLM if un-scorable.
        # Un-scorable: experience AND skills are missing.
        missing_critical = False
        
        has_exp = fields["experience"] and len(fields["experience"]) > 0
        has_skills = fields["skills"] and len(fields["skills"]) > 0
        
        if not has_exp and not has_skills:
            missing_critical = True
            
        if not fields["name"]:
            missing_critical = True
            
    
        chunks = []
        if missing_critical:
            # We must tailor the chunks sent to Nova.
            contact_chunk = ""
            if not fields["name"]:
                contact_chunk = markdown_text[:500]
            
            exp_chunk = ""
            if not has_exp and not has_skills:
                # Find experience section
                import re
                _EXP_FLAT_RE = re.compile(
                    r'(?:^|\n)'
                    r'(?:#{0,3}\s*)'
                    r'(?:work\s+)?(?:professional\s+)?'
                    r'(?:experience|experince|employment(?:\s+history)?|'
                    r'career\s+(?:history|summary)|work\s+(?:experience|history)|'
                    r'positions?\s+held|relevant\s+experience)'
                    r'\s*:?\s*\n',
                    re.I,
                )
                m = _EXP_FLAT_RE.search(markdown_text)
                if m:
                    start_idx = m.start()
                    # Find the next 2 headings
                    _HEADING_RE = re.compile(r'\n(?:#{1,3}\s*\w|\n[A-Z][A-Z &/]{3,}\s*:?\s*\n)')
                    headings = list(_HEADING_RE.finditer(markdown_text, m.end()))
                    end_idx = headings[1].start() if len(headings) >= 2 else start_idx + 1500
                    exp_chunk = markdown_text[start_idx:end_idx][:1500]
                else:
                    exp_chunk = markdown_text[500:2000] # Fallback to middle if not found

            if contact_chunk and exp_chunk:
                chunks.append(contact_chunk + "\n\n" + exp_chunk)
            elif contact_chunk:
                chunks.append(contact_chunk)
            elif exp_chunk:
                chunks.append(exp_chunk)
            
        return {
            "fields": fields,
            "unresolved_chunks": chunks
        }
