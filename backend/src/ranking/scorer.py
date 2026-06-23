"""
scorer.py — AI Resume Screening & Candidate Ranking System
============================================================
3-Phase scoring engine:
  Phase 1: Hard Knockout    (must-have skills, min years, required degree)
  Phase 2: Multi-Signal     (BM25 skills, experience, keywords, education)
  Phase 3: Rank & Explain   (sort, percentile, breakdown, anomaly flags)

Usage:
  from scorer import CandidateScorer, JobDescription
  jd = JobDescription(title="Backend Engineer", must_have_skills=["Python", "SQL"], ...)
  scorer = CandidateScorer()
  results = scorer.rank(jd, candidates)
"""

from __future__ import annotations
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes (imported from src.schemas.scoring)
# ─────────────────────────────────────────────────────────────────────────────

from src.schemas.scoring import JobDescription, ScoredCandidate


# ─────────────────────────────────────────────────────────────────────────────
# Degree Level Mapping
# ─────────────────────────────────────────────────────────────────────────────

DEGREE_LEVELS = {
    "phd": 5, "doctorate": 5, "ph.d": 5,
    "master": 4, "masters": 4, "mba": 4, "m.s": 4, "m.a": 4, "msc": 4,
    "m.sc": 4, "m.tech": 4, "mtech": 4,
    "bachelor": 3, "bachelors": 3, "b.s": 3, "b.a": 3, "bsc": 3,
    "b.sc": 3, "b.tech": 3, "btech": 3, "bca": 3, "b.e": 3, "be": 3,
    "associate": 2, "associates": 2, "diploma": 2,
    "class 12": 1, "12th": 1, "high school": 1,
    "class 10": 0, "10th": 0,
    "any": -1, "none": 0,
}


def _parse_degree_level(degree_str: str) -> int:
    """Convert a degree string to a numeric level."""
    if not degree_str:
        return 0
    d = degree_str.lower().strip()
    # Direct match
    for key, val in DEGREE_LEVELS.items():
        if key in d:
            return val
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Skill Normalization & Matching (delegated to skill_registry)
# ─────────────────────────────────────────────────────────────────────────────

from src.registries.skill_registry import (
    SKILL_ALIASES as _SKILL_ALIASES,
    SINGLE_CHAR_SKILLS as _SINGLE_CHAR_SKILLS,
    normalize as _normalize_skill,
    match as _skill_match,
    find_matches as _find_matching_skills,
    get_search_variants as _get_search_variants,
)


# ─────────────────────────────────────────────────────────────────────────────
# Ranking Algorithms (delegated to src/ranking/)
# ─────────────────────────────────────────────────────────────────────────────

from src.ranking.tfidf_scorer import (
    tokenize as _tokenize,
    tf as _tf,
    cosine_sim as _cosine_sim,
    text_cosine_sim as _text_cosine_sim,
)

from src.ranking.bm25_scorer import bm25_skill_score as _bm25_skill_score, precompute_bm25_idf as _precompute_bm25_idf
from src.ranking.similarity import (
    parse_date as _parse_date,
    compute_total_experience_years as _compute_total_experience_years,
    most_recent_end_date as _most_recent_end_date,
    experience_score as _experience_score,
    keyword_score as _keyword_score,
    education_score as _education_score,
)

# ── Phase 2: Inference Engine & Domain Classification ─────────────────────
from src.ranking.skill_inference import SkillInferenceEngine, WEIGHT_INFERRED
from src.ranking.domain_classifier import DomainClassifier

import json as _json
import os as _os

_DOMAIN_PROXIMITY_PATH = _os.path.join(
    _os.path.dirname(__file__), '..', 'registries', 'domain_proximity.json'
)
_cached_proximity = None

def _load_domain_proximity():
    """Load and cache the domain proximity penalty matrix."""
    global _cached_proximity
    if _cached_proximity is not None:
        return _cached_proximity
    with open(_DOMAIN_PROXIMITY_PATH) as f:
        _cached_proximity = _json.load(f)
    return _cached_proximity

def _get_domain_penalty(jd_domain: str, candidate_domain: str,
                        jd_confidence: float, cand_confidence: float) -> float:
    """Get domain mismatch penalty for skill_score.

    Returns negative penalty percentage (e.g., -80 for severe mismatch).
    Returns 0 when domains match or confidence is too low.
    """
    # No penalty for unknown domains (confidence < 0.4)
    if not jd_domain or not candidate_domain:
        return 0.0
    if jd_confidence < 0.4 or cand_confidence < 0.4:
        return 0.0
    if jd_domain == candidate_domain:
        return 0.0
    if jd_domain == 'unknown' or candidate_domain == 'unknown':
        return 0.0

    prox = _load_domain_proximity()
    penalties = prox.get('penalties', {})

    # Look up JD domain → candidate domain penalty
    jd_penalties = penalties.get(jd_domain, {})
    penalty = jd_penalties.get(candidate_domain, -50.0)  # Default -50 for unmapped

    return float(penalty)


