from typing import Dict, Any, List
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.skills.skills_parser import SkillsParser
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.education.education_parser import EducationParser
from src.extractors.projects.project_parser import ProjectParser
class MarkdownExtractionService:
    """
    Applies the V1 ported deterministic regex parsers to the clean Markdown.
    Provides fallback compatibility with existing extractors.
    """
    def __init__(self):
        self.contact_parser = ContactParser()
        self.skills_parser = SkillsParser()
        self.experience_parser = ExperienceParser()
        self.edu_parser = EducationParser()
        self.project_parser = ProjectParser()
        
    def extract(self, markdown_text: str, hyperlinks: list = None, elements: list = None) -> Dict[str, Any]:
        """
        Runs V1 ported regex parsers on the clean Markdown.
        Returns resolved fields and a list of unresolved chunks.
        """
        # Run parsers
        contact = self.contact_parser.parse(raw_text=markdown_text, hyperlinks=hyperlinks, elements=elements)
        skills = self.skills_parser.parse(full_text=markdown_text, also_scan_fulltext=True)
        experience = self.experience_parser.parse(markdown_text, elements=elements)
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
        
        # Only trigger LLM if un-contactable or un-scorable.
        # Un-contactable: name is missing, OR (email AND phone are missing).
        # Un-scorable: experience AND skills are missing.
        missing_critical = False
        if not fields["name"] or (not fields["email"] and not fields["phone"]):
            missing_critical = True
        
        has_exp = fields["experience"] and len(fields["experience"]) > 0
        has_skills = fields["skills"] and len(fields["skills"]) > 0
        
        if not has_exp and not has_skills:
            missing_critical = True
            
        chunks = []
        if missing_critical:
            # Chunk the markdown text
            paragraphs = markdown_text.split('\n\n')
            current_chunk = []
            current_len = 0
            for p in paragraphs:
                if current_len + len(p) > 1000:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [p]
                    current_len = len(p)
                else:
                    current_chunk.append(p)
                    current_len += len(p)
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            
        return {
            "fields": fields,
            "unresolved_chunks": chunks
        }
