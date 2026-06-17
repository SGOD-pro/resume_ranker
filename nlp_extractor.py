"""
NLP Entity Extractor
Stack: NLTK NE chunker + spaCy EntityRuler (blank model, no download) + regex
Lambda-safe: no transformers, no large model downloads
"""
import re
import nltk
import spacy
from typing import List, Dict, Any
from dataclasses import dataclass

# Download required NLTK data (tiny, ~3MB total)
for pkg in ['punkt_tab', 'averaged_perceptron_tagger_eng', 'maxent_ne_chunker_tab', 'words']:
    try:
        nltk.download(pkg, quiet=True)
    except Exception:
        pass

@dataclass
class Entity:
    text: str
    label: str
    start: int = 0
    end: int = 0
    source: str = "nltk"

# ------------------------------------------------------------------
# Domain Knowledge Sets for Post-Filtering
# ------------------------------------------------------------------
TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "ruby", "go", "rust", "php", "swift", "kotlin",
    "react", "nextjs", "angular", "vue", "node", "django", "flask", "springboot", "express", "fastapi", "qwik",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "keras", "langchain", "langraph", "rag",
    "sql", "mysql", "postgresql", "postgres", "mongodb", "firebase", "redis", "qdrantdb", "vector db", "elasticsearch",
    "docker", "kubernetes", "aws", "azure", "gcp", "vercel", "heroku", "netlify",
    "html", "css", "tailwind", "bootstrap", "sass", "tailwind css",
    "git", "github", "gitlab", "bitbucket", "jira", "confluence", "github actions",
    "figma", "sketch", "adobe", "photoshop", "illustrator", "xd",
    "excel", "tableau", "powerbi", "sap", "oracle", "salesforce", "quickbooks",
    "json", "xml", "yaml", "rest", "graphql", "api", "sdk", "llm", "openai", "chatgpt"
}

PLATFORMS_ORGS = {
    "linkedin", "github", "twitter", "facebook", "instagram", "stackoverflow",
    "microsoft", "google", "amazon", "apple", "meta", "nvidia", "whatsapp",
    "lovableai", "cleark", "saas", "seo", "base_url"
}

# Labels that are clearly NOT people
NOT_PERSON = {
    "linkedin", "github", "twitter", "facebook", "instagram",
    "microsoft", "google", "amazon", "apple", "meta", "nvidia",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "skills", "education", "experience", "portfolio", "summary", "projects"
}

REGEX_PATTERNS = {
    "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
    "PHONE": r'(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}(?!\d)',
    "URL": r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s`<>"{}|\\^`\[\]]+',
    "LINKEDIN": r'linkedin\.com/in/[A-Za-z0-9\-_%]+',
    "MONEY": r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|thousand|k|M|B))?\b|\b[\d,]+(?:\.\d{2})?\s*(?:USD|EUR|GBP|INR|CAD)\b',
    "PERCENTAGE": r'\b\d+(?:\.\d+)?%',
    "DATE": (
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'(?:\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+)?\d{4}\b'
        r'|\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b'
        r'|\b\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}\b'
        r'|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b'
        r'|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–—]\s*(?:Present|Current|Now)\b'
    ),
    "ZIP": r'\b\d{5}(?:-\d{4})?\b',
}

