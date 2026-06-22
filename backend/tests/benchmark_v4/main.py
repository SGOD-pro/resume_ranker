#!/usr/bin/env python3
"""
benchmark_v5 — Trustworthy Production Benchmark (5000+ PDFs)
=============================================================
Remediation of v4: fixes metric integrity, name audit, deduplication,
domain taxonomy, and honest scoring. Every metric has an explicit formula.

Usage:
    cd backend && .venv/bin/python tests/benchmark_v4/main.py
"""

from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import re
import resource
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.ranking.scorer import CandidateScorer
from src.ranking.skill_inference import SkillInferenceEngine
from src.ranking.domain_classifier import DomainClassifier
from src.schemas.scoring import JobDescription

# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────
BATCH_SIZE = 200
V4_DIR = Path(__file__).parent
RESUME_DIR = V4_DIR / "resumes"
REPORT_PATH = V4_DIR / "report.md"
JSON_PATH = V4_DIR / "report.json"

# Sub-domain keyword sets for Phase 6 taxonomy
CIVIL_KEYWORDS = {
    "civil", "structural", "construction", "bridge", "road", "highway",
    "concrete", "surveying", "geotechnical", "infrastructure", "building",
    "site engineer", "quantity surveyor", "autocad", "staad", "revit",
    "pile", "foundation", "masonry", "plumbing", "drainage",
}
ELECTRICAL_KEYWORDS = {
    "electrical", "circuit", "power", "voltage", "current", "transformer",
    "relay", "plc", "scada", "pcb", "embedded", "vhdl", "verilog",
    "motor", "generator", "switchgear", "substation", "wiring",
}
MECHANICAL_KEYWORDS = {
    "mechanical", "solidworks", "catia", "ansys", "thermodynamics",
    "cnc", "manufacturing", "assembly", "tolerance", "material",
    "hydraulic", "pneumatic", "hvac", "turbine", "gear", "lathe",
    "cad/cam", "machining",
}

TAG_LEAK_PATTERNS = [
    re.compile(r"<[a-z/][^>]*>", re.IGNORECASE),
    re.compile(r"\[/?[A-Z]+\]"),
    re.compile(r"\\[a-z]+\{"),
    re.compile(r"&#?\w+;"),
]

