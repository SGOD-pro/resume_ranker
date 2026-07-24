"""
ranking/idf_table.py — Fixed Reference-Corpus IDF Table
=========================================================
ADR-04: IDF is computed ONCE from a synthetic reference corpus and loaded at
module import time. Score for a given candidate NEVER depends on who else is in
the current request's pool — that was the non-determinism bug in V1.

Public API
----------
get_idf(skill: str) -> float
    Returns the IDF value for a skill token. Unknown skills get the
    "unseen" IDF: log((N + 0.5) / 0.5) where N = corpus size.

CORPUS_SIZE: int
    Number of documents in the reference corpus.

Why synthetic corpus?
---------------------
Using the benchmark PDFs would create a runtime dependency on local files
and make IDF values tied to a specific data snapshot. A synthetic corpus
covering the same skill distribution is reproducible, self-contained, and
can always be rebuilt from real data if needed.
"""

from __future__ import annotations

import math
import re

from src.registries.skill_registry import match as _skill_match

# ---------------------------------------------------------------------------
# Synthetic Reference Corpus
# ---------------------------------------------------------------------------
# 500 representative skill sets covering 10 major domains.
# Distribution reflects real-world hiring volume (tech-heavy, then finance, etc.)

_CORPUS: list[list[str]] = []

# ── IT / Software (200 docs) ────────────────────────────────────────────────
_IT_SKILLS = [
    ["Python", "Django", "REST API", "PostgreSQL", "Docker"],
    ["JavaScript", "React", "Node.js", "TypeScript", "GraphQL"],
    ["Java", "Spring Boot", "Microservices", "Kafka", "Kubernetes"],
    ["AWS", "Lambda", "DynamoDB", "S3", "API Gateway"],
    ["Python", "FastAPI", "SQLAlchemy", "Redis", "Celery"],
    ["Go", "gRPC", "Kubernetes", "Prometheus", "Helm"],
    ["C++", "Embedded", "RTOS", "Linux", "CMake"],
    ["Python", "TensorFlow", "PyTorch", "Pandas", "NumPy"],
    ["Data Engineering", "Spark", "Airflow", "BigQuery", "dbt"],
    ["DevOps", "CI/CD", "Jenkins", "Terraform", "Ansible"],
    ["React", "Redux", "Webpack", "CSS", "HTML"],
    ["iOS", "Swift", "Xcode", "UIKit", "Core Data"],
    ["Android", "Kotlin", "Jetpack Compose", "Room", "Retrofit"],
    ["Cybersecurity", "Penetration Testing", "SIEM", "Nmap", "Burp Suite"],
    ["Machine Learning", "Scikit-learn", "XGBoost", "Feature Engineering", "A/B Testing"],
    ["PHP", "Laravel", "MySQL", "Vue.js", "REST API"],
    ["Ruby", "Rails", "Sidekiq", "PostgreSQL", "RSpec"],
    ["Scala", "Akka", "Spark", "Hadoop", "Hive"],
    ["Azure", "Azure DevOps", "ARM Templates", "Power BI", "Logic Apps"],
    ["GCP", "BigQuery", "Cloud Run", "Pub/Sub", "Dataflow"],
]
for i in range(200):
    _CORPUS.append(_IT_SKILLS[i % len(_IT_SKILLS)] + [f"Tool{i % 30}"])

# ── Finance / Banking (80 docs) ─────────────────────────────────────────────
_FIN_SKILLS = [
    ["CFA", "Financial Modeling", "Valuation", "Excel", "Bloomberg"],
    ["Risk Management", "Basel III", "VaR", "Credit Analysis", "Fixed Income"],
    ["Investment Banking", "M&A", "Due Diligence", "Pitch Decks", "LBO Modeling"],
    ["Accounting", "IFRS", "GAAP", "Audit", "SAP"],
    ["FRM", "Derivatives", "Options", "Hedging", "Quantitative Analysis"],
    ["Python", "Quantitative Finance", "Algorithmic Trading", "NumPy", "Backtesting"],
    ["Compliance", "AML", "KYC", "Regulatory Reporting", "FATCA"],
    ["Private Equity", "Portfolio Management", "Fund Accounting", "Carry", "EBITDA"],
]
for i in range(80):
    _CORPUS.append(_FIN_SKILLS[i % len(_FIN_SKILLS)])

# ── Marketing / Growth (60 docs) ────────────────────────────────────────────
_MKT_SKILLS = [
    ["SEO", "SEM", "Google Analytics", "Content Marketing", "HubSpot"],
    ["Digital Marketing", "Social Media", "Paid Ads", "Facebook Ads", "Copywriting"],
    ["Email Marketing", "Mailchimp", "A/B Testing", "Marketing Automation", "CRM"],
    ["Brand Management", "Market Research", "Campaign Management", "PR", "Storytelling"],
    ["Performance Marketing", "ROI", "Google Ads", "Retargeting", "Conversion Rate Optimization"],
    ["Product Marketing", "Go-to-Market", "Competitive Analysis", "Positioning", "Salesforce"],
]
for i in range(60):
    _CORPUS.append(_MKT_SKILLS[i % len(_MKT_SKILLS)])

