import logging
from typing import Dict, Any, List

from src.extractors.contact.contact_parser import ContactParser
from src.extractors.skills.skills_parser import SkillsParser
from src.extractors.experience.experience_parser import ExperienceParser
from src.extractors.education.education_parser import EducationParser

logger = logging.getLogger(__name__)

class MarkdownExtractionService:
    def __init__(self):
        self.contact_parser = ContactParser()
        self.skills_parser = SkillsParser()
        self.experience_parser = ExperienceParser()
        self.edu_parser = EducationParser()
        
    def extract(self, markdown_text: str) -> Dict[str, Any]:
        """
        Runs V1 ported regex parsers on the clean Markdown.
        Returns resolved fields and a list of unresolved chunks.
        """
        # Run parsers
        contact = self.contact_parser.parse(raw_text=markdown_text)
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
        
        # Collect UnresolvedChunks: blocks of text that didn't yield any fields.
        # A simple heuristic: if a paragraph doesn't contain known extracted info, it's unresolved.
        # But for Phase 3 requirements, we can simply split the text and return it as chunks for Nova.
        # To avoid sending the whole document, we just send the whole markdown in chunks.
        chunks = []
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