class NLPExtractor:
    def __init__(self):
        self.nlp = self._build_spacy_ruler()

    def _build_spacy_ruler(self):
        nlp = spacy.blank("en")
        ruler = nlp.add_pipe("entity_ruler")

        patterns = [
            {"label": "ROLE", "pattern": [{"LOWER": {"IN": [
                "ceo", "cfo", "cto", "coo", "vp", "director", "manager",
                "engineer", "analyst", "consultant", "coordinator", "specialist",
                "developer", "designer", "architect", "president", "founder",
                "associate", "senior", "junior", "lead", "head", "officer",
                "supervisor", "administrator", "intern", "contractor", "nutritionist",
                "dietitian", "teacher", "professor", "nurse", "doctor", "physician"
            ]}}]},
            {"label": "DEGREE", "pattern": [{"LOWER": {"IN": [
                "bachelor", "master", "phd", "mba", "md", "jd", "associate",
                "diploma", "certificate", "b.s.", "m.s.", "b.a.", "m.a.", "b.sc", "m.sc"
            ]}}]},
            {"label": "SKILL", "pattern": [{"LOWER": {"IN": list(TECH_SKILLS)}}]},
            {"label": "DURATION", "pattern": [
                {"LIKE_NUM": True},
                {"LOWER": {"IN": ["year", "years", "month", "months", "week", "weeks"]}}
            ]},
        ]
        ruler.add_patterns(patterns)
        return nlp

    def extract(self, text: str) -> List[Entity]:
        entities = []
        entities.extend(self._regex_extract(text))
        entities.extend(self._nltk_extract(text))
        entities.extend(self._spacy_extract(text))
        
        entities = self._deduplicate(entities)
        entities = self._post_filter(entities)
        return entities

    def _regex_extract(self, text: str) -> List[Entity]:
        entities = []
        for label, pattern in REGEX_PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(Entity(text=m.group(0).strip(), label=label, start=m.start(), end=m.end(), source="regex"))
        return entities

    def _nltk_extract(self, text: str) -> List[Entity]:
        entities = []
        try:
            sentences = nltk.sent_tokenize(text)
            offset = 0
            for sent in sentences:
                tokens = nltk.word_tokenize(sent)
                pos_tags = nltk.pos_tag(tokens)
                chunks = nltk.ne_chunk(pos_tags, binary=False)
                for subtree in chunks:
                    if not hasattr(subtree, 'label'): continue
                    entity_text = ' '.join(c[0] for c in subtree.leaves())
                    label = subtree.label()
                    label_map = {"PERSON": "PERSON", "ORGANIZATION": "ORG", "GPE": "LOCATION", "FACILITY": "FACILITY", "GSP": "LOCATION", "LOCATION": "LOCATION"}
                    mapped = label_map.get(label, label)
                    start = text.find(entity_text, offset)
                    end = start + len(entity_text) if start != -1 else 0
                    entities.append(Entity(text=entity_text, label=mapped, start=max(0, start), end=end, source="nltk"))
                offset += len(sent) + 1
        except Exception:
            pass
        return entities

    def _spacy_extract(self, text: str) -> List[Entity]:
        entities = []
        try:
            chunk_size = 10000
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                doc = self.nlp(chunk)
                for ent in doc.ents:
                    entities.append(Entity(text=ent.text.strip(), label=ent.label_, start=i + ent.start_char, end=i + ent.end_char, source="spacy_ruler"))
        except Exception:
            pass
        return entities

    def _deduplicate(self, entities: List[Entity]) -> List[Entity]:
        if not entities: return []
        entities.sort(key=lambda e: (e.start, -len(e.text)))
        seen_spans = []
        result = []
        for ent in entities:
            overlap = False
            for (s, e) in seen_spans:
                if ent.start < e and ent.end > s:
                    overlap = True
                    break
            if not overlap and ent.text.strip():
                result.append(ent)
                seen_spans.append((ent.start, ent.end))
        return result

    def _post_filter(self, entities: List[Entity]) -> List[Entity]:
        cleaned = []
        for ent in entities:
            text_lower = ent.text.lower().strip()
            
            if len(ent.text.strip()) <= 1: continue
            if ent.text.strip().isdigit() and ent.source != "regex": continue
            
            # CRITICAL FIX: Relabel Tech Skills misclassified by NLTK
            if ent.label in ["PERSON", "ORG", "LOCATION"] and text_lower in TECH_SKILLS:
                ent.label = "SKILL"
            elif ent.label in ["PERSON", "LOCATION"] and text_lower in PLATFORMS_ORGS:
                ent.label = "ORG"
                
            # Filter out obvious non-person words labeled as PERSON
            if ent.label == "PERSON" and text_lower in NOT_PERSON:
                continue
                
            # Fix languages misclassified as ORG
            if ent.label == "ORG" and text_lower in {"english", "french", "spanish", "german", "chinese", "arabic", "bengali"}:
                ent.label = "LANGUAGE"
                
            cleaned.append(ent)
        return cleaned