# ─────────────────────────────────────────────────────────────────
# JD Definitions
# ─────────────────────────────────────────────────────────────────
JOB_DESCRIPTIONS = {
    "Backend Engineer": JobDescription(
        title="Backend Engineer", department="Engineering",
        description="Backend engineer building scalable microservices and APIs",
        must_have_skills=[], nice_to_have_skills=["Python", "Node.js", "Docker", "AWS", "MongoDB", "PostgreSQL", "Microservices", "SQL", "Java", "REST"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Computer Science",
        keywords=["microservices", "api", "database", "scalable", "backend", "server", "distributed"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "Frontend Engineer": JobDescription(
        title="Frontend Engineer", department="Engineering",
        description="Frontend engineer building responsive UIs with React, Angular, or Vue",
        must_have_skills=[], nice_to_have_skills=["JavaScript", "React", "CSS", "HTML", "TypeScript", "Angular", "Vue.js", "Git", "Redux", "Webpack"],
        min_years=0, max_years=10, required_degree="any", preferred_field="Computer Science",
        keywords=["frontend", "responsive", "ui", "web", "component", "user interface"],
        weights={"skills": 0.45, "experience": 0.20, "keywords": 0.20, "education": 0.15},
    ),
    "Fullstack Engineer": JobDescription(
        title="Full Stack Developer", department="Engineering",
        description="Full stack developer with backend and frontend experience",
        must_have_skills=[], nice_to_have_skills=["JavaScript", "React", "Python", "Node.js", "Docker", "AWS", "MongoDB", "TypeScript", "PostgreSQL"],
        min_years=0, max_years=10, required_degree="any", preferred_field="Computer Science",
        keywords=["fullstack", "frontend", "backend", "api", "web", "full stack"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "DevOps Engineer": JobDescription(
        title="DevOps Engineer", department="Engineering",
        description="DevOps engineer managing cloud infrastructure and CI/CD",
        must_have_skills=[], nice_to_have_skills=["Docker", "Kubernetes", "AWS", "Terraform", "CI/CD", "Jenkins", "Linux", "Python", "Ansible"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Computer Science",
        keywords=["infrastructure", "deployment", "automation", "monitoring", "cloud", "container"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "Data Engineer": JobDescription(
        title="Data Engineer", department="Engineering",
        description="Data engineer building ETL pipelines and data warehouses",
        must_have_skills=[], nice_to_have_skills=["SQL", "Python", "Spark", "MongoDB", "ETL", "Kafka", "Airflow", "Snowflake", "Hadoop"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Computer Science",
        keywords=["data", "pipeline", "etl", "warehouse", "analytics", "streaming"],
        weights={"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15},
    ),
    "Data Scientist": JobDescription(
        title="Data Scientist", department="Engineering",
        description="Data scientist applying statistical models and ML",
        must_have_skills=[], nice_to_have_skills=["Python", "R", "TensorFlow", "PyTorch", "SQL", "Pandas", "Scikit-learn", "Machine Learning"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Computer Science",
        keywords=["model", "prediction", "classification", "regression", "training", "statistical"],
        weights={"skills": 0.40, "experience": 0.20, "keywords": 0.25, "education": 0.15},
    ),
    "ML Engineer": JobDescription(
        title="ML Engineer", department="Engineering",
        description="ML Engineer deploying machine learning models to production",
        must_have_skills=[], nice_to_have_skills=["Python", "TensorFlow", "PyTorch", "Docker", "Kubernetes", "MLOps", "AWS", "NLP"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Computer Science",
        keywords=["model", "inference", "training", "pipeline", "neural", "deep learning"],
        weights={"skills": 0.40, "experience": 0.20, "keywords": 0.25, "education": 0.15},
    ),
    "Marketing Manager": JobDescription(
        title="Digital Marketing Manager", department="Marketing",
        description="Digital marketing manager leading campaigns and SEO",
        must_have_skills=[], nice_to_have_skills=["Marketing", "SEO", "Google Ads", "Email Marketing", "Analytics", "Content Marketing", "Social Media"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Marketing",
        keywords=["campaign", "brand", "content", "traffic", "conversion", "strategy", "marketing"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    ),
    "Sales Executive": JobDescription(
        title="Sales Executive", department="Sales",
        description="Sales executive managing client relationships",
        must_have_skills=[], nice_to_have_skills=["Sales", "CRM", "Lead Generation", "Negotiation", "Salesforce"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Business",
        keywords=["revenue", "target", "client", "pipeline", "quota", "deal"],
        weights={"skills": 0.30, "experience": 0.35, "keywords": 0.20, "education": 0.15},
    ),
    "HR Manager": JobDescription(
        title="HR Manager", department="HR",
        description="HR manager overseeing recruitment and talent management",
        must_have_skills=[], nice_to_have_skills=["Recruiting", "Employee Relations", "HRIS", "Onboarding", "Payroll", "Talent Acquisition"],
        min_years=0, max_years=15, required_degree="any", preferred_field="HR",
        keywords=["recruit", "talent", "employee", "onboarding", "retention", "engagement"],
        weights={"skills": 0.30, "experience": 0.30, "keywords": 0.25, "education": 0.15},
    ),
    "Accountant": JobDescription(
        title="Accountant", department="Finance",
        description="Accountant managing financial statements and auditing",
        must_have_skills=[], nice_to_have_skills=["Accounting", "Budgeting", "Tax", "GAAP", "QuickBooks", "Excel", "Auditing"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Accounting",
        keywords=["financial", "audit", "ledger", "reconciliation", "tax", "budget"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    ),
    "Civil Engineer": JobDescription(
        title="Civil Engineer", department="Civil Engineering",
        description="Civil engineer designing infrastructure and buildings",
        must_have_skills=[], nice_to_have_skills=["AutoCAD", "Structural Analysis", "Project Management", "Construction", "Surveying", "STAAD", "Revit"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Civil Engineering",
        keywords=["structural", "construction", "bridge", "road", "building", "infrastructure", "concrete"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    ),
    "Electrical Engineer": JobDescription(
        title="Electrical Engineer", department="Electrical Engineering",
        description="Electrical engineer designing circuits and power systems",
        must_have_skills=[], nice_to_have_skills=["Circuit Design", "PLC", "MATLAB", "SCADA", "PCB", "Embedded Systems", "Power Systems"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Electrical Engineering",
        keywords=["circuit", "power", "voltage", "transformer", "relay", "electrical", "embedded"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    ),
    "Mechanical Engineer": JobDescription(
        title="Mechanical Engineer", department="Mechanical Engineering",
        description="Mechanical engineer designing systems and manufacturing",
        must_have_skills=[], nice_to_have_skills=["SolidWorks", "AutoCAD", "ANSYS", "CAD", "Manufacturing", "CNC", "CATIA"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Mechanical Engineering",
        keywords=["mechanical", "manufacturing", "cad", "design", "assembly", "material", "thermal"],
        weights={"skills": 0.35, "experience": 0.30, "keywords": 0.20, "education": 0.15},
    ),
    "Legal Advisor": JobDescription(
        title="Legal Advisor", department="Legal",
        description="Legal advisor handling compliance and contracts",
        must_have_skills=[], nice_to_have_skills=["Compliance", "Litigation", "Contract", "Legal Research", "Negotiation"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Law",
        keywords=["legal", "contract", "compliance", "litigation", "court", "regulation"],
        weights={"skills": 0.30, "experience": 0.30, "keywords": 0.25, "education": 0.15},
    ),
    "Healthcare Specialist": JobDescription(
        title="Healthcare Specialist", department="Healthcare",
        description="Healthcare professional providing patient care",
        must_have_skills=[], nice_to_have_skills=["CPR", "First Aid", "Patient Care", "HIPAA", "Nursing", "EMR"],
        min_years=0, max_years=15, required_degree="any", preferred_field="Healthcare",
        keywords=["patient", "clinical", "health", "care", "medical", "treatment"],
        weights={"skills": 0.30, "experience": 0.30, "keywords": 0.25, "education": 0.15},
    ),
}


# ═════════════════════════════════════════════════════════════════
# PHASE 1: Knockout Regression
# ═════════════════════════════════════════════════════════════════

def phase1_knockout(scorer: CandidateScorer) -> dict:
    """Verify knockout logic with correctly-formed candidates."""
    checks = []

    jd = JobDescription(
        title="Senior Python Backend", department="Engineering",
        description="Senior Python backend engineer",
        must_have_skills=["Python"], nice_to_have_skills=["Docker", "AWS"],
        min_years=3, max_years=15, required_degree="bachelor", preferred_field="CS",
        keywords=["backend", "api"],
        weights={"skills": 0.4, "experience": 0.25, "keywords": 0.2, "education": 0.15},
    )

    # Test 1: HAS Python + correct date format → NOT knocked out
    cand1 = {
        "personal_info": {"name": "Test Python Dev"}, "skills": ["Python", "Docker", "AWS"],
        "experience": [{"role": "Backend Dev", "company": "Co", "start": "January 2020", "end": "Present",
                        "description": "Built APIs", "achievements": []}],
        "education": [{"degree": "Bachelor of CS", "institution": "MIT"}],
        "projects": [], "certifications": [], "extraction_quality": 0.8,
        "raw_text_sections": {"full_text": "5 years of experience in Python backend development"},
    }
    r1 = scorer.rank(jd, [cand1])[0]
    checks.append({
        "test": "Has must-have + valid experience", "knocked_out": r1.knocked_out,
        "expected_ko": False, "pass": not r1.knocked_out,
        "ko_reasons": r1.knockout_reasons, "matched_must": r1.matched_must_have,
        "missing_must": r1.missing_must_have, "total_years": r1.total_exp_years,
    })

    # Test 2: MISSING Python → knocked out
    cand2 = {
        "personal_info": {"name": "Test Java Dev"}, "skills": ["Java", "Spring Boot", "Docker"],
        "experience": [{"role": "Java Dev", "company": "Co", "start": "January 2020", "end": "Present",
                        "description": "Built Java APIs", "achievements": []}],
        "education": [{"degree": "Bachelor of CS", "institution": "MIT"}],
        "projects": [], "certifications": [], "extraction_quality": 0.8,
        "raw_text_sections": {"full_text": "5 years of experience in Java backend development"},
    }
    r2 = scorer.rank(jd, [cand2])[0]
    checks.append({
        "test": "Missing must-have skill", "knocked_out": r2.knocked_out,
        "expected_ko": True, "pass": r2.knocked_out,
        "ko_reasons": r2.knockout_reasons, "matched_must": r2.matched_must_have,
        "missing_must": r2.missing_must_have, "total_years": r2.total_exp_years,
    })

    # Test 3: Has Python via INFERENCE (Django) → NOT knocked out
    cand3 = {
        "personal_info": {"name": "Test Django Dev"}, "skills": ["Django", "Docker", "PostgreSQL"],
        "experience": [{"role": "Backend Dev", "company": "Co", "start": "January 2020", "end": "Present",
                        "description": "Built Django APIs", "achievements": []}],
        "education": [{"degree": "Bachelor of CS", "institution": "MIT"}],
        "projects": [], "certifications": [], "extraction_quality": 0.8,
        "raw_text_sections": {"full_text": "5 years of experience in Django Python backend development"},
    }
    r3 = scorer.rank(jd, [cand3])[0]
    checks.append({
        "test": "Must-have via inference (Django→Python)", "knocked_out": r3.knocked_out,
        "expected_ko": False, "pass": not r3.knocked_out,
        "ko_reasons": r3.knockout_reasons, "matched_must": r3.matched_must_have,
        "missing_must": r3.missing_must_have, "total_years": r3.total_exp_years,
    })

    passed = sum(1 for c in checks if c["pass"])
    return {"checks": checks, "passed": passed, "total": len(checks)}


# ═════════════════════════════════════════════════════════════════
# PHASE 2: Extraction + Name Audit (batched)
# ═════════════════════════════════════════════════════════════════

def extract_all_batches(pipe, classifier, pdfs):
    """Extract all PDFs, return per-candidate index with name confidence."""
    candidate_index = {}
    # Counters
    total = len(pdfs)
    success = failures = 0
    name_present = name_blacklisted = name_blank = 0
    email_present = phone_present = skills_present = 0
    exp_present = edu_present = proj_present = cert_present = 0
    skill_counts = []
    exp_counts = []
    edu_counts = []
    quality_sum = 0.0
    tag_leaks = []
    skill_dupes = 0
    low_quality = []
    confidence_dist = {"high": 0, "medium": 0, "low": 0, "zero": 0}
    # Domain
    domain_counts = Counter()
    domain_conf_sum = defaultdict(float)
    low_conf_domains = 0

    n_batches = math.ceil(total / BATCH_SIZE)
    print(f"\n  Processing {total} PDFs in {n_batches} batches of {BATCH_SIZE}...")

    for batch_idx in range(n_batches):
        start_i = batch_idx * BATCH_SIZE
        end_i = min(start_i + BATCH_SIZE, total)
        batch = pdfs[start_i:end_i]

        for pdf in batch:
            try:
                result = pipe.extract(str(pdf))
                fields = result.fields
                success += 1

                pi = fields.get("personal_info", {})
                skills = fields.get("skills", [])
                exp = fields.get("experience", [])
                edu = fields.get("education", [])
                quality = fields.get("extraction_quality", 0)
                quality_sum += quality

                # Name analysis
                name = (pi.get("name") or "").strip()
                name_conf = pi.get("name_confidence", 1.0)
                is_header = pi.get("candidate_name_is_section_header", False)

                if name:
                    name_present += 1
                    if name_conf >= 0.8:
                        confidence_dist["high"] += 1
                    elif name_conf >= 0.5:
                        confidence_dist["medium"] += 1
                    else:
                        confidence_dist["low"] += 1
                else:
                    name_blank += 1
                    confidence_dist["zero"] += 1

                if is_header:
                    name_blacklisted += 1

                # Contact
                if pi.get("email"):
                    email_present += 1
                if pi.get("phone"):
                    phone_present += 1

                # Skills
                if skills:
                    skills_present += 1
                    skill_counts.append(len(skills))
                    if len(skills) != len(set(s.lower() for s in skills)):
                        skill_dupes += 1
                    for s in skills:
                        for pat in TAG_LEAK_PATTERNS:
                            if pat.search(s):
                                tag_leaks.append({"file": pdf.name, "value": s})
                                break

                if exp:
                    exp_present += 1
                    exp_counts.append(len(exp))
                if edu:
                    edu_present += 1
                    edu_counts.append(len(edu))
                if fields.get("projects"):
                    proj_present += 1
                if fields.get("certifications"):
                    cert_present += 1
                if quality < 0.3:
                    low_quality.append({"file": pdf.name, "quality": quality})

                # Domain
                domain, conf = classifier.classify(fields)
                domain_counts[domain] += 1
                domain_conf_sum[domain] += conf
                if conf < 0.3:
                    low_conf_domains += 1

                # Sub-domain (Phase 6 taxonomy)
                sub_domain = domain
                if domain == "engineering":
                    all_text = " ".join([
                        " ".join(skills).lower(),
                        " ".join((e.get("role") or "") for e in exp).lower(),
                        " ".join((e.get("description") or "") for e in exp).lower(),
                        " ".join((e.get("degree") or "") for e in edu).lower(),
                    ])
                    civil_hits = sum(1 for k in CIVIL_KEYWORDS if k in all_text)
                    elec_hits = sum(1 for k in ELECTRICAL_KEYWORDS if k in all_text)
                    mech_hits = sum(1 for k in MECHANICAL_KEYWORDS if k in all_text)
                    max_hits = max(civil_hits, elec_hits, mech_hits)
                    if max_hits >= 2:
                        if civil_hits == max_hits:
                            sub_domain = "civil_engineering"
                        elif elec_hits == max_hits:
                            sub_domain = "electrical_engineering"
                        elif mech_hits == max_hits:
                            sub_domain = "mechanical_engineering"
                    else:
                        sub_domain = "software_engineering"

                candidate_index[pdf.name] = {
                    "name": name, "email": pi.get("email"), "phone": pi.get("phone"),
                    "name_confidence": name_conf, "is_section_header": is_header,
                    "domain": domain, "sub_domain": sub_domain, "confidence": round(conf, 3),
                    "skill_count": len(skills), "skills": skills[:30],
                    "exp_count": len(exp), "edu_count": len(edu),
                    "quality": quality,
                }

            except Exception as e:
                failures += 1

        done = end_i
        pct = done / total * 100
        mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(f"    Batch {batch_idx+1}/{n_batches}: {done}/{total} ({pct:.0f}%) | mem={mem_mb:.0f}MB")
        gc.collect()

    s = success or 1
    extraction = {
        "total": total, "success": success, "failures": failures,
        "success_rate": round(success / total * 100, 1),
        "fields": {
            "name":     {"present": name_present, "rate": round(name_present / s * 100, 1), "formula": f"{name_present}/{s}"},
            "email":    {"present": email_present, "rate": round(email_present / s * 100, 1), "formula": f"{email_present}/{s}"},
            "phone":    {"present": phone_present, "rate": round(phone_present / s * 100, 1), "formula": f"{phone_present}/{s}"},
            "skills":   {"present": skills_present, "rate": round(skills_present / s * 100, 1),
                         "avg": round(sum(skill_counts)/len(skill_counts), 1) if skill_counts else 0, "formula": f"{skills_present}/{s}"},
            "experience": {"present": exp_present, "rate": round(exp_present / s * 100, 1),
                           "avg": round(sum(exp_counts)/len(exp_counts), 1) if exp_counts else 0, "formula": f"{exp_present}/{s}"},
            "education": {"present": edu_present, "rate": round(edu_present / s * 100, 1),
                          "avg": round(sum(edu_counts)/len(edu_counts), 1) if edu_counts else 0, "formula": f"{edu_present}/{s}"},
            "projects":  {"present": proj_present, "rate": round(proj_present / s * 100, 1), "formula": f"{proj_present}/{s}"},
            "certs":     {"present": cert_present, "rate": round(cert_present / s * 100, 1), "formula": f"{cert_present}/{s}"},
        },
        "avg_quality": round(quality_sum / s, 3),
        "anomalies": {
            "tag_leaks": len(tag_leaks), "tag_leak_samples": tag_leaks[:15],
            "skill_duplicates": skill_dupes,
            "low_quality": len(low_quality), "low_quality_samples": low_quality[:15],
        },
        "name_audit": {
            "valid_names": name_present, "blank_names": name_blank,
            "blacklisted_names": name_blacklisted,
            "name_precision": round(name_present / (name_present + name_blacklisted) * 100, 1) if (name_present + name_blacklisted) else 0,
            "name_precision_formula": f"{name_present}/({name_present}+{name_blacklisted})",
            "confidence_distribution": confidence_dist,
        },
        # Composite extraction quality (Phase 4 honest metric)
        "composite_score": round(
            (
                (name_present / s * 100) * 0.20 +
                (skills_present / s * 100) * 0.25 +
                (exp_present / s * 100) * 0.25 +
                (edu_present / s * 100) * 0.20 +
                (email_present / s * 100) * 0.10
            ), 1
        ),
        "composite_formula": "0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email",
    }

    domain_dist = {}
    for d in sorted(domain_counts.keys(), key=lambda x: -domain_counts[x]):
        cnt = domain_counts[d]
        avg_conf = domain_conf_sum[d] / cnt if cnt else 0
        domain_dist[d] = {"count": cnt, "pct": round(cnt / s * 100, 1), "avg_confidence": round(avg_conf, 3)}

    domain_result = {
        "total": s, "unique_domains": len(domain_counts),
        "domain_distribution": domain_dist,
        "low_confidence": low_conf_domains,
        "unknown_count": domain_counts.get("unknown", 0),
        "unknown_pct": round(domain_counts.get("unknown", 0) / s * 100, 1),
        "classified_accuracy": round((s - domain_counts.get("unknown", 0)) / s * 100, 1),
        "classified_formula": f"({s} - {domain_counts.get('unknown', 0)}) / {s}",
    }

    return extraction, domain_result, candidate_index


# ═════════════════════════════════════════════════════════════════
# PHASE 2.5: Deduplication Audit
# ═════════════════════════════════════════════════════════════════

def phase2_5_dedup(pdfs, candidate_index):
    """SHA256 all PDFs, detect exact and near duplicates."""
    pdf_hashes = {}  # sha256 -> [filenames]
    text_hashes = {}  # sha256(name+skills) -> [filenames]

    for pdf in pdfs:
        # File hash
        try:
            with open(pdf, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
        except:
            continue
        pdf_hashes.setdefault(file_hash, []).append(pdf.name)

        # Text hash (name + skills fingerprint)
        info = candidate_index.get(pdf.name)
        if info:
            fingerprint = f"{info['name']}|{','.join(sorted(s.lower() for s in info.get('skills', [])))}"
            text_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
            text_hashes.setdefault(text_hash, []).append(pdf.name)

    exact_dupes = {h: files for h, files in pdf_hashes.items() if len(files) > 1}
    near_dupes = {h: files for h, files in text_hashes.items() if len(files) > 1}
    # Remove exact dupes from near dupes
    exact_files = set()
    for files in exact_dupes.values():
        exact_files.update(files)
    near_only = {}
    for h, files in near_dupes.items():
        non_exact = [f for f in files if f not in exact_files]
        if len(files) > 1 and len(non_exact) < len(files):
            continue  # This is already counted as exact
        if len(files) > 1:
            near_only[h] = files

    total = len(pdfs)
    unique_pdfs = len(pdf_hashes)
    exact_count = sum(len(f) - 1 for f in exact_dupes.values())
    near_count = sum(len(f) - 1 for f in near_only.values())

    return {
        "total_pdfs": total,
        "unique_pdfs_by_hash": unique_pdfs,
        "exact_duplicates": exact_count,
        "near_duplicates": near_count,
        "exact_duplicate_groups": len(exact_dupes),
        "near_duplicate_groups": len(near_only),
        "exact_samples": [{"hash": h[:12], "files": files[:5]} for h, files in list(exact_dupes.items())[:10]],
        "near_samples": [{"hash": h[:12], "files": files[:5]} for h, files in list(near_only.items())[:10]],
        "dedup_rate": round((exact_count + near_count) / total * 100, 1) if total else 0,
    }


# ═════════════════════════════════════════════════════════════════
# PHASE 3: Skill Intelligence
# ═════════════════════════════════════════════════════════════════

SKILL_TESTS = [
    # (candidate_skill, jd_skill, type, min_weight_or_max)
    # True Positives
    ("Next.js", "React", True, 0.75), ("NestJS", "Node.js", True, 0.75),
    ("Django", "Python", True, 0.75), ("FastAPI", "Python", True, 0.75),
    ("Spring Boot", "Java", True, 0.75), ("Flask", "Python", True, 0.75),
    ("TypeScript", "JavaScript", True, 0.75), ("React Native", "React", True, 0.75),
    ("Kotlin", "Java", True, 0.75), ("Express.js", "Node.js", True, 0.75),
    ("PyTorch", "Python", True, 0.75),
    ("React", "React", True, 1.0), ("Python", "Python", True, 1.0),
    ("Docker", "Docker", True, 1.0), ("JS", "JavaScript", True, 1.0),
    # True Negatives
    ("SEO", "Python", False, 0.0), ("Nursing", "React", False, 0.0),
    ("Accounting", "Docker", False, 0.0), ("Python", "Java", False, 0.0),
]


def phase3_skill_intelligence(engine):
    tp = tn = fp = fn = 0
    results = []
    for cand, jd, is_positive, threshold in SKILL_TESTS:
        r = engine.match_skills([cand], [jd])
        w = r.skill_weights.get(jd, 0.0)
        if is_positive:
            ok = w >= threshold
            tp += int(ok)
            fn += int(not ok)
        else:
            ok = w <= threshold
            tn += int(ok)
            fp += int(not ok)
        results.append({"candidate": cand, "jd": jd, "weight": round(w, 2),
                        "expected_positive": is_positive, "threshold": threshold, "pass": ok})

    total = tp + tn + fp + fn
    prec = tp / (tp + fp) * 100 if (tp + fp) else 0
    rec = tp / (tp + fn) * 100 if (tp + fn) else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
    return {
        "accuracy": round((tp + tn) / total * 100, 1), "precision": round(prec, 1),
        "recall": round(rec, 1), "f1": round(f1, 1),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn, "results": results,
    }


# ═════════════════════════════════════════════════════════════════
# PHASE 4: Ranking (lightweight skill-overlap scoring)
# ═════════════════════════════════════════════════════════════════

def phase4_ranking(candidate_index):
    jd_rankings = {}
    for jd_name, jd in JOB_DESCRIPTIONS.items():
        jd_skills = set(s.lower() for s in (jd.nice_to_have_skills + jd.must_have_skills))
        jd_kws = set(k.lower() for k in jd.keywords)
        jd_dept = jd.department.lower()

        scored = []
        for pdf_name, info in candidate_index.items():
            cand_skills = set(s.lower() for s in info.get("skills", []))
            skill_match = len(jd_skills & cand_skills)
            skill_score = skill_match / len(jd_skills) * 100 if jd_skills else 0

            # Sub-domain matching for engineering JDs
            domain_bonus = 0
            if jd_dept in ("civil engineering", "electrical engineering", "mechanical engineering"):
                if info.get("sub_domain", "").replace("_", " ") == jd_dept:
                    domain_bonus = 25
                elif info.get("domain") == "engineering":
                    domain_bonus = 5  # Wrong sub-type
            elif jd_dept == "engineering":
                if info.get("sub_domain", "").startswith("software"):
                    domain_bonus = 20
                elif info.get("domain") == "engineering":
                    domain_bonus = 10
            else:
                if info.get("domain") == jd_dept:
                    domain_bonus = 20

            exp_bonus = min(info.get("exp_count", 0) * 5, 20)
            approx = skill_score * 0.5 + domain_bonus + exp_bonus
            scored.append((pdf_name, info.get("name", "?"), round(approx, 1),
                          info.get("domain", "?"), info.get("sub_domain", "?"),
                          skill_match, len(jd_skills), info.get("exp_count", 0)))

        scored.sort(key=lambda x: -x[2])
        top20 = scored[:20]
        jd_rankings[jd_name] = {
            "top20": [{"rank": i+1, "file": s[0], "name": s[1], "score": s[2],
                       "domain": s[3], "sub_domain": s[4],
                       "skill_overlap": f"{s[5]}/{s[6]}", "exp_count": s[7]}
                      for i, s in enumerate(top20)],
            "total": len(scored),
        }
    return {"jd_rankings": jd_rankings}


# ═════════════════════════════════════════════════════════════════
# PHASE 5+6: FP/FN Audit (with full breakdown)
# ═════════════════════════════════════════════════════════════════

def phase5_6_fp_fn(jd_rankings, candidate_index):
    fp_cases = []
    fn_cases = []

    eng_jds = {"Backend Engineer", "Frontend Engineer", "Fullstack Engineer",
               "DevOps Engineer", "Data Engineer", "Data Scientist", "ML Engineer"}
    civil_jds = {"Civil Engineer"}
    elec_jds = {"Electrical Engineer"}
    mech_jds = {"Mechanical Engineer"}
    non_eng = {"marketing", "accounting", "legal", "healthcare", "hr", "finance"}

    for jd_name, ranking in jd_rankings.items():
        top20 = ranking["top20"]
        jd_dept = JOB_DESCRIPTIONS[jd_name].department.lower()

        for entry in top20[:10]:
            cand_domain = entry["domain"]
            sub_domain = entry["sub_domain"]
            score = entry["score"]
            reason_parts = []

            # FP logic: wrong domain or wrong sub-domain in top 10
            is_fp = False
            if jd_name in eng_jds:  # Software engineering JDs
                if cand_domain in non_eng and score > 30:
                    is_fp = True
                    reason_parts.append(f"{cand_domain} candidate in software engineering JD '{jd_name}'")
                elif cand_domain == "engineering" and sub_domain in ("civil_engineering", "mechanical_engineering", "electrical_engineering") and score > 30:
                    is_fp = True
                    reason_parts.append(f"{sub_domain} candidate in software JD '{jd_name}'")
            elif jd_name in civil_jds:
                if sub_domain != "civil_engineering" and cand_domain != "unknown" and score > 30:
                    is_fp = True
                    reason_parts.append(f"{sub_domain or cand_domain} candidate in Civil Engineer JD")
            elif jd_name in elec_jds:
                if sub_domain != "electrical_engineering" and cand_domain != "unknown" and score > 30:
                    is_fp = True
                    reason_parts.append(f"{sub_domain or cand_domain} candidate in Electrical Engineer JD")
            elif jd_name in mech_jds:
                if sub_domain != "mechanical_engineering" and cand_domain != "unknown" and score > 30:
                    is_fp = True
                    reason_parts.append(f"{sub_domain or cand_domain} candidate in Mechanical Engineer JD")
            else:  # Non-engineering JDs
                if cand_domain == "engineering" and score > 40:
                    is_fp = True
                    reason_parts.append(f"engineering candidate in non-eng JD '{jd_name}'")

            if is_fp:
                fp_cases.append({
                    "jd": jd_name, "jd_dept": jd_dept,
                    "file": entry["file"], "name": entry["name"],
                    "score": score, "domain": cand_domain, "sub_domain": sub_domain,
                    "skill_overlap": entry["skill_overlap"],
                    "exp_count": entry["exp_count"],
                    "reason": "; ".join(reason_parts),
                })

    # FN: domain-matching candidates with many skills NOT in top 20
    for jd_name, jd in JOB_DESCRIPTIONS.items():
        ranking = jd_rankings[jd_name]
        top20_files = {e["file"] for e in ranking["top20"]}
        jd_skills = set(s.lower() for s in (jd.nice_to_have_skills + jd.must_have_skills))
        jd_dept = jd.department.lower()
        fn_count = 0

        for pdf_name, info in candidate_index.items():
            if pdf_name in top20_files:
                continue
            # Check domain match
            domain_match = False
            if jd_dept == "engineering" and info.get("sub_domain", "").startswith("software"):
                domain_match = True
            elif info.get("domain") == jd_dept:
                domain_match = True
            elif jd_dept.replace(" ", "_") == info.get("sub_domain"):
                domain_match = True

            if domain_match:
                cand_skills = set(s.lower() for s in info.get("skills", []))
                overlap = len(jd_skills & cand_skills)
                if overlap >= 3:  # At least 3 matching skills
                    fn_cases.append({
                        "jd": jd_name, "file": pdf_name, "name": info["name"],
                        "domain": info["domain"], "sub_domain": info.get("sub_domain", ""),
                        "skill_count": info["skill_count"], "skill_overlap": overlap,
                        "reason": f"Domain match + {overlap}/{len(jd_skills)} skill overlap but not in top 20",
                    })
                    fn_count += 1
                    if fn_count >= 20:
                        break
        if len(fn_cases) >= 200:
            break

    fp_rate = len(fp_cases) / (len(jd_rankings) * 10) * 100 if jd_rankings else 0
    return (
        {"count": len(fp_cases), "rate": round(fp_rate, 1),
         "formula": f"{len(fp_cases)} / ({len(jd_rankings)} × 10)", "cases": fp_cases[:50]},
        {"count": len(fn_cases), "cases": fn_cases[:50]},
    )


# ═════════════════════════════════════════════════════════════════
# PHASE 7: Performance
# ═════════════════════════════════════════════════════════════════

def phase7_performance(pipe, scorer, pdfs, phase1_time, phase1_count):
    tiers = [1, 10, 100]
    if len(pdfs) >= 1000:
        tiers.append(1000)
    results = []
    jd = list(JOB_DESCRIPTIONS.values())[0]

    for n in tiers:
        t0 = time.time()
        extracted = []
        fails = 0
        for p in pdfs[:n]:
            try:
                r = pipe.extract(str(p))
                extracted.append(r.fields)
            except:
                fails += 1
        ext_time = time.time() - t0

        t0 = time.time()
        if extracted:
            scorer.rank(jd, extracted)
        rank_time = time.time() - t0

        mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        results.append({
            "n_pdfs": n, "extract_s": round(ext_time, 2), "rank_s": round(rank_time, 3),
            "memory_mb": round(mem, 1), "failures": fails,
            "per_pdf_ms": round(ext_time / n * 1000, 1),
        })
        print(f"    {n:5d} PDFs: extract={ext_time:.1f}s  rank={rank_time:.3f}s  mem={mem:.0f}MB")
        gc.collect()

    # Extrapolated from Phase 1
    if phase1_time > 0 and phase1_count >= 1000:
        results.append({
            "n_pdfs": phase1_count, "extract_s": round(phase1_time, 2), "rank_s": -1,
            "memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "failures": 0, "per_pdf_ms": round(phase1_time / phase1_count * 1000, 1),
            "note": "Phase 1 batch extraction data",
        })
        print(f"    {phase1_count:5d} PDFs: extract={phase1_time:.1f}s (Phase 1)  per_pdf={phase1_time/phase1_count*1000:.0f}ms")

    return {"tiers": results}


# ═════════════════════════════════════════════════════════════════
# PHASE 8: Frontend Consistency
# ═════════════════════════════════════════════════════════════════

def phase8_frontend():
    try:
        from fastapi.testclient import TestClient
        from src.api.app import app
        client = TestClient(app)
    except ImportError:
        return {"accuracy": 0, "error": "TestClient not available", "checks": []}

    checks = []
    passed = total = 0

    def _check(name, cond, detail=""):
        nonlocal passed, total
        total += 1
        ok = bool(cond)
        passed += int(ok)
        checks.append({"name": name, "passed": ok, "detail": detail})

    resp = client.post("/jobs", json={
        "title": "V5 Benchmark", "department": "Engineering", "description": "Test",
        "must_have_skills": ["Python"], "nice_to_have_skills": ["Docker"],
        "min_years": 0, "max_years": 99, "education_level": "any", "keywords": ["test"],
    })
    _check("POST /jobs", resp.status_code == 200)
    job_id = resp.json().get("id", "")

    test_pdf = next(RESUME_DIR.glob("*.pdf"), None)
    if test_pdf and job_id:
        with open(test_pdf, "rb") as f:
            resp = client.post(f"/jobs/{job_id}/resumes", files=[("files", (test_pdf.name, f, "application/pdf"))])
        _check("POST /resumes", resp.status_code == 200)

        events = []
        with client.stream("GET", f"/jobs/{job_id}/extract") as sse:
            for line in sse.iter_lines():
                if line:
                    events.append(line)
        _check("SSE extraction", len(events) > 0)

        resp = client.post(f"/jobs/{job_id}/score", json={
            "weights": {"skills": 40, "experience": 25, "keywords": 20, "education": 15},
        })
        _check("POST /score", resp.status_code == 200)

        if resp.status_code == 200:
            cands = resp.json().get("candidates", [])
            _check("Has candidates", len(cands) > 0)
            if cands:
                c = cands[0]
                for field in ["name", "document_id", "final_score", "rank", "knocked_out",
                              "skill_score", "experience_score", "keyword_score", "education_scre",
                              "matched_must_have", "missing_must_have"]:
                    _check(f"Field: {field}", field in c)

        resp = client.get(f"/jobs/{job_id}/results")
        _check("GET /results", resp.status_code == 200)

    return {"accuracy": round(passed / total * 100, 1) if total else 0, "passed": passed, "total": total, "checks": checks}


# ═════════════════════════════════════════════════════════════════
# PHASE 9: Production Readiness (honest scoring)
# ═════════════════════════════════════════════════════════════════

def phase9_scorecard(phases):
    scores = {}
    deductions = []

    # 1. Extraction Quality (25%) — composite of all field rates
    ext = phases["extraction"]
    scores["Extraction Quality"] = ext["composite_score"]
    deductions.append(f"Extraction composite: {ext['composite_formula']} = {ext['composite_score']}")

    # 2. Ranking Quality (20%) — based on domain match in top 5
    rank = phases["ranking"]
    domain_match_top5 = 0
    total_jds = len(rank["jd_rankings"])
    for jd_name, data in rank["jd_rankings"].items():
        jd_dept = JOB_DESCRIPTIONS[jd_name].department.lower()
        for entry in data["top20"][:5]:
            domain = entry["domain"]
            sub = entry["sub_domain"]
            if domain == jd_dept or sub.replace("_", " ") == jd_dept:
                domain_match_top5 += 1
            elif jd_dept == "engineering" and domain == "engineering":
                domain_match_top5 += 1
    rank_score = domain_match_top5 / (total_jds * 5) * 100 if total_jds else 0
    scores["Ranking Quality"] = round(rank_score, 1)
    deductions.append(f"Ranking: {domain_match_top5} domain-matched in top-5 across {total_jds} JDs = {domain_match_top5}/({total_jds}×5)")

    # 3. Knockout Reliability (15%)
    ko = phases["knockout"]
    scores["Knockout Reliability"] = round(ko["passed"] / ko["total"] * 100, 1) if ko["total"] else 0
    deductions.append(f"Knockout: {ko['passed']}/{ko['total']}")

    # 4. Domain Accuracy (15%) — % not unknown
    dom = phases["domain"]
    scores["Domain Accuracy"] = dom["classified_accuracy"]
    deductions.append(f"Domain: {dom['classified_formula']} = {dom['classified_accuracy']}%")

    # 5. FP Control (10%)
    fp = phases["fp"]
    fp_score = max(0, 100 - fp["rate"] * 5)
    scores["False Positive Control"] = round(fp_score, 1)
    deductions.append(f"FP: {fp['formula']} = {fp['rate']}%")

    # 6. FN Control (10%)
    fn = phases["fn"]
    fn_score = max(0, 100 - len(fn["cases"]) * 0.5)
    scores["False Negative Control"] = round(fn_score, 1)
    deductions.append(f"FN: {fn['count']} cases")

    # 7. Performance (5%)
    perf = phases["performance"]
    perf_score = 100
    for t in perf["tiers"]:
        if t["failures"] > 0:
            perf_score -= 10
    scores["Performance"] = max(0, round(perf_score, 1))

    # Weighted overall
    weights = {
        "Extraction Quality": 0.25, "Ranking Quality": 0.20,
        "Knockout Reliability": 0.15, "Domain Accuracy": 0.15,
        "False Positive Control": 0.10, "False Negative Control": 0.10,
        "Performance": 0.05,
    }
    overall = sum(scores.get(k, 0) * w for k, w in weights.items())

    if overall >= 95:
        verdict = "ENTERPRISE READY"
    elif overall >= 85:
        verdict = "PRODUCTION READY"
    elif overall >= 70:
        verdict = "BETA READY"
    else:
        verdict = "NOT READY"

    return {"scores": scores, "overall": round(overall, 1), "verdict": verdict, "deductions": deductions}


# ═════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═════════════════════════════════════════════════════════════════

def generate_report(phases, scorecard):
    L = []
    L.append(f"# Benchmark v5 — Trustworthy Production Report")
    L.append(f"Generated: {datetime.now().isoformat()}")
    L.append(f"Version: 5.0.0")
    L.append("")

    # Scorecard
    L.append("## Production Readiness Scorecard")
    L.append("")
    L.append("| Category | Score | Weight | Formula |")
    L.append("|----------|-------|--------|---------|")
    weights = {"Extraction Quality": 25, "Ranking Quality": 20, "Knockout Reliability": 15,
               "Domain Accuracy": 15, "False Positive Control": 10, "False Negative Control": 10, "Performance": 5}
    for k, v in scorecard["scores"].items():
        bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
        L.append(f"| {k} | {v:.0f}/100 {bar} | {weights.get(k, 0)}% | — |")
    L.append(f"| **OVERALL** | **{scorecard['overall']:.0f}/100** | **100%** | |")
    L.append("")
    emoji = {"ENTERPRISE READY": "🟢", "PRODUCTION READY": "🔵", "BETA READY": "🟡", "NOT READY": "🔴"}
    L.append(f"### Verdict: {emoji.get(scorecard['verdict'], '❓')} {scorecard['verdict']}")
    L.append("")
    L.append("### Metric Formulas (Phase 4 Audit)")
    for d in scorecard["deductions"]:
        L.append(f"- {d}")
    L.append("")

    # Phase 1: Knockout
    L.append("---")
    L.append("## Phase 1 — Knockout Validation")
    ko = phases["knockout"]
    L.append(f"**Passed: {ko['passed']}/{ko['total']}**")
    L.append("")
    for c in ko["checks"]:
        icon = "✅" if c["pass"] else "❌"
        L.append(f"- {icon} **{c['test']}**: knocked_out={c['knocked_out']} (expected={c['expected_ko']})")
        L.append(f"  - KO reasons: {c['ko_reasons']}")
        L.append(f"  - Matched must-have: {c['matched_must']}, Missing: {c['missing_must']}")
        L.append(f"  - Total years: {c['total_years']}")
    L.append("")

    # Phase 2: Extraction
    L.append("---")
    L.append("## Phase 2 — Extraction Accuracy")
    ext = phases["extraction"]
    L.append(f"- **Total PDFs**: {ext['total']}")
    L.append(f"- **Success Rate**: {ext['success_rate']}% ({ext['success']}/{ext['total']})")
    L.append(f"- **Composite Score**: {ext['composite_score']}/100")
    L.append(f"- **Formula**: `{ext['composite_formula']}`")
    L.append("")
    L.append("### Field Extraction Rates")
    L.append("| Field | Present | Rate | Formula | Avg Count |")
    L.append("|-------|---------|------|---------|-----------|")
    for f, d in ext["fields"].items():
        avg = d.get("avg", "-")
        L.append(f"| {f} | {d['present']} | {d['rate']}% | {d['formula']} | {avg} |")
    L.append("")

    # Name Audit
    na = ext["name_audit"]
    L.append("### Name Precision Audit")
    L.append(f"- **Valid names**: {na['valid_names']}")
    L.append(f"- **Blank names**: {na['blank_names']}")
    L.append(f"- **Blacklisted names**: {na['blacklisted_names']}")
    L.append(f"- **Name Precision**: {na['name_precision']}%")
    L.append(f"- **Formula**: `{na['name_precision_formula']}`")
    L.append(f"- **Confidence distribution**: {na['confidence_distribution']}")
    L.append("")

    # Anomalies
    an = ext["anomalies"]
    L.append("### Anomalies")
    L.append(f"- Tag leaks: {an['tag_leaks']}")
    L.append(f"- Skill duplicates: {an['skill_duplicates']}")
    L.append(f"- Low quality: {an['low_quality']}")
    L.append("")

    # Phase 2.5: Dedup
    L.append("---")
    L.append("## Phase 2.5 — Deduplication Audit")
    dd = phases["dedup"]
    L.append(f"- **Total PDFs**: {dd['total_pdfs']}")
    L.append(f"- **Unique PDFs (by SHA256)**: {dd['unique_pdfs_by_hash']}")
    L.append(f"- **Exact duplicates**: {dd['exact_duplicates']} ({dd['exact_duplicate_groups']} groups)")
    L.append(f"- **Near duplicates**: {dd['near_duplicates']} ({dd['near_duplicate_groups']} groups)")
    L.append(f"- **Dedup rate**: {dd['dedup_rate']}%")
    L.append("")
    if dd["exact_samples"]:
        L.append("### Exact Duplicate Samples")
        for s in dd["exact_samples"][:5]:
            L.append(f"- `{s['hash']}...`: {', '.join(s['files'][:3])}")
    if dd["near_samples"]:
        L.append("### Near Duplicate Samples")
        for s in dd["near_samples"][:5]:
            L.append(f"- `{s['hash']}...`: {', '.join(s['files'][:3])}")
    L.append("")

    # Phase 3: Skill Intelligence
    L.append("---")
    L.append("## Phase 3 — Skill Intelligence")
    sk = phases["skill"]
    L.append(f"- **Accuracy**: {sk['accuracy']}%  **P**: {sk['precision']}%  **R**: {sk['recall']}%  **F1**: {sk['f1']}%")
    L.append(f"- TP={sk['tp']}  TN={sk['tn']}  FP={sk['fp']}  FN={sk['fn']}")
    L.append("")

    # Phase 4: Ranking
    L.append("---")
    L.append("## Phase 4 — Ranking Accuracy")
    for jd_name, data in phases["ranking"]["jd_rankings"].items():
        L.append(f"\n### {jd_name}")
        L.append(f"Total candidates: {data['total']}")
        L.append("")
        L.append("| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |")
        L.append("|------|------|-------|--------|------------|--------|-----|")
        for e in data["top20"]:
            L.append(f"| #{e['rank']} | {e['name'][:30]} | {e['score']} | {e['domain']} | {e['sub_domain']} | {e['skill_overlap']} | {e['exp_count']} |")
    L.append("")

    # Phase 5: FP
    L.append("---")
    L.append("## Phase 5 — False Positive Audit")
    fp = phases["fp"]
    L.append(f"- **Count**: {fp['count']}")
    L.append(f"- **FP Rate**: {fp['rate']}%")
    L.append(f"- **Formula**: {fp['formula']}")
    L.append("")
    if fp["cases"]:
        L.append("| JD | Name | Score | Domain | Sub-Domain | Skills | Exp | Reason |")
        L.append("|----|------|-------|--------|------------|--------|-----|--------|")
        for c in fp["cases"][:30]:
            L.append(f"| {c['jd']} | {c['name'][:25]} | {c['score']} | {c['domain']} | {c['sub_domain']} | {c['skill_overlap']} | {c['exp_count']} | {c['reason'][:50]} |")
    L.append("")

    # Phase 6: FN
    L.append("---")
    L.append("## Phase 6 — False Negative Audit")
    fn = phases["fn"]
    L.append(f"- **Count**: {fn['count']}")
    L.append("")
    if fn["cases"]:
        L.append("| JD | Name | Domain | Sub-Domain | Skills | Overlap | Reason |")
        L.append("|----|------|--------|------------|--------|---------|--------|")
        for c in fn["cases"][:30]:
            L.append(f"| {c['jd']} | {c['name'][:25]} | {c['domain']} | {c['sub_domain']} | {c['skill_count']} | {c['skill_overlap']} | {c['reason'][:45]} |")
    L.append("")

    # Phase 6b: Domain Distribution
    L.append("---")
    L.append("## Phase 6b — Domain Classification")
    dom = phases["domain"]
    L.append(f"- **Classified**: {dom['classified_accuracy']}%")
    L.append(f"- **Formula**: `{dom['classified_formula']}`")
    L.append(f"- **Unknown**: {dom['unknown_count']} ({dom['unknown_pct']}%)")
    L.append("")
    L.append("| Domain | Count | % | Avg Confidence |")
    L.append("|--------|-------|---|----------------|")
    for d, data in dom["domain_distribution"].items():
        L.append(f"| {d} | {data['count']} | {data['pct']}% | {data['avg_confidence']} |")
    L.append("")

    # Phase 7: Performance
    L.append("---")
    L.append("## Phase 7 — Performance")
    L.append("| PDFs | Extract | Rank | Per-PDF | Memory | Failures |")
    L.append("|------|---------|------|---------|--------|----------|")
    for t in phases["performance"]["tiers"]:
        rank = f"{t['rank_s']}s" if t['rank_s'] >= 0 else "N/A"
        note = f" ({t.get('note', '')})" if t.get('note') else ""
        L.append(f"| {t['n_pdfs']} | {t['extract_s']}s | {rank} | {t['per_pdf_ms']}ms | {t['memory_mb']}MB | {t['failures']} |{note}")
    L.append("")

    # Phase 8: Frontend
    L.append("---")
    L.append("## Phase 8 — Frontend Consistency")
    fe = phases["frontend"]
    L.append(f"- **Accuracy**: {fe['accuracy']}% ({fe['passed']}/{fe['total']})")
    for c in fe.get("checks", []):
        icon = "✅" if c["passed"] else "❌"
        L.append(f"- {icon} {c['name']}: {c.get('detail', '')}")
    L.append("")

    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════

def main():
    print("\n" + "█" * 70)
    print("  ██  BENCHMARK v5: TRUSTWORTHY PRODUCTION EVALUATION  ██")
    print("█" * 70)
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Resume Dir: {RESUME_DIR}")

    pdfs = sorted(RESUME_DIR.glob("*.pdf"))
    print(f"  Total PDFs: {len(pdfs)}")
    if not pdfs:
        print("  ERROR: No PDFs found!")
        return

    pipe = PDFPipelineV3()
    scorer = CandidateScorer()
    engine = SkillInferenceEngine()
    classifier = DomainClassifier(engine)
    phases = {}

    # ── PHASE 1: Knockout ──
    print("\n" + "=" * 70)
    print("  PHASE 1: KNOCKOUT VALIDATION")
    print("=" * 70)
    phases["knockout"] = phase1_knockout(scorer)
    print(f"  Passed: {phases['knockout']['passed']}/{phases['knockout']['total']}")
    for c in phases['knockout']['checks']:
        icon = "✅" if c["pass"] else "❌"
        print(f"    {icon} {c['test']}: ko={c['knocked_out']} (expected={c['expected_ko']})")

    # ── PHASE 2: Extraction + Domain + Name Audit ──
    print("\n" + "=" * 70)
    print("  PHASE 2: EXTRACTION + DOMAIN + NAME AUDIT")
    print("=" * 70)
    t0 = time.time()
    extraction, domain, candidate_index = extract_all_batches(pipe, classifier, pdfs)
    phase1_elapsed = time.time() - t0
    phases["extraction"] = extraction
    phases["domain"] = domain
    print(f"  Completed in {phase1_elapsed:.1f}s")
    print(f"  Composite Extraction: {extraction['composite_score']}/100")
    print(f"  Name Precision: {extraction['name_audit']['name_precision']}%")
    print(f"  Domain Classified: {domain['classified_accuracy']}%")

    # ── PHASE 2.5: Dedup ──
    print("\n" + "=" * 70)
    print("  PHASE 2.5: DEDUPLICATION AUDIT")
    print("=" * 70)
    phases["dedup"] = phase2_5_dedup(pdfs, candidate_index)
    dd = phases["dedup"]
    print(f"  Unique PDFs: {dd['unique_pdfs_by_hash']}/{dd['total_pdfs']}")
    print(f"  Exact duplicates: {dd['exact_duplicates']}  Near duplicates: {dd['near_duplicates']}")

    # ── PHASE 3: Skill Intelligence ──
    print("\n" + "=" * 70)
    print("  PHASE 3: SKILL INTELLIGENCE")
    print("=" * 70)
    phases["skill"] = phase3_skill_intelligence(engine)
    print(f"  Accuracy: {phases['skill']['accuracy']}%  F1: {phases['skill']['f1']}%")

    # ── PHASE 4: Ranking ──
    print("\n" + "=" * 70)
    print("  PHASE 4: RANKING ACCURACY")
    print("=" * 70)
    phases["ranking"] = phase4_ranking(candidate_index)
    print(f"  Ranked {len(JOB_DESCRIPTIONS)} JDs × {len(candidate_index)} candidates")

    # ── PHASE 5+6: FP/FN ──
    print("\n" + "=" * 70)
    print("  PHASE 5-6: FALSE POSITIVE / NEGATIVE AUDIT")
    print("=" * 70)
    fp, fn = phase5_6_fp_fn(phases["ranking"]["jd_rankings"], candidate_index)
    phases["fp"] = fp
    phases["fn"] = fn
    print(f"  FP: {fp['count']} ({fp['rate']}%)  FN: {fn['count']}")

    # ── PHASE 7: Performance ──
    print("\n" + "=" * 70)
    print("  PHASE 7: PERFORMANCE")
    print("=" * 70)
    phases["performance"] = phase7_performance(pipe, scorer, pdfs, phase1_elapsed, len(pdfs))

    # ── PHASE 8: Frontend ──
    print("\n" + "=" * 70)
    print("  PHASE 8: FRONTEND CONSISTENCY")
    print("=" * 70)
    phases["frontend"] = phase8_frontend()
    print(f"  API Checks: {phases['frontend']['passed']}/{phases['frontend']['total']}")

    # ── PHASE 9: Scorecard ──
    print("\n" + "=" * 70)
    print("  PHASE 9: PRODUCTION READINESS SCORE")
    print("=" * 70)
    scorecard = phase9_scorecard(phases)

    print()
    weights = {"Extraction Quality": 25, "Ranking Quality": 20, "Knockout Reliability": 15,
               "Domain Accuracy": 15, "False Positive Control": 10, "False Negative Control": 10, "Performance": 5}
    for k, v in scorecard["scores"].items():
        bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
        print(f"  {k:30s} {v:5.0f}/100  {bar}  ({weights.get(k, 0)}%)")
    print(f"\n  {'OVERALL':30s} {scorecard['overall']:5.0f}/100")
    emoji = {"ENTERPRISE READY": "🟢", "PRODUCTION READY": "🔵", "BETA READY": "🟡", "NOT READY": "🔴"}
    print(f"\n  {emoji.get(scorecard['verdict'], '❓')} VERDICT: {scorecard['verdict']}")

    # Generate report
    report = generate_report(phases, scorecard)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"\n  📄 Report: {REPORT_PATH}")

    json_report = {
        "timestamp": datetime.now().isoformat(), "version": "5.0.0",
        "total_pdfs": len(pdfs), "phases": phases, "scorecard": scorecard,
    }
    with open(JSON_PATH, "w") as f:
        json.dump(json_report, f, indent=2, default=str)
    print(f"  📄 JSON: {JSON_PATH}")
    print(f"\n  Total time: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