# ── Engineering / Non-IT (50 docs) ──────────────────────────────────────────
_ENG_SKILLS = [
    ["AutoCAD", "SolidWorks", "Mechanical Design", "FEA", "GD&T"],
    ["Civil Engineering", "AutoCAD Civil 3D", "Structural Analysis", "STAAD.Pro", "Project Management"],  # noqa: E501
    ["Electrical Engineering", "PLC", "SCADA", "HMI", "Circuit Design"],
    ["Manufacturing", "Lean", "Six Sigma", "FMEA", "SPC"],
    ["Chemical Engineering", "Process Simulation", "HAZOP", "Aspen Plus", "P&ID"],
]
for i in range(50):
    _CORPUS.append(_ENG_SKILLS[i % len(_ENG_SKILLS)])

# ── Healthcare (30 docs) ────────────────────────────────────────────────────
_HC_SKILLS = [
    ["Clinical Research", "ICH GCP", "SAS", "Protocol Development", "IRB"],
    ["Nursing", "Patient Care", "ICU", "EMR", "HIPAA"],
    ["Pharmacy", "Pharmacovigilance", "Drug Safety", "FDA Regulations", "Clinical Trials"],
]
for i in range(30):
    _CORPUS.append(_HC_SKILLS[i % len(_HC_SKILLS)])

# ── HR / People (20 docs) ───────────────────────────────────────────────────
_HR_SKILLS = [
    ["Talent Acquisition", "HRIS", "Onboarding", "Performance Management", "LinkedIn Recruiter"],
    ["HR Business Partner", "Employee Relations", "Compensation & Benefits", "SHRM", "Labor Law"],
]
for i in range(20):
    _CORPUS.append(_HR_SKILLS[i % len(_HR_SKILLS)])

# ── Legal (20 docs) ─────────────────────────────────────────────────────────
_LGL_SKILLS = [
    ["Contract Drafting", "Corporate Law", "M&A", "Due Diligence", "Negotiation"],
    ["Intellectual Property", "Patent Filing", "Trademark", "Copyright", "Licensing"],
]
for i in range(20):
    _CORPUS.append(_LGL_SKILLS[i % len(_LGL_SKILLS)])

# ── Data & Analytics (30 docs) ──────────────────────────────────────────────
_DA_SKILLS = [
    ["SQL", "Tableau", "Power BI", "Excel", "Data Visualization"],
    ["Python", "R", "Statistics", "Regression", "Hypothesis Testing"],
    ["Business Intelligence", "ETL", "Data Warehousing", "Looker", "Mode"],
]
for i in range(30):
    _CORPUS.append(_DA_SKILLS[i % len(_DA_SKILLS)])

# ── Sales (10 docs) ─────────────────────────────────────────────────────────
_SALES_SKILLS = [
    ["B2B Sales", "Salesforce", "Pipeline Management", "Account Management", "Cold Calling"],
    ["Enterprise Sales", "SaaS", "Negotiation", "Demo", "Quota Attainment"],
]
for i in range(10):
    _CORPUS.append(_SALES_SKILLS[i % len(_SALES_SKILLS)])

CORPUS_SIZE: int = len(_CORPUS)


# ---------------------------------------------------------------------------
# IDF Computation
# ---------------------------------------------------------------------------

def _build_idf_table(corpus: list[list[str]]) -> dict[str, float]:
    """
    Build IDF table from a skill corpus.

    IDF(skill) = log((N - df + 0.5) / (df + 0.5) + 1)
    where df = number of documents containing the skill.

    This is the smoothed BM25 IDF formula — same as V1's bm25_scorer.py.
    """
    n = len(corpus)
    # Collect all unique skills
    all_skills: set[str] = set()
    for doc in corpus:
        all_skills.update(doc)

    idf: dict[str, float] = {}
    for skill in all_skills:
        df = sum(
            1 for doc in corpus
            if any(_skill_match(s, skill) for s in doc)
        )
        idf[skill] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    return idf


# Build the table at import time (runs once per Lambda cold start)
_IDF_TABLE: dict[str, float] = _build_idf_table(_CORPUS)

# IDF for a skill that appears in ZERO reference documents
# log((N + 0.5) / 0.5 + 1) — maximum possible IDF
_UNSEEN_IDF: float = math.log((CORPUS_SIZE + 0.5) / 0.5 + 1.0)


def get_idf(skill: str) -> float:
    """
    Return the fixed reference-corpus IDF for a skill.

    Normalisation: tries exact match first, then skill_registry alias match.
    Unknown skills get _UNSEEN_IDF (treated as maximally rare — no penalty for
    being specific, only for being common).
    """
    # Exact match
    if skill in _IDF_TABLE:
        return _IDF_TABLE[skill]

    # Alias / normalised match against all corpus skills
    for corpus_skill, idf_val in _IDF_TABLE.items():
        if _skill_match(skill, corpus_skill):
            return idf_val

    return _UNSEEN_IDF


def normalise_skill(s: str) -> str:
    """Lowercase + strip for consistent lookup."""
    return re.sub(r"\s+", " ", s.strip().lower())
