from typing import Dict, Any, List
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.skills.skills_parser import SkillsParser
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.education.education_parser import EducationParser

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
        
    def extract(self, markdown_text: str, hyperlinks: list = None) -> Dict[str, Any]:
        """
        Runs V1 ported regex parsers on the clean Markdown.
        Returns resolved fields and a list of unresolved chunks.
        """
        # Run parsers
        contact = self.contact_parser.parse(raw_text=markdown_text, hyperlinks=hyperlinks)
        skills = self.skills_parser.parse(full_text=markdown_text, also_scan_fulltext=True)
        experience = self.experience_parser.parse(markdown_text)
        education = self.edu_parser.parse(markdown_text)
        
        fields = {
            "name": contact.get("name"),
            "email": contact.get("email"),
            "phone": contact.get("phone"),
            "skills": skills,
            "experience": experience,
            "education": education,
        }
        
        # Only trigger LLM if a CRITICAL field is missing.
        # Critical fields: name, email, phone, experience, skills
        missing_critical = False
        if not fields["name"] or not fields["email"] or not fields["phone"]:
            missing_critical = True
        if not fields["experience"] or len(fields["experience"]) == 0:
            missing_critical = True
        if not fields["skills"] or len(fields["skills"]) == 0:
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
