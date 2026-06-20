"""
scoring.py — Scoring data models
==================================
Schemas for job descriptions and scored candidate results.
"""

from dataclasses import dataclass, field
from typing import Dict, List


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


@dataclass
class ScoredCandidate:
    """Result for a single candidate after scoring."""
    name: str
    document_id: str
    final_score: float              # 0.0–100.0
    percentile: float               # 0.0–100.0 (computed in Phase 3)
    rank: int                       # 1-based rank
    knocked_out: bool
    knockout_reasons: List[str]

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

    total_exp_years: float = 0.0
    best_title_match: str = ""
    degree_level: str = ""
    degree_field: str = ""

    anomalies: List[str] = field(default_factory=list)
    extraction_quality: float = 0.0
