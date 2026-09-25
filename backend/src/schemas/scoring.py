"""
scoring.py — Scoring data models
==================================
Schemas for job descriptions and scored candidate results.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class JobDescription:
    """Structured Job Description for scoring."""
    title: str
    department: str = ""
    description: str = ""
    must_have_skills: List[str] = field(default_factory=list)
    nice_to_have_skills: List[str] = field(default_factory=list)
    min_years: int = 0
    max_years: int = 99
    required_degree: str = "any"       # "any", "associate", "bachelor", "master", "phd"
    preferred_field: str = ""          # e.g. "Computer Science"
    keywords: List[str] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "skills": 0.40,
        "experience": 0.25,
        "keywords": 0.20,
        "education": 0.15,
    })
    job_version: int = 1


@dataclass
class ScoredCandidate:
    """Result for a single candidate after scoring."""
    name: Optional[str]
    document_id: str
    final_score: float              # 0.0–100.0 (synonym for relevance_score for backwards compatibility)
    relevance_score: float = 0.0    # 0.0–100.0 policy-compliant candidate relevance
    percentile: float = 0.0         # 0.0–100.0 (computed in Phase 3)
    rank: int = 0                   # 1-based rank
    knocked_out: bool = False
    knockout_reasons: List[str] = field(default_factory=list)

    # Decision separation (Rule 3)
    eligibility_status: str = "ELIGIBLE"  # "ELIGIBLE" | "REVIEW_REQUIRED" | "DOES_NOT_MEET_CRITERIA"
    human_decision: str = "NEW"           # "NEW" | "REVIEWING" | "SHORTLISTED" | "REJECTED" | "INTERVIEW" | "ARCHIVED"

    # Identity resolution metadata
    identity_status: str = "VERIFIED"     # "VERIFIED" | "PLAUSIBLE" | "UNRESOLVED"
    identity_confidence: float = 1.0
    identity_provenance: Dict[str, Any] = field(default_factory=dict)

    # Version lineage & audit ledger (Rule 6)
    score_version: str = "2.2.0"
    policy_version: str = "2026.1"
    job_version: int = 1
    normalized_weights: Dict[str, float] = field(default_factory=dict)
    factor_ledger: List[Dict[str, Any]] = field(default_factory=list)

    email: str = ""
    phone: str = ""
    location: str = ""
    pdf_url: str = ""
    low_confidence_extraction: bool = False
    fallback_reason: Optional[str] = None


    # Phase 2 sub-scores (each 0.0–100.0 before weight)
    skill_score: float = 0.0
    experience_score: float = 0.0
    keyword_score: float = 0.0
    education_score: float = 0.0

    # Bonus scores (added on top of weighted score)
    project_bonus: float = 0.0       # Bonus for projects using JD skills
    prestige_bonus: float = 0.0      # Bonus for working at prestigious companies
    cert_bonus: float = 0.0          # Bonus for relevant certifications

    # Weighted contributions to final score
    skill_weighted: float = 0.0
    experience_weighted: float = 0.0
    keyword_weighted: float = 0.0
    education_weighted: float = 0.0

    # Breakdown details
    matched_must_have: List[str] = field(default_factory=list)
    missing_must_have: List[str] = field(default_factory=list)
    matched_nice_to_have: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    missing_keywords: List[str] = field(default_factory=list)
    extra_skills: List[str] = field(default_factory=list)
    project_skill_matches: List[str] = field(default_factory=list)
    prestigious_companies: List[str] = field(default_factory=list)
    relevant_certs: List[str] = field(default_factory=list)

    # Inference results (Phase 2)
    skill_matches: List[Dict] = field(default_factory=list)       # Full SkillMatchResult dicts
    matched_inferred: List[str] = field(default_factory=list)     # Inferred skill names
    matched_related: List[str] = field(default_factory=list)      # Related skill names

    # Domain classification (Phase 2)
    candidate_domain: str = ""
    candidate_subdomain: str = ""     # Engineering subdomain (civil/electrical/mechanical/software...)
    domain_confidence: float = 0.0
    domain_penalty: float = 0.0      # Applied penalty (0.0 = no penalty)

    total_exp_years: float = 0.0
    best_title_match: str = ""
    degree_level: str = ""
    degree_field: str = ""

    anomalies: List[str] = field(default_factory=list)
    extraction_quality: float = 0.0
    
    # Phase 3: ATS Score
    ats_score: float = 0.0
    ats_warnings: List[str] = field(default_factory=list)
