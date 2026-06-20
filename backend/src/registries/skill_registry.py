"""
skill_registry.py — Single source of truth for skill normalization & matching
================================================================================
Consolidates skill aliases, normalization, and matching logic that was previously
duplicated across scorer.py and skills_parser.py.

Usage:
    from src.registries.skill_registry import normalize, match, find_matches

    normalize("React.js")          # → "reactjs"
    match("k8s", "Kubernetes")     # → True
    find_matches(["Python", "SQL"], ["Python", "Go"])  # → (["Python"], ["Go"])
"""

import re
from typing import Dict, List, Set, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Skill Aliases — abbreviations, typos, alternate spellings
# ─────────────────────────────────────────────────────────────────────────────
# Both sides are normalized (lowercase, no dots/dashes/spaces)

SKILL_ALIASES: Dict[str, str] = {
    # ── Programming Languages ──
    'js': 'javascript', 'ts': 'typescript', 'py': 'python',
    'c#': 'csharp', 'c++': 'cplusplus', 'golang': 'go',
    'objc': 'objectivec', 'objectivec': 'objectivec',
    'vb': 'visualbasic', 'vbnet': 'visualbasic',
    # ── DevOps / Infra ──
    'k8s': 'kubernetes', 'kube': 'kubernetes', 'kubernates': 'kubernetes',
    'kubernatis': 'kubernetes', 'kubernetis': 'kubernetes',
    'dkr': 'docker', 'dockerize': 'docker',
    'tf': 'terraform', 'terrform': 'terraform',
    'ans': 'ansible', 'anisble': 'ansible',
    'jenkin': 'jenkins', 'jenkns': 'jenkins',
    'ci': 'continuousintegration', 'cd': 'continuousdeployment',
    'cicd': 'continuousintegration',
    # ── Cloud ──
    'aws': 'amazonwebservices', 'amazn': 'amazonwebservices',
    'gcp': 'googlecloud', 'googlecloudplatform': 'googlecloud',
    'az': 'azure', 'msazure': 'azure',
    # ── Databases ──
    'pg': 'postgresql', 'postgres': 'postgresql', 'postgre': 'postgresql',
    'postgressql': 'postgresql', 'psql': 'postgresql',
    'mongo': 'mongodb', 'mongdb': 'mongodb',
    'mssql': 'microsoftsqlserver', 'sqlserver': 'microsoftsqlserver',
    'dynamodb': 'amazondynamodb', 'dynamo': 'amazondynamodb',
    # ── Frameworks ──
    'react': 'reactjs', 'reactjs': 'reactjs', 'reactnative': 'reactnative',
    'node': 'nodejs', 'nodejs': 'nodejs', 'nodjs': 'nodejs',
    'nextjs': 'nextjs', 'next': 'nextjs',
    'vue': 'vuejs', 'vuejs': 'vuejs',
    'django': 'django', 'djnago': 'django',
    'flask': 'flask', 'flsk': 'flask',
    'fastapi': 'fastapi', 'fstapi': 'fastapi',
    'springboot': 'springboot', 'spring': 'springboot',
    'express': 'expressjs', 'expressjs': 'expressjs',
    'rails': 'rubyonrails', 'ror': 'rubyonrails',
    # ── Data / AI / ML ──
    'sklearn': 'scikitlearn', 'scikitlearn': 'scikitlearn',
    'ml': 'machinelearning', 'dl': 'deeplearning',
    'nlp': 'naturallanguageprocessing',
    'ai': 'artificialintelligence',
    'cv': 'computervision',
    'pytorch': 'pytorch', 'torch': 'pytorch',
    'tensorflow': 'tensorflow', 'tensrflow': 'tensorflow',
    'pandas': 'pandas', 'pnds': 'pandas',
    'numpy': 'numpy', 'np': 'numpy',
    # ── APIs ──
    'restapi': 'restapis', 'rest': 'restapis', 'restapis': 'restapis',
    'restful': 'restapis', 'restfulapi': 'restapis',
    'graphql': 'graphql', 'gql': 'graphql',
    'grpc': 'grpc',
    # ── Tools ──
    'git': 'git', 'github': 'github', 'gitlab': 'gitlab',
    'jira': 'jira', 'jiira': 'jira',
    'figma': 'figma', 'fgma': 'figma',
    # ── Marketing / Business ──
    'seo': 'searchengineoptimization', 'sem': 'searchenginemarketing',
    'smm': 'socialmediamarketing', 'ppc': 'payperclick',
    'crm': 'customerrelationshipmanagement',
    'erp': 'enterpriseresourceplanning',
    'bi': 'businessintelligence',
    # ── Security ──
    'ids': 'intrusiondetectionsystem', 'ips': 'intrusionpreventionsystem',
    'siem': 'securityinformationeventmanagement',
    'vpn': 'virtualprivatenetwork',
    # ── Misc typos / shortforms ──
    'agile': 'agile', 'agil': 'agile',
    'scrum': 'scrum', 'scurm': 'scrum',
    'devops': 'devops', 'devop': 'devops',
    'oop': 'objectorientedprogramming',
    'tdd': 'testdrivendevelopment',
    'bdd': 'behaviordrivendevelopment',
}

# Single-char skills that are valid programming languages
SINGLE_CHAR_SKILLS: Set[str] = {'r', 'c'}


# ─────────────────────────────────────────────────────────────────────────────
# Normalization
# ─────────────────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Lowercase, strip, and normalize common variants."""
    s = s.lower().strip()
    # Normalize common variations
    s = re.sub(r'\.js$', 'js', s)        # "react.js" → "reactjs"
    s = re.sub(r'[.\-/]', '', s)         # "node.js" → "nodejs"
    s = s.replace(' ', '')               # "machine learning" → "machinelearning"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Matching
# ─────────────────────────────────────────────────────────────────────────────

def match(candidate_skill: str, jd_skill: str) -> bool:
    """Check if a candidate skill matches a JD skill (fuzzy).
    Handles aliases, typos, abbreviations (k8s→Kubernetes), and
    single-char language names (R, C) safely."""
    cn = normalize(candidate_skill)
    jn = normalize(jd_skill)

    # Exact match after normalization
    if cn == jn:
        return True

    # Single-char skills (R, C): only exact match, no substring
    if len(cn) <= 1 or len(jn) <= 1:
        # Resolve via aliases only
        cn_resolved = SKILL_ALIASES.get(cn, cn)
        jn_resolved = SKILL_ALIASES.get(jn, jn)
        return cn_resolved == jn_resolved

    # Short skills (2 chars like JS, AI, ML): resolve via aliases, no substring
    if len(cn) <= 2 or len(jn) <= 2:
        cn_resolved = SKILL_ALIASES.get(cn, cn)
        jn_resolved = SKILL_ALIASES.get(jn, jn)
        if cn_resolved == jn_resolved:
            return True
        # Also check if short form equals the other directly
        return cn == jn

    # Substring matching for 3+ char strings
    if cn in jn or jn in cn:
        return True

    # Alias resolution
    cn_resolved = SKILL_ALIASES.get(cn, cn)
    jn_resolved = SKILL_ALIASES.get(jn, jn)
    if cn_resolved == jn_resolved:
        return True

    return False


def find_matches(candidate_skills: List[str],
                 jd_skills: List[str]) -> Tuple[List[str], List[str]]:
    """Return (matched, missing) JD skills against candidate skills."""
    matched = []
    missing = []
    for jd_sk in jd_skills:
        found = any(match(c_sk, jd_sk) for c_sk in candidate_skills)
        if found:
            matched.append(jd_sk)
        else:
            missing.append(jd_sk)
    return matched, missing