# ─────────────────────────────────────────────────────────────────────────────
# Project-Skill Bonus Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _project_skill_bonus(candidate: Dict[str, Any],
                         jd_skills: List[str]) -> Tuple[float, List[str]]:
    """
    Bonus for having projects that use technologies matching JD skills.
    If candidate built real projects with the required skills, they're
    more likely to be a strong fit.
    Returns (bonus 0-5.0, list of matched project skills).
    """
    projects = candidate.get('projects', [])
    if not projects or not jd_skills:
        return 0.0, []

    matched_project_skills = set()
    for proj in projects:
        # Check technologies listed in the project
        tech_list = proj.get('technologies') or []
        if isinstance(tech_list, str):
            tech_list = [t.strip() for t in tech_list.split(',')]
        proj_text = ' '.join([
            proj.get('name') or '',
            proj.get('description') or '',
            ' '.join(tech_list),
        ]).lower()

        for jd_sk in jd_skills:
            jd_sk_lower = jd_sk.lower()
            # Check structured tech list
            if any(_skill_match(t, jd_sk) for t in tech_list):
                matched_project_skills.add(jd_sk)
            # Also check project description text
            elif re.search(r'\b' + re.escape(jd_sk_lower) + r'\b', proj_text):
                matched_project_skills.add(jd_sk)

    if not matched_project_skills:
        return 0.0, []

    # Bonus: up to 5.0 points, scaled by how many JD skills are in projects
    ratio = len(matched_project_skills) / len(jd_skills)
    bonus = min(5.0, ratio * 6.0)  # Max 5 points
    return round(bonus, 1), sorted(matched_project_skills)


# ─────────────────────────────────────────────────────────────────────────────
# Prestigious Company Bonus
# ─────────────────────────────────────────────────────────────────────────────

# Top-tier companies across industries
_PRESTIGIOUS_COMPANIES = {
    # ── Tech / FAANG+ ──
    'google', 'alphabet', 'meta', 'facebook', 'apple', 'amazon', 'microsoft',
    'netflix', 'nvidia', 'tesla', 'openai', 'deepmind', 'anthropic',
    'salesforce', 'adobe', 'oracle', 'ibm', 'intel', 'cisco', 'samsung',
    'palantir', 'snowflake', 'databricks', 'stripe', 'uber', 'airbnb',
    'linkedin', 'twitter', 'x corp', 'spotify', 'shopify', 'atlassian',
    'vmware', 'sap', 'twilio', 'cloudflare', 'crowdstrike', 'datadog',
    'square', 'block', 'coinbase', 'robinhood', 'instacart', 'doordash',
    'lyft', 'pinterest', 'snap', 'tiktok', 'bytedance', 'zoom',
    'infosys', 'tcs', 'wipro', 'cognizant', 'hcl', 'tech mahindra',
    # ── Finance ──
    'goldman sachs', 'jpmorgan', 'jp morgan', 'morgan stanley',
    'blackrock', 'citadel', 'two sigma', 'jane street', 'bridgewater',
    'barclays', 'deutsche bank', 'ubs', 'credit suisse', 'hsbc',
    'visa', 'mastercard', 'paypal', 'american express', 'fidelity',
    # ── Consulting ──
    'mckinsey', 'bcg', 'bain', 'deloitte', 'pwc', 'kpmg', 'ey',
    'ernst & young', 'accenture', 'capgemini',
    # ── Pharma / Healthcare ──
    'pfizer', 'johnson & johnson', 'roche', 'novartis', 'merck',
    'abbvie', 'eli lilly', 'astrazeneca', 'moderna', 'gsk',
    # ── Retail / Consumer ──
    'walmart', 'target', 'costco', 'nike', 'adidas',
    "macy's", 'macys', 'nordstrom', 'best buy', 'home depot',
    'coca-cola', 'pepsico', 'procter & gamble', 'unilever', "l'oreal",
    # ── Media / Entertainment ──
    'disney', 'warner bros', 'paramount', 'sony', 'nbc', 'cnn', 'bbc',
    # ── Automotive / Aerospace ──
    'bmw', 'mercedes', 'toyota', 'ford', 'general motors', 'spacex',
    'boeing', 'lockheed martin', 'raytheon',
    # ── Energy ──
    'shell', 'bp', 'chevron', 'exxonmobil',
}


