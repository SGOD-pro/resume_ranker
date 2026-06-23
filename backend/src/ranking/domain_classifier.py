"""
domain_classifier.py — Candidate domain classification
=========================================================
Classifies a candidate's professional domain from resume content
using weighted voting across skills, experience, and projects.

Priority order:
    Experience keywords  (weight 3.0)
    Project keywords     (weight 2.0)
    Skills               (weight 1.0)

Usage:
    classifier = DomainClassifier()
    domain, confidence = classifier.classify(candidate_fields)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.ranking.skill_inference import SkillInferenceEngine

logger = logging.getLogger(__name__)


class DomainClassifier:
    """Classify candidate domain from resume fields using weighted voting."""

    def __init__(self, engine: Optional[SkillInferenceEngine] = None):
        self._engine = engine or SkillInferenceEngine()

    def classify(self, candidate: Dict[str, Any]) -> Tuple[str, float]:
        """Classify candidate domain from resume fields.

        Returns:
            (domain, confidence) where domain is one of the 7 supported domains
            and confidence is 0.0–1.0.
        """
        domain_scores: Dict[str, float] = {}

        # ── Signal 1: Experience keywords (weight 3.0) ────────────────────
        experience = candidate.get('experience', [])
        for exp in experience:
            role = (exp.get('role') or '').lower()
            company = (exp.get('company') or '').lower()
            description = (exp.get('description') or '').lower()
            achievements = exp.get('achievements', []) or []
            ach_text = ' '.join(str(a) for a in achievements).lower()
            exp_text = f"{role} {company} {description} {ach_text}"

            # Score role title (strongest signal)
            role_domain = self._classify_text_snippet(role)
            for d, s in role_domain.items():
                domain_scores[d] = domain_scores.get(d, 0) + s * 3.0

            # Score experience description (moderate signal)
            desc_domain = self._classify_text_snippet(exp_text)
            for d, s in desc_domain.items():
                domain_scores[d] = domain_scores.get(d, 0) + s * 1.5

        # ── Signal 2: Project keywords (weight 2.0) ───────────────────────
        projects = candidate.get('projects', [])
        for proj in projects:
            name = (proj.get('name') or '').lower()
            desc = (proj.get('description') or '').lower()
            tech = proj.get('technologies', []) or []
            tech_text = ' '.join(str(t) for t in tech).lower()
            proj_text = f"{name} {desc} {tech_text}"

            proj_domain = self._classify_text_snippet(proj_text)
            for d, s in proj_domain.items():
                domain_scores[d] = domain_scores.get(d, 0) + s * 2.0

        # ── Signal 3: Skills (weight 1.0) ─────────────────────────────────
        skills = candidate.get('skills', [])
        for skill in skills:
            skill_domain = self._engine.get_skill_domain(skill)
            if skill_domain:
                domain_scores[skill_domain] = domain_scores.get(skill_domain, 0) + 1.0

        # ── Compute final domain and confidence ───────────────────────────
        if not domain_scores:
            return 'unknown', 0.0

        best_domain = max(domain_scores, key=domain_scores.get)  # type: ignore
        total = sum(domain_scores.values())
        confidence = domain_scores[best_domain] / total if total > 0 else 0.0

        return best_domain, round(confidence, 3)

    def _classify_text_snippet(self, text: str) -> Dict[str, float]:
        """Score a text snippet against domain keyword dictionaries.

        Returns {domain: score} based on keyword matches.
        """
        if not text or len(text) < 5:
            return {}

        scores: Dict[str, float] = {}

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = 0.0
            for kw, weight in keywords:
                if kw in text:
                    score += weight
            if score > 0:
                scores[domain] = score

        return scores

    def classify_jd(self, jd_title: str, jd_skills: List[str],
                    jd_description: str = '', jd_department: str = '') -> Tuple[str, float]:
        """Classify a JD's domain for penalty computation.

        Uses job title, skills, and description to determine domain.
        """
        domain_scores: Dict[str, float] = {}

        # Title is the strongest signal
        title_lower = jd_title.lower()
        title_domain = self._classify_text_snippet(title_lower)
        for d, s in title_domain.items():
            domain_scores[d] = domain_scores.get(d, 0) + s * 4.0

        # Department
        dept_lower = jd_department.lower()
        dept_domain = self._classify_text_snippet(dept_lower)
        for d, s in dept_domain.items():
            domain_scores[d] = domain_scores.get(d, 0) + s * 3.0

        # Skills
        for skill in jd_skills:
            skill_domain = self._engine.get_skill_domain(skill)
            if skill_domain:
                domain_scores[skill_domain] = domain_scores.get(skill_domain, 0) + 1.5

        # Description
        desc_domain = self._classify_text_snippet(jd_description.lower())
        for d, s in desc_domain.items():
            domain_scores[d] = domain_scores.get(d, 0) + s * 1.0

        if not domain_scores:
            return 'unknown', 0.0

        best = max(domain_scores, key=domain_scores.get)  # type: ignore
        total = sum(domain_scores.values())
        confidence = domain_scores[best] / total if total > 0 else 0.0

        return best, round(confidence, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Domain keyword dictionaries for text-based classification
# ─────────────────────────────────────────────────────────────────────────────
# Each entry: (keyword, weight) — higher weight = stronger domain signal

_DOMAIN_KEYWORDS: Dict[str, List[Tuple[str, float]]] = {
    "engineering": [
        # Job titles
        ("software engineer", 3.0), ("developer", 2.5), ("programmer", 2.5),
        ("devops", 2.5), ("architect", 2.0), ("data engineer", 2.5),
        ("machine learning", 2.5), ("frontend", 2.0), ("backend", 2.0),
        ("full stack", 2.0), ("fullstack", 2.0), ("sre", 2.0),
        ("system administrator", 2.0), ("sysadmin", 2.0), ("dba", 2.0),
        ("web developer", 2.5), ("mobile developer", 2.5),
        ("qa engineer", 2.0), ("test engineer", 2.0),
        ("data scientist", 2.5), ("ml engineer", 2.5),
        # Tech keywords
        ("api", 1.5), ("database", 1.5), ("microservice", 1.5),
        ("deployment", 1.5), ("cloud", 1.5), ("server", 1.0),
        ("github", 1.5), ("repository", 1.0), ("codebase", 1.5),
        ("agile", 1.0), ("sprint", 1.0), ("scrum", 1.0),
        ("ci/cd", 1.5), ("pipeline", 1.0), ("container", 1.5),
        ("algorithm", 1.5), ("framework", 1.0),
    ],
    "legal": [
        ("attorney", 3.0), ("lawyer", 3.0), ("counsel", 3.0),
        ("paralegal", 2.5), ("legal", 2.5), ("law firm", 2.5),
        ("court", 2.0), ("litigation", 2.5), ("compliance", 2.0),
        ("contract", 2.0), ("statute", 2.0), ("regulation", 1.5),
        ("intellectual property", 2.0), ("patent", 2.0), ("trademark", 2.0),
        ("deposition", 2.0), ("arbitration", 2.0), ("mediation", 1.5),
        ("jurisdiction", 2.0), ("plaintiff", 2.0), ("defendant", 2.0),
        ("legal research", 2.5), ("westlaw", 2.5), ("lexisnexis", 2.5),
        ("bar exam", 2.5), ("juris doctor", 2.5), ("llb", 2.5),
    ],
    "finance": [
        ("financial analyst", 3.0), ("investment", 2.5), ("banker", 2.5),
        ("portfolio", 2.5), ("trading", 2.5), ("equity", 2.0),
        ("hedge fund", 2.5), ("private equity", 2.5), ("venture capital", 2.5),
        ("asset management", 2.5), ("risk management", 2.0),
        ("valuation", 2.0), ("dcf", 2.0), ("financial model", 2.5),
        ("bloomberg", 2.0), ("capital market", 2.0), ("underwriting", 2.0),
        ("derivatives", 2.0), ("fixed income", 2.0), ("bonds", 1.5),
        ("securities", 2.0), ("stock", 1.5), ("forex", 2.0),
        ("wealth management", 2.5), ("fintech", 2.0),
        ("cfa", 2.5), ("frm", 2.5),
    ],
    "healthcare": [
        ("nurse", 3.0), ("nursing", 3.0), ("physician", 3.0), ("doctor", 2.5),
        ("patient", 2.5), ("clinical", 2.5), ("hospital", 2.5),
        ("medical", 2.5), ("healthcare", 2.5), ("health care", 2.5),
        ("pharmacy", 2.5), ("pharmacist", 2.5), ("pharmaceutical", 2.0),
        ("diagnosis", 2.0), ("treatment", 2.0), ("surgery", 2.0),
        ("therapist", 2.5), ("physical therapy", 2.5),
        ("emr", 2.0), ("ehr", 2.0), ("hipaa", 2.0),
        ("vital signs", 2.0), ("medication", 2.0), ("prescription", 2.0),
        ("icu", 2.0), ("er ", 1.5), ("emergency room", 2.0),
        ("mental health", 2.0), ("psychiatr", 2.0), ("counselor", 2.0),
    ],
    "hr": [
        ("human resources", 3.0), ("hr manager", 3.0), ("hr director", 3.0),
        ("recruiter", 3.0), ("recruiting", 2.5), ("recruitment", 2.5),
        ("talent acquisition", 3.0), ("headhunter", 2.5), ("sourcing", 2.0),
        ("onboarding", 2.0), ("employee relations", 2.5),
        ("compensation", 2.0), ("benefits", 1.5), ("payroll", 2.0),
        ("hris", 2.5), ("workday", 2.0), ("successfactors", 2.0),
        ("performance management", 2.0), ("training", 1.5),
        ("organizational development", 2.0), ("diversity", 1.5),
        ("labor relations", 2.5), ("employee engagement", 2.0),
        ("people operations", 2.5), ("people ops", 2.5),
        ("workforce planning", 2.5), ("employer branding", 2.0),
    ],
    "marketing": [
        ("marketing", 2.5), ("marketer", 2.5), ("brand", 2.0),
        ("digital marketing", 3.0), ("content marketing", 2.5),
        ("seo", 2.5), ("sem", 2.0), ("ppc", 2.0), ("google ads", 2.5),
        ("social media", 2.5), ("campaign", 2.0), ("advertising", 2.0),
        ("copywriting", 2.0), ("email marketing", 2.0),
        ("conversion", 1.5), ("lead generation", 2.0), ("crm", 1.5),
        ("analytics", 1.5), ("google analytics", 2.0),
        ("market research", 2.0), ("audience", 1.5),
        ("engagement", 1.5), ("influencer", 2.0),
        ("content strategy", 2.5), ("brand manager", 2.5),
        ("creative director", 2.0),
    ],
    "accounting": [
        ("accountant", 3.0), ("accounting", 2.5), ("bookkeeper", 2.5),
        ("auditor", 3.0), ("audit", 2.0), ("cpa", 2.5),
        ("gaap", 2.5), ("ifrs", 2.5), ("sox", 2.0),
        ("tax", 2.0), ("taxation", 2.0), ("tax preparation", 2.5),
        ("accounts payable", 2.5), ("accounts receivable", 2.5),
        ("general ledger", 2.5), ("journal entries", 2.0),
        ("financial statements", 2.0), ("balance sheet", 2.0),
        ("reconciliation", 2.0), ("invoicing", 1.5),
        ("quickbooks", 2.0), ("xero", 2.0), ("sage", 1.5),
        ("forensic accounting", 2.5), ("internal controls", 2.0),
        ("cost accounting", 2.0), ("payroll", 1.5),
    ],
    "education": [
        ("teacher", 3.0), ("teaching", 2.5), ("professor", 3.0),
        ("lecturer", 2.5), ("instructor", 2.5), ("educator", 2.5),
        ("curriculum", 2.5), ("pedagogy", 2.5), ("lesson plan", 2.5),
        ("classroom", 2.5), ("student", 2.0), ("school", 2.0),
        ("university", 1.5), ("academic", 2.0), ("faculty", 2.5),
        ("tutor", 2.5), ("tutoring", 2.0), ("scholarship", 1.5),
        ("e-learning", 2.0), ("lms", 2.0), ("moodle", 2.0),
        ("course design", 2.5), ("assessment", 1.5),
        ("special education", 2.5), ("k-12", 2.5), ("kindergarten", 2.5),
        ("principal", 2.0), ("superintendent", 2.5),
        ("research paper", 2.0), ("phd", 1.5), ("dissertation", 2.0),
        ("dean", 2.0), ("provost", 2.5),
    ],
    "hospitality": [
        ("hotel", 3.0), ("hospitality", 3.0), ("restaurant", 2.5),
        ("chef", 3.0), ("cook", 2.0), ("kitchen", 2.0),
        ("front desk", 2.5), ("concierge", 2.5), ("housekeeping", 2.5),
        ("tourism", 2.5), ("travel", 2.0), ("resort", 2.5),
        ("food service", 2.5), ("catering", 2.5), ("banquet", 2.0),
        ("bar", 1.5), ("bartender", 2.5), ("sommelier", 2.5),
        ("guest", 2.0), ("reservation", 2.0), ("lobby", 1.5),
        ("room service", 2.5), ("event management", 2.0),
        ("food safety", 2.0), ("haccp", 2.0), ("menu", 1.5),
    ],
    "construction": [
        ("construction", 3.0), ("contractor", 2.5), ("builder", 2.5),
        ("foreman", 2.5), ("site manager", 3.0), ("site engineer", 2.5),
        ("quantity surveyor", 3.0), ("civil engineer", 3.0),
        ("structural engineer", 3.0), ("architect", 2.5),
        ("blueprint", 2.0), ("scaffolding", 2.0), ("concrete", 2.0),
        ("masonry", 2.0), ("welding", 2.0), ("plumbing", 2.0),
        ("electrician", 2.0), ("carpentry", 2.0), ("roofing", 2.0),
        ("excavation", 2.0), ("demolition", 2.0), ("safety officer", 2.5),
        ("osha", 2.5), ("building code", 2.0), ("permit", 1.5),
        ("project management", 1.5), ("autocad", 1.5), ("revit", 1.5),
        ("primavera", 2.0), ("ms project", 1.5),
    ],
    "admin": [
        ("administrative", 2.5), ("admin assistant", 3.0),
        ("executive assistant", 3.0), ("office manager", 3.0),
        ("secretary", 2.5), ("receptionist", 2.5),
        ("office coordinator", 2.5), ("data entry", 2.5),
        ("filing", 1.5), ("scheduling", 2.0), ("calendar", 1.5),
        ("correspondence", 2.0), ("typing", 1.5), ("wpm", 2.0),
        ("office administration", 3.0), ("front office", 2.0),
        ("clerical", 2.5), ("office supplies", 1.5),
        ("switchboard", 2.0), ("mail", 1.5), ("fax", 1.5),
        ("meeting minutes", 2.0), ("travel arrangements", 2.0),
        ("document management", 2.0), ("archiving", 1.5),
    ],
    "sales": [
        ("sales", 2.5), ("salesperson", 3.0), ("sales manager", 3.0),
        ("account executive", 3.0), ("business development", 3.0),
        ("bdr", 2.5), ("sdr", 2.5), ("closer", 2.0),
        ("quota", 2.5), ("revenue", 2.0), ("commission", 2.0),
        ("cold call", 2.5), ("prospecting", 2.5), ("pipeline", 1.5),
        ("deal", 1.5), ("territory", 2.0), ("retail", 2.0),
        ("customer", 1.5), ("client", 1.5), ("negotiation", 2.0),
        ("salesforce", 2.0), ("hubspot", 2.0), ("crm", 1.5),
        ("b2b", 2.0), ("b2c", 2.0), ("enterprise sales", 3.0),
        ("channel partner", 2.5), ("key account", 2.5),
        ("upsell", 2.0), ("cross-sell", 2.0),
    ],
}