def _prestige_bonus(candidate: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Bonus for working at prestigious/top-tier companies.
    Returns (bonus 0-4.0, list of matched prestigious companies).
    """
    experience = candidate.get('experience', [])
    if not experience:
        return 0.0, []

    matched = []

    for exp in experience:
        company = (exp.get('company') or '').lower()
        if not company:
            continue
        for prestige in _PRESTIGIOUS_COMPANIES:
            # Only match against the structured company name (not raw text)
            # to avoid false positives from URLs like "linkedin.com/in/..."
            if prestige in company and len(prestige) >= 3:
                display_name = prestige.title()
                if display_name not in matched:
                    matched.append(display_name)
                break  # One match per experience entry

    if not matched:
        return 0.0, []

    # Bonus: 2.0 per prestigious company, max 4.0
    bonus = min(4.0, len(matched) * 2.0)
    return round(bonus, 1), matched


# ─────────────────────────────────────────────────────────────────────────────
# Certificate / Hackathon Bonus Scoring
# ─────────────────────────────────────────────────────────────────────────────

# Prestigious certificate issuers (higher bonus weight)
_PRESTIGIOUS_CERT_ISSUERS = {
    # ── Tech Companies ──
    'google', 'aws', 'amazon', 'microsoft', 'azure', 'meta', 'facebook',
    'ibm', 'oracle', 'cisco', 'salesforce', 'adobe', 'nvidia',
    'red hat', 'vmware', 'hashicorp', 'databricks', 'snowflake',
    # ── Education / Certification Bodies ──
    'coursera', 'udacity', 'edx', 'mit', 'stanford', 'harvard',
    'iit', 'cambridge', 'oxford',
    'comptia', 'pmi', 'isaca', 'isc2', '(isc)2',
    # ── Domain-specific ──
    'hubspot', 'hootsuite', 'semrush', 'moz',       # Marketing
    'cfa', 'frm', 'chartered',                       # Finance
    'nist', 'sans', 'ec-council',                    # Security
    'six sigma', 'lean', 'prince2', 'itil',          # Management
}

# Keywords indicating hackathon / competition achievements
_HACKATHON_KEYWORDS = [
    'hackathon', 'hack-a-thon', 'coding competition', 'code competition',
    'programming contest', 'coding challenge', 'competitive programming',
    'kaggle', 'topcoder', 'codeforces', 'leetcode', 'hackerrank',
    'datathon', 'ideathon', 'makeathon', 'buildathon',
]

_WIN_KEYWORDS = [
    'winner', 'won', 'first place', '1st place', 'champion', 'gold',
    'finalist', 'runner-up', 'runner up', 'second place', '2nd place',
    'top 3', 'top 5', 'top 10', 'best project', 'grand prize',
]

# Domain-relevant cert keywords (for all domains, not just IT)
_CERT_DOMAIN_KEYWORDS = {
    'it': ['web', 'cloud', 'devops', 'python', 'java', 'javascript', 'react',
           'angular', 'node', 'docker', 'kubernetes', 'aws', 'azure', 'gcp',
           'data science', 'machine learning', 'deep learning', 'ai',
           'cybersecurity', 'network', 'database', 'sql', 'full stack',
           'frontend', 'backend', 'mobile', 'ios', 'android', 'agile', 'scrum'],
    'marketing': ['digital marketing', 'seo', 'sem', 'social media', 'content',
                  'google ads', 'analytics', 'marketing', 'brand', 'campaign',
                  'hubspot', 'hootsuite', 'email marketing'],
    'finance': ['cfa', 'frm', 'cpa', 'acca', 'financial', 'accounting',
                'investment', 'banking', 'audit', 'tax', 'risk management'],
    'healthcare': ['nursing', 'cpr', 'first aid', 'medical', 'clinical',
                   'pharmaceutical', 'health', 'hipaa', 'patient care'],
    'security': ['security guard', 'socp', 'surveillance', 'law enforcement',
                 'criminal justice', 'safety', 'osha', 'fire safety'],
    'education': ['teaching', 'tesol', 'tefl', 'pedagogy', 'curriculum',
                  'education', 'training', 'certification', 'instructor'],
    'design': ['ui', 'ux', 'user experience', 'figma', 'sketch', 'adobe',
               'photoshop', 'illustrator', 'graphic design', 'interaction'],
    'hr': ['hr', 'human resources', 'recruitment', 'talent', 'payroll',
            'labor law', 'employee relations', 'organizational behavior'],
    'hospitality': ['hospitality', 'tourism', 'travel', 'hotel', 'restaurant',
                    'food safety', 'customer service'],
    'legal': ['law', 'legal', 'compliance', 'regulatory', 'contract',
              'litigation', 'paralegal', 'bar exam'],
    'retail': ['retail', 'sales', 'merchandising', 'inventory', 'pos',
               'customer relations', 'store management'],
}


def _cert_bonus(candidate: Dict[str, Any],
                jd: JobDescription) -> Tuple[float, List[str]]:
    """
    Bonus for relevant certifications and hackathon achievements.
    - Base certs: 0.15 per relevant cert (max 3.0)
    - Prestigious issuer certs: 0.25 per cert (max 3.0)
    - Hackathon participation: +0.5
    - Hackathon wins: +1.0
    Returns (bonus 0-5.0, list of relevant cert names).
    """
    certs = candidate.get('certifications', [])
    raw_text = (candidate.get('raw_text_sections', {}).get('full_text', '') or '').lower()

    # Build domain keywords from JD
    jd_text = f"{jd.title} {jd.department} {jd.description}".lower()
    all_jd_skills_lower = [s.lower() for s in jd.must_have_skills + jd.nice_to_have_skills]
    jd_keywords_lower = [k.lower() for k in jd.keywords]

    # Determine relevant domains
    relevant_domain_kws = set()
    for domain, kws in _CERT_DOMAIN_KEYWORDS.items():
        for kw in kws:
            if kw in jd_text or kw in ' '.join(all_jd_skills_lower):
                relevant_domain_kws.update(kws)
                break

    # If no domain matched, use all JD skills + keywords as relevance indicators
    if not relevant_domain_kws:
        relevant_domain_kws = set(all_jd_skills_lower + jd_keywords_lower)

    bonus = 0.0
    relevant = []

    for cert in certs:
        cert_name = (cert.get('name') or '').lower()
        cert_issuer = (cert.get('issuer') or '').lower()
        cert_full = f"{cert_name} {cert_issuer}"

        if not cert_name:
            continue

        # Check if cert is relevant to the JD domain
        is_relevant = any(kw in cert_full for kw in relevant_domain_kws)
        # Also check against JD skill names directly
        if not is_relevant:
            is_relevant = any(sk in cert_full for sk in all_jd_skills_lower)

        if not is_relevant:
            continue

        relevant.append(cert.get('name') or cert_name.title())

        # Check if from prestigious issuer
        is_prestigious = any(iss in cert_full for iss in _PRESTIGIOUS_CERT_ISSUERS)
        if is_prestigious:
            bonus += 0.25  # Higher weight for prestigious certs
        else:
            bonus += 0.15  # Base weight for relevant certs

    # ── Hackathon detection ───────────────────────────────────────────────
    hackathon_found = any(kw in raw_text for kw in _HACKATHON_KEYWORDS)
    hackathon_win = hackathon_found and any(kw in raw_text for kw in _WIN_KEYWORDS)

    # Also check cert names for hackathon mentions
    for cert in certs:
        cert_name = (cert.get('name') or '').lower()
        if any(kw in cert_name for kw in _HACKATHON_KEYWORDS):
            hackathon_found = True
            if any(kw in cert_name for kw in _WIN_KEYWORDS):
                hackathon_win = True

    if hackathon_win:
        bonus += 1.0
        relevant.append("🏆 Hackathon Winner")
    elif hackathon_found:
        bonus += 0.5
        relevant.append("🎯 Hackathon Participant")

    bonus = min(5.0, bonus)  # Cap at 5.0
    return round(bonus, 1), relevant


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection
# ─────────────────────────────────────────────────────────────────────────────

def _detect_anomalies(candidate: Dict[str, Any],
                      total_years: float,
                      jd: JobDescription) -> List[str]:
    """Flag potential anomalies in the candidate profile."""
    flags = []
    experience = candidate.get('experience', [])

    # Fresher (no experience at all)
    if not experience and total_years == 0:
        flags.append("FRESHER: No work experience")

    # Overqualified
    if jd.max_years < 99 and total_years > jd.max_years * 1.5:
        flags.append(f"OVERQUALIFIED: {total_years}yr exp vs {jd.max_years}yr max")

    # Employment gap: check for gaps > 6 months between jobs
    dates = []
    for exp in experience:
        start = _parse_date(exp.get('start'))
        end = _parse_date(exp.get('end'))
        if start and end:
            dates.append((start, end))
    if len(dates) >= 2:
        dates.sort(key=lambda x: x[0])
        for i in range(len(dates) - 1):
            gap = (dates[i + 1][0] - dates[i][1]).days
            if gap > 180:
                flags.append(f"GAP: {gap // 30}mo gap between jobs")
                break

    # Low extraction quality
    quality = candidate.get('extraction_quality', 1.0)
    if quality < 0.5:
        flags.append(f"LOW_QUALITY: Extraction quality {quality:.0%}, data may be incomplete")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# Main Scorer Class
# ─────────────────────────────────────────────────────────────────────────────

class CandidateScorer:
    """
    3-Phase candidate ranking engine with inference-aware skill matching.

    Usage:
        scorer = CandidateScorer()
        results = scorer.rank(jd, candidates)
    """

    def __init__(self):
        self._inference_engine = SkillInferenceEngine()
        self._domain_classifier = DomainClassifier(self._inference_engine)

    def rank(self, jd: JobDescription,
             candidates: List[Dict[str, Any]]) -> List[ScoredCandidate]:
        """
        Run the full 3-phase scoring pipeline.

        Args:
            jd: Structured job description
            candidates: List of extracted resume fields dicts

        Returns:
            List of ScoredCandidate sorted by final_score descending
        """
        # Pre-compute all candidate skills for BM25 IDF
        all_skills = [c.get('skills', []) for c in candidates]

        # Pre-compute IDF ONCE (was O(n²) when done per-candidate)
        all_jd_skills = list(set(jd.must_have_skills + jd.nice_to_have_skills))
        precomputed_idf = _precompute_bm25_idf(all_jd_skills, all_skills)

        # ── Domain pre-filter: skip clearly unrelated candidates ──────────
        # This prevents healthcare/legal/accounting candidates from polluting
        # engineering rankings. Only filter when we have high JD confidence.
        jd_domain, jd_conf = self._domain_classifier.classify_jd(
            jd.title, all_jd_skills, jd.description, jd.department
        )
        prox = _load_domain_proximity()
        penalties_matrix = prox.get('penalties', {})

        # Construction is related to civil engineering — never filter
        _RELATED_DOMAINS = {
            ('engineering', 'construction'),
            ('construction', 'engineering'),
        }

        filtered_candidates = []
        for candidate in candidates:
            cand_domain, cand_conf = self._domain_classifier.classify(candidate)

            # Only filter if BOTH sides have reasonable confidence
            if jd_conf >= 0.35 and cand_conf >= 0.35:
                pair = (jd_domain, cand_domain)
                if jd_domain != cand_domain and jd_domain != 'unknown' and cand_domain != 'unknown':
                    if pair not in _RELATED_DOMAINS:
                        jd_penalties = penalties_matrix.get(jd_domain, {})
                        penalty = jd_penalties.get(cand_domain, -50.0)
                        # Skip candidates with severe domain mismatch (penalty <= -60)
                        if penalty <= -60:
                            continue

            filtered_candidates.append(candidate)

        # Recompute all_skills for filtered set (for BM25 IDF)
        filtered_all_skills = [c.get('skills', []) for c in filtered_candidates]
        precomputed_idf = _precompute_bm25_idf(all_jd_skills, filtered_all_skills)

        results = []
        for candidate in filtered_candidates:
            result = self._score_candidate(jd, candidate, filtered_all_skills, precomputed_idf=precomputed_idf)
            results.append(result)

        # ── Phase 3: Rank & Explain ───────────────────────────────────────
        # Sort by final_score descending (knocked-out go to bottom)
        results.sort(key=lambda r: (not r.knocked_out, r.final_score), reverse=True)

        # Assign ranks
        for i, r in enumerate(results):
            r.rank = i + 1

        # Compute percentiles (among non-knocked-out)
        active = [r for r in results if not r.knocked_out]
        if active:
            max_score = active[0].final_score if active else 1.0
            for r in results:
                if r.knocked_out:
                    r.percentile = 0.0
                elif max_score > 0:
                    r.percentile = round((r.final_score / max_score) * 100.0, 1)
                else:
                    r.percentile = 0.0

        return results

    def _classify_jd_subdomain(self, jd: JobDescription) -> str:
        """Classify JD into engineering subdomain based on title/department."""
        title_lower = jd.title.lower()
        dept_lower = jd.department.lower()
        combined = f"{title_lower} {dept_lower}"

        # Direct mapping from common JD titles
        _JD_SUBDOMAIN_MAP = {
            'civil': 'civil',
            'structural': 'civil',
            'electrical': 'electrical',
            'mechanical': 'mechanical',
            'frontend': 'frontend',
            'front-end': 'frontend',
            'backend': 'backend',
            'back-end': 'backend',
            'full stack': 'fullstack',
            'fullstack': 'fullstack',
            'devops': 'devops',
            'sre': 'devops',
            'data engineer': 'data',
            'data scientist': 'ml',
            'ml engineer': 'ml',
            'machine learning': 'ml',
            'embedded': 'embedded',
            'firmware': 'embedded',
        }
        for keyword, subdomain in _JD_SUBDOMAIN_MAP.items():
            if keyword in combined:
                return subdomain
        return 'software'  # Default for unspecified engineering

    def _score_candidate(self, jd: JobDescription,
                         candidate: Dict[str, Any],
                         all_skills: List[List[str]],
                         precomputed_idf=None) -> ScoredCandidate:
        """Score a single candidate through Phase 1 and Phase 2."""
        pi = candidate.get('personal_info', {})
        name = pi.get('name') or 'Unknown'
        doc_id = candidate.get('_document_id', name)
        c_skills = candidate.get('skills', [])
        experience = candidate.get('experience', [])
        total_years = _compute_total_experience_years(experience)

        result = ScoredCandidate(
            name=name,
            document_id=doc_id,
            final_score=0.0,
            percentile=0.0,
            rank=0,
            knocked_out=False,
            knockout_reasons=[],
            total_exp_years=total_years,
            extraction_quality=candidate.get('extraction_quality', 0.0),
        )

        # ── Phase 2 Pre-compute: Inference Engine ─────────────────────────
        # Run inference matching BEFORE knockout so inferred skills can
        # satisfy must-have requirements.
        all_jd_skills = jd.must_have_skills + jd.nice_to_have_skills

        # Augment skills with JD skills found in targeted text sections only.
        skill_sections = self._get_skill_sections(candidate)
        augmented_skills = list(c_skills)
        for jd_sk in all_jd_skills:
            if not any(_skill_match(cs, jd_sk) for cs in augmented_skills):
                variants = _get_search_variants(jd_sk)
                found = False
                for variant in variants:
                    if len(variant) >= 3 and re.search(
                        r'\b' + re.escape(variant) + r'\b', skill_sections
                    ):
                        found = True
                        break
                if found:
                    augmented_skills.append(jd_sk)

        # Run inference engine for all JD skills
        inference_result = self._inference_engine.match_skills(
            augmented_skills, all_jd_skills
        )

        # Store inference results on the result object
        result.skill_matches = [m.to_dict() for m in inference_result.all_matches]
        result.matched_inferred = [m.skill for m in inference_result.inferred_skills]
        result.matched_related = [m.skill for m in inference_result.related_skills]

        # Domain classification (with subdomain for engineering)
        cand_domain, cand_subdomain, cand_conf = self._domain_classifier.classify_with_subdomain(candidate)
        result.candidate_domain = cand_domain
        result.domain_confidence = cand_conf
        result.candidate_subdomain = cand_subdomain

        # ── Phase 1: Hard Knockout (inference-aware) ──────────────────────
        ko_reasons = self._phase1_knockout(
            jd, candidate, c_skills, total_years, inference_result
        )
        if ko_reasons:
            result.knocked_out = True
            result.knockout_reasons = ko_reasons
            # DO NOT return early — compute Phase 2 sub-scores for reporting

        # ── Phase 2: Multi-Signal Scoring ─────────────────────────────────
        # Always compute sub-scores regardless of knockout status, so that
        # the UI can show actual skill/experience/keyword discrimination
        # even for knocked-out candidates.

        # Skill scoring (BM25) — use inference weights for fractional scoring
        result.skill_score = _bm25_skill_score(
            augmented_skills, all_jd_skills, all_skills,
            skill_weights=inference_result.skill_weights,
            precomputed_idf=precomputed_idf,
        )

        # Build matched/missing from inference results
        # Must-have: matched if weight >= WEIGHT_INFERRED (0.75)
        matched_must = []
        missing_must = []
        for sk in jd.must_have_skills:
            w = inference_result.skill_weights.get(sk, 0.0)
            if w >= WEIGHT_INFERRED:
                matched_must.append(sk)
            else:
                missing_must.append(sk)
        result.matched_must_have = matched_must
        result.missing_must_have = missing_must

        # Nice-to-have: any match (even related at 0.50) counts
        matched_nice = []
        for sk in jd.nice_to_have_skills:
            w = inference_result.skill_weights.get(sk, 0.0)
            if w > 0:
                matched_nice.append(sk)
        result.matched_nice_to_have = matched_nice

        # Extra skills (candidate has but JD doesn't mention)
        all_jd_set = set(s.lower() for s in all_jd_skills)
        result.extra_skills = [s for s in c_skills
                               if s.lower() not in all_jd_set
                               and not any(_skill_match(s, j) for j in all_jd_skills)]

        # Experience scoring
        result.experience_score, result.best_title_match = _experience_score(candidate, jd)

        # Keyword scoring
        result.keyword_score, result.matched_keywords, result.missing_keywords = \
            _keyword_score(candidate, jd)

        # Education scoring
        result.education_score, result.degree_level, result.degree_field = \
            _education_score(candidate, jd)

        # ── Bonus: Project-skill match ────────────────────────────────────
        result.project_bonus, result.project_skill_matches = \
            _project_skill_bonus(candidate, all_jd_skills)

        # ── Bonus: Prestigious companies ──────────────────────────────────
        result.prestige_bonus, result.prestigious_companies = \
            _prestige_bonus(candidate)

        # ── Bonus: Certifications & hackathons ────────────────────────────
        result.cert_bonus, result.relevant_certs = \
            _cert_bonus(candidate, jd)

        # ── Domain penalty (ONLY affects skill_score) ─────────────────────
        jd_domain, jd_conf = self._domain_classifier.classify_jd(
            jd.title, all_jd_skills, jd.description, jd.department
        )
        penalty = _get_domain_penalty(jd_domain, cand_domain, jd_conf, cand_conf)

        # ── Subdomain penalty for engineering JDs ─────────────────────────
        # If both JD and candidate are "engineering", apply subdomain penalty
        if jd_domain == 'engineering' and cand_domain == 'engineering' and penalty == 0.0:
            jd_subdomain = self._classify_jd_subdomain(jd)
            if jd_subdomain and cand_subdomain and jd_subdomain != cand_subdomain:
                prox = _load_domain_proximity()
                sub_penalties = prox.get('sub_domain_penalties', {})
                jd_sub_key = f'engineering.{jd_subdomain}'
                cand_sub_key = f'engineering.{cand_subdomain}'
                jd_sub_penalties = sub_penalties.get(jd_sub_key, {})
                subdomain_penalty = jd_sub_penalties.get(cand_sub_key, -30.0)
                if subdomain_penalty < 0:
                    penalty = float(subdomain_penalty)

        if penalty < 0:
            result.domain_penalty = penalty
            result.skill_score = max(0.0, result.skill_score * (1.0 + penalty / 100.0))

        # ── Weighted final score ──────────────────────────────────────────
        w = jd.weights
        skill_w = w.get('skills', 0.4)
        exp_w = w.get('experience', 0.25)
        kw_w = w.get('keywords', 0.2)
        edu_w = w.get('education', 0.15)

        # If JD has no keywords, redistribute keyword weight proportionally
        if not jd.keywords and kw_w > 0:
            remaining = skill_w + exp_w + edu_w
            if remaining > 0:
                skill_w = skill_w / remaining * (skill_w + exp_w + edu_w + kw_w)
                exp_w = exp_w / remaining * (w.get('skills', 0.4) + w.get('experience', 0.25) + w.get('education', 0.15) + kw_w)
                edu_w = edu_w / remaining * (w.get('skills', 0.4) + w.get('experience', 0.25) + w.get('education', 0.15) + kw_w)
                # Recalculate proportionally from originals
                orig_s, orig_e, orig_d = w.get('skills', 0.4), w.get('experience', 0.25), w.get('education', 0.15)
                total_non_kw = orig_s + orig_e + orig_d
                skill_w = orig_s / total_non_kw
                exp_w = orig_e / total_non_kw
                edu_w = orig_d / total_non_kw
            kw_w = 0.0

        result.skill_weighted = result.skill_score * skill_w
        result.experience_weighted = result.experience_score * exp_w
        result.keyword_weighted = result.keyword_score * kw_w
        result.education_weighted = result.education_score * edu_w

        base_score = (
            result.skill_weighted +
            result.experience_weighted +
            result.keyword_weighted +
            result.education_weighted
        )

        # Add bonuses on top (capped at 100)
        total_bonus = result.project_bonus + result.prestige_bonus + result.cert_bonus

        # If knocked out, zero the final score but keep sub-scores for reporting
        if result.knocked_out:
            result.final_score = 0.0
        else:
            result.final_score = round(min(100.0, base_score + total_bonus), 1)

        # Anomaly detection
        result.anomalies = _detect_anomalies(candidate, total_years, jd)

        return result

    def _get_skill_sections(self, candidate: Dict[str, Any]) -> str:
        """
        Extract only the skill-bearing text sections from a candidate.
        This prevents false-positive skill matches from URLs, footers,
        email addresses, and boilerplate text.
        """
        sections = candidate.get('raw_text_sections', {}) or {}
        parts = []

        # Structured skills list (most reliable)
        skills_list = candidate.get('skills', [])
        if skills_list:
            parts.append(' '.join(str(s) for s in skills_list))

        # Dedicated skills section text
        for key in ('skills', 'technical_skills', 'core_competencies',
                    'technologies', 'tools'):
            if sections.get(key):
                parts.append(str(sections[key]))

        # Summary / objective (candidates often list skills here)
        for key in ('summary', 'objective', 'profile', 'about'):
            if sections.get(key):
                parts.append(str(sections[key]))

        # Experience descriptions (skills in context)
        experience = candidate.get('experience', [])
        for exp in experience:
            desc = exp.get('description') or exp.get('responsibilities') or ''
            if desc:
                parts.append(str(desc))

        # Projects (technologies used)
        projects = candidate.get('projects', [])
        for proj in projects:
            tech = proj.get('technologies') or []
            if isinstance(tech, list):
                parts.append(' '.join(str(t) for t in tech))
            elif tech:
                parts.append(str(tech))
            desc = proj.get('description') or ''
            if desc:
                parts.append(str(desc))

        return ' '.join(parts).lower()

    def _phase1_knockout(self, jd: JobDescription,
                         candidate: Dict[str, Any],
                         c_skills: List[str],
                         total_years: float,
                         inference_result=None) -> List[str]:
        """
        Phase 1: Hard knockout checks (inference-aware).

        Inferred skills with weight >= 0.75 can satisfy must-have requirements.
        Related skills (weight 0.50) do NOT satisfy must-have requirements.

        Returns list of reasons (empty = passes).
        """
        reasons = []

        # ── Must-have skills check (inference-aware) ───────────────────────
        if jd.must_have_skills:
            _, missing = _find_matching_skills(c_skills, jd.must_have_skills)
            if missing:
                # Second chance: check SKILL-BEARING SECTIONS ONLY for missing
                # skills. We deliberately avoid full raw text here because URLs,
                # footers, email addresses, and boilerplate often contain tech
                # words (e.g. "node" in "linkedin.com/in/...", "react" in a
                # disclaimer) that produce false-positive skill matches.
                skill_sections_text = self._get_skill_sections(candidate)
                still_missing = []
                for sk in missing:
                    sk_lower = sk.lower().strip()

                    # Check inference engine: weight >= 0.75 satisfies must-have
                    if inference_result:
                        inferred_weight = inference_result.skill_weights.get(sk, 0.0)
                        if inferred_weight >= WEIGHT_INFERRED:
                            continue  # Satisfied via inference

                    # Only allow second-chance text matches for skills >= 4 chars
                    if len(sk_lower) >= 4:
                        variants = _get_search_variants(sk)
                        found_in_text = False
                        for variant in variants:
                            if len(variant) >= 3 and re.search(
                                r'\b' + re.escape(variant) + r'\b',
                                skill_sections_text
                            ):
                                found_in_text = True
                                break
                        if found_in_text:
                            continue  # Found in skill-bearing section — valid match
                    still_missing.append(sk)

                if still_missing:
                    reasons.append(
                        f"Missing must-have skills: {', '.join(still_missing)}"
                    )

                logger.debug(
                    "[KO-SKILLS] %s | missing_from_structured=%s | still_missing=%s",
                    candidate.get('personal_info', {}).get('name', 'Unknown'),
                    missing,
                    still_missing if missing else [],
                )

        # ── Minimum years check ───────────────────────────────────────────
        if jd.min_years > 0 and total_years < jd.min_years:
            experience = candidate.get('experience', [])
            n_entries = len(experience)

            # If candidate has multiple job entries, dates may just not be parseable
            # Don't knock out if they clearly have experience (>=2 roles)
            has_entries = n_entries >= 2

            # Also check raw text for "X years of experience" patterns
            raw_text_lc = (candidate.get('raw_text_sections', {})
                           .get('full_text', '') or '').lower()
            raw_years_match = re.search(
                r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)',
                raw_text_lc
            )
            raw_years = int(raw_years_match.group(1)) if raw_years_match else 0

            if not has_entries and raw_years < jd.min_years and total_years < jd.min_years * 0.5:
                reasons.append(
                    f"Insufficient experience: {total_years}yr vs {jd.min_years}yr required"
                )

        # ── Maximum years check (overqualified knockout) ──────────────────
        if jd.max_years < 99 and total_years > jd.max_years:
            # Hard knockout: candidate exceeds the maximum experience cap.
            # This is a constraint, not a preference — HR screening for
            # "0-2 years, junior role" should strictly exclude senior candidates.
            reasons.append(
                f"Exceeds maximum experience: {total_years}yr vs {jd.max_years}yr max"
            )

        # ── Required degree check ─────────────────────────────────────────
        if jd.required_degree and jd.required_degree.lower() not in ('any', 'none', ''):
            required_level = _parse_degree_level(jd.required_degree)
            education = candidate.get('education', [])
            best_level = 0
            for edu in education:
                level = _parse_degree_level(edu.get('degree') or '')
                best_level = max(best_level, level)

            # Also check raw text for degree mentions
            raw_text = (candidate.get('raw_text_sections', {}).get('full_text', '')).lower()
            for deg_key, deg_val in DEGREE_LEVELS.items():
                if deg_val >= required_level and deg_key in raw_text:
                    best_level = max(best_level, deg_val)
                    break

            if best_level < required_level and required_level > 0:
                reasons.append(
                    f"Degree requirement not met: has level {best_level}, needs {required_level} "
                    f"({jd.required_degree})"
                )

        return reasons


# ─────────────────────────────────────────────────────────────────────────────
# Pretty Print Results
# ─────────────────────────────────────────────────────────────────────────────

def print_rankings(results: List[ScoredCandidate], jd: JobDescription):
    """Pretty-print ranking results to console."""
    print(f"\n{'='*72}")
    print(f"  RANKING RESULTS — {jd.title}")
    print(f"  {len(results)} candidates analyzed | "
          f"Must-have: {jd.must_have_skills} | Min: {jd.min_years}yr")
    print(f"{'='*72}")

    for r in results:
        if r.knocked_out:
            print(f"\n  ❌ #{r.rank:2d}  {r.name:25s}  KNOCKED OUT")
            for reason in r.knockout_reasons:
                print(f"       → {reason}")
        else:
            bar_len = int(r.final_score / 5)
            bar = '█' * bar_len + '░' * (20 - bar_len)
            medal = '🏆' if r.rank == 1 else ('🥈' if r.rank == 2 else ('🥉' if r.rank == 3 else '  '))
            print(f"\n  {medal} #{r.rank:2d}  {r.name:25s}  {r.final_score:5.1f}%  {bar}")
            print(f"       Skills: {r.skill_score:.0f}×{jd.weights.get('skills',0.4):.0%}="
                  f"{r.skill_weighted:.1f}  |  Exp: {r.experience_score:.0f}×{jd.weights.get('experience',0.25):.0%}="
                  f"{r.experience_weighted:.1f}  |  KW: {r.keyword_score:.0f}×{jd.weights.get('keywords',0.2):.0%}="
                  f"{r.keyword_weighted:.1f}  |  Edu: {r.education_score:.0f}×{jd.weights.get('education',0.15):.0%}="
                  f"{r.education_weighted:.1f}")
            # Bonus line
            total_bonus = r.project_bonus + r.prestige_bonus + r.cert_bonus
            if total_bonus > 0:
                parts = []
                if r.project_bonus > 0:
                    parts.append(f"Proj:+{r.project_bonus}")
                if r.prestige_bonus > 0:
                    parts.append(f"Prestige:+{r.prestige_bonus}")
                if r.cert_bonus > 0:
                    parts.append(f"Cert:+{r.cert_bonus}")
                print(f"       ⭐ Bonus: {' | '.join(parts)} = +{total_bonus:.1f}")
            print(f"       Exp: {r.total_exp_years}yr | Degree: {r.degree_level or 'N/A'}")
            if r.matched_must_have:
                print(f"       ✅ Must-have: {', '.join(r.matched_must_have)}")
            if r.missing_must_have:
                print(f"       ⚠ Missing: {', '.join(r.missing_must_have)}")
            if r.matched_nice_to_have:
                print(f"       ✅ Nice-to-have: {', '.join(r.matched_nice_to_have)}")
            if r.project_skill_matches:
                print(f"       🔨 Projects use: {', '.join(r.project_skill_matches)}")
            if r.prestigious_companies:
                print(f"       🏢 Prestige: {', '.join(r.prestigious_companies)}")
            if r.relevant_certs:
                print(f"       📜 Certs: {', '.join(r.relevant_certs)}")
            if r.matched_keywords:
                print(f"       🔑 Keywords: {', '.join(r.matched_keywords)}")
            if r.missing_keywords:
                print(f"       🔑 Missing KW: {', '.join(r.missing_keywords)}")
            if r.anomalies:
                for a in r.anomalies:
                    print(f"       ⚠ {a}")

    print(f"\n{'='*72}")
    active = [r for r in results if not r.knocked_out]
    ko = [r for r in results if r.knocked_out]
    print(f"  ACTIVE: {len(active)} | KNOCKED OUT: {len(ko)}")
    if active:
        print(f"  TOP: {active[0].name} ({active[0].final_score:.1f}%)")
        print(f"  AVG: {sum(r.final_score for r in active)/len(active):.1f}%")
    print(f"{'='*72}\n")
