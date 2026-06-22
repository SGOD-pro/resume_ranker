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
    'javascript': 'javascript', 'typescript': 'typescript', 'python': 'python',
    'c#': 'csharp', 'c++': 'cplusplus', 'golang': 'go', 'go': 'go',
    'objc': 'objectivec', 'objectivec': 'objectivec',
    'vb': 'visualbasic', 'vbnet': 'visualbasic',
    'ruby': 'ruby', 'rb': 'ruby',
    'java': 'java', 'scala': 'scala', 'kotlin': 'kotlin',
    'rust': 'rust', 'swift': 'swift', 'dart': 'dart',
    'php': 'php', 'perl': 'perl', 'lua': 'lua',
    # ── DevOps / Infra ──
    'k8s': 'kubernetes', 'kube': 'kubernetes', 'kubernetes': 'kubernetes',
    'kubernates': 'kubernetes', 'kubernatis': 'kubernetes', 'kubernetis': 'kubernetes',
    'dkr': 'docker', 'docker': 'docker', 'dockerize': 'docker',
    'tf': 'terraform', 'terraform': 'terraform', 'terrform': 'terraform',
    'ans': 'ansible', 'ansible': 'ansible', 'anisble': 'ansible',
    'jenkin': 'jenkins', 'jenkins': 'jenkins', 'jenkns': 'jenkins',
    'ci': 'continuousintegration', 'cd': 'continuousdeployment',
    'cicd': 'cicd', 'ci/cd': 'cicd',
    # ── Cloud ──
    'aws': 'aws', 'amazonwebservices': 'aws',
    'gcp': 'gcp', 'googlecloud': 'gcp', 'googlecloudplatform': 'gcp',
    'azure': 'azure', 'msazure': 'azure',
    # ── Databases ──
    'pg': 'postgresql', 'postgres': 'postgresql', 'postgre': 'postgresql',
    'postgresql': 'postgresql', 'postgressql': 'postgresql', 'psql': 'postgresql',
    'mongo': 'mongodb', 'mongodb': 'mongodb', 'mongdb': 'mongodb',
    'mysql': 'mysql', 'sql': 'sql',
    'mssql': 'mssql', 'sqlserver': 'mssql', 'microsoftsqlserver': 'mssql',
    'dynamodb': 'dynamodb', 'dynamo': 'dynamodb',
    'redis': 'redis', 'memcached': 'memcached',
    'cassandra': 'cassandra', 'elasticsearch': 'elasticsearch',
    # ── Frameworks ──
    'react': 'reactjs', 'reactjs': 'reactjs', 'react.js': 'reactjs',
    'reactnative': 'reactnative', 'react native': 'reactnative',
    'node': 'nodejs', 'nodejs': 'nodejs', 'node.js': 'nodejs', 'nodjs': 'nodejs',
    'nextjs': 'nextjs', 'next': 'nextjs', 'next.js': 'nextjs',
    'vue': 'vuejs', 'vuejs': 'vuejs', 'vue.js': 'vuejs',
    'angular': 'angular', 'angularjs': 'angular',
    'django': 'django', 'djnago': 'django',
    'flask': 'flask', 'flsk': 'flask',
    'fastapi': 'fastapi', 'fstapi': 'fastapi',
    'springboot': 'springboot', 'spring': 'springboot', 'spring boot': 'springboot',
    'express': 'expressjs', 'expressjs': 'expressjs', 'express.js': 'expressjs',
    'rails': 'rubyonrails', 'ror': 'rubyonrails', 'rubyonrails': 'rubyonrails',
    'aspnet': 'aspnet', 'asp.net': 'aspnet',
    'dotnet': 'dotnet', '.net': 'dotnet',
    # ── Data / AI / ML ──
    'sklearn': 'scikitlearn', 'scikitlearn': 'scikitlearn', 'scikit-learn': 'scikitlearn',
    'ml': 'machinelearning', 'machinelearning': 'machinelearning',
    'dl': 'deeplearning', 'deeplearning': 'deeplearning',
    'nlp': 'nlp', 'naturallanguageprocessing': 'nlp',
    'ai': 'ai', 'artificialintelligence': 'ai',
    'cv': 'computervision', 'computervision': 'computervision',
    'pytorch': 'pytorch', 'torch': 'pytorch',
    'tensorflow': 'tensorflow', 'tensrflow': 'tensorflow', 'tf': 'tensorflow',
    'pandas': 'pandas', 'pnds': 'pandas',
    'numpy': 'numpy', 'np': 'numpy',
    'scipy': 'scipy', 'keras': 'keras',
    'llm': 'llm', 'largelanguagemodel': 'llm',
    'rag': 'rag', 'gpt': 'gpt', 'chatgpt': 'gpt',
    # ── APIs ──
    'restapi': 'restapi', 'rest': 'restapi', 'restapis': 'restapi',
    'restful': 'restapi', 'restfulapi': 'restapi',
    'graphql': 'graphql', 'gql': 'graphql',
    'grpc': 'grpc',
    # ── Tools ──
    'git': 'git', 'github': 'github', 'gitlab': 'gitlab',
    'jira': 'jira', 'jiira': 'jira',
    'figma': 'figma', 'fgma': 'figma',
    'webpack': 'webpack', 'vite': 'vite',
    'npm': 'npm', 'yarn': 'yarn', 'pnpm': 'pnpm',
    # ── Marketing / Business ──
    'seo': 'seo', 'searchengineoptimization': 'seo',
    'sem': 'sem', 'searchenginemarketing': 'sem',
    'smm': 'smm', 'socialmediamarketing': 'smm',
    'ppc': 'ppc', 'payperclick': 'ppc',
    'crm': 'crm', 'customerrelationshipmanagement': 'crm',
    'erp': 'erp', 'enterpriseresourceplanning': 'erp',
    'bi': 'bi', 'businessintelligence': 'bi',
    # ── Security ──
    'ids': 'ids', 'intrusiondetectionsystem': 'ids',
    'ips': 'ips', 'intrusionpreventionsystem': 'ips',
    'siem': 'siem', 'securityinformationeventmanagement': 'siem',
    'vpn': 'vpn', 'virtualprivatenetwork': 'vpn',
    # ── Misc typos / shortforms ──
    'agile': 'agile', 'agil': 'agile',
    'scrum': 'scrum', 'scurm': 'scrum',
    'devops': 'devops', 'devop': 'devops',
    'oop': 'oop', 'objectorientedprogramming': 'oop',
    'tdd': 'tdd', 'testdrivendevelopment': 'tdd',
    'bdd': 'bdd', 'behaviordrivendevelopment': 'bdd',
    'mvc': 'mvc', 'mvvm': 'mvvm',
}

# ─────────────────────────────────────────────────────────────────────────────
# Keyword Aliases — for domain-agnostic keyword variations in JD matching
# ─────────────────────────────────────────────────────────────────────────────
# Maps a keyword to a list of alternative surface forms to search in text.
# These are NOT normalized — they're literal strings to match in raw text.

KEYWORD_ALIASES: Dict[str, List[str]] = {
    # Tech / architecture keywords
    'microservices':  ['microservices', 'micro-services', 'micro services', 'microservice'],
    'backend':        ['backend', 'back-end', 'back end', 'server-side', 'server side'],
    'frontend':       ['frontend', 'front-end', 'front end', 'client-side', 'client side'],
    'fullstack':      ['fullstack', 'full-stack', 'full stack'],
    'deployment':     ['deployment', 'deploy', 'deploying', 'deployed', 'deployments'],
    'scalable':       ['scalable', 'scalability', 'scaling', 'scale'],
    'api':            ['api', 'apis', 'rest api', 'restful', 'web service', 'web services', 'endpoint'],
    'database':       ['database', 'databases', 'db', 'data store', 'datastore', 'rdbms'],
    'agile':          ['agile', 'scrum', 'kanban', 'sprint', 'sprints'],
    'server':         ['server', 'servers', 'server-side'],
    'cloud':          ['cloud', 'cloud-based', 'cloud computing', 'saas', 'paas', 'iaas'],
    'devops':         ['devops', 'dev-ops', 'dev ops', 'ci/cd', 'cicd'],
    'testing':        ['testing', 'test', 'unit test', 'unit testing', 'integration testing', 'qa'],
    'containerization': ['containerization', 'containers', 'container', 'docker', 'kubernetes'],
    'monitoring':     ['monitoring', 'observability', 'logging', 'alerting'],
    # Marketing keywords
    'campaign':       ['campaign', 'campaigns', 'ad campaign', 'marketing campaign'],
    'brand':          ['brand', 'branding', 'brand awareness', 'brand identity'],
    'content':        ['content', 'content creation', 'content strategy', 'content marketing'],
    'traffic':        ['traffic', 'web traffic', 'site traffic', 'organic traffic'],
    'conversion':     ['conversion', 'conversions', 'conversion rate', 'cro'],
    'strategy':       ['strategy', 'strategic', 'strategies', 'strategic planning'],
    'audience':       ['audience', 'target audience', 'demographics', 'segmentation'],
    'engagement':     ['engagement', 'user engagement', 'customer engagement'],
    # Security keywords
    'security':       ['security', 'cybersecurity', 'cyber security', 'infosec', 'information security'],
    'patrol':         ['patrol', 'patrolling', 'patrols'],
    'monitor':        ['monitor', 'monitoring', 'surveillance', 'supervise'],
    'safety':         ['safety', 'safe', 'safety protocols', 'workplace safety'],
    'guard':          ['guard', 'guarding', 'security guard', 'security officer'],
    'investigation':  ['investigation', 'investigate', 'investigations', 'investigative'],
    'compliance':     ['compliance', 'compliant', 'regulatory', 'regulations'],
    # Web dev keywords
    'web':            ['web', 'website', 'websites', 'web application', 'web app', 'webapp'],
    'responsive':     ['responsive', 'responsive design', 'mobile-friendly', 'mobile friendly'],
    'github':         ['github', 'git', 'version control', 'source control'],
}

# Build reverse lookup: canonical → {all known surface forms}
_REVERSE_ALIASES: Dict[str, Set[str]] = {}
for _alias, _canonical in SKILL_ALIASES.items():
    _REVERSE_ALIASES.setdefault(_canonical, set()).add(_alias)

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


def normalize_for_graph(s: str) -> str:
    """Normalize a skill name to a skill_graph.json key.

    Maps surface forms to underscore-separated graph keys:
        "Financial Modeling" → "financial_modeling"
        "React.js"          → "reactjs"
        "Node.js"           → "nodejs"
        "C++"               → "cplusplus"
        "C#"                → "csharp"
        "Employment Law"    → "employment_law"

    The graph key format uses underscores for multi-word domain skills
    and no separators for tech names (matching existing SKILL_ALIASES).
    """
    s = s.lower().strip()

    # Special cases
    s = s.replace('c++', 'cplusplus')
    s = s.replace('c#', 'csharp')
    s = s.replace('.net', 'dotnet')
    s = s.replace('asp.net', 'aspnet')

    # Strip .js suffix then dots/dashes
    s = re.sub(r'\.js$', 'js', s)
    s = re.sub(r'[.\-/]', '', s)

    # Replace spaces with underscores for multi-word skills
    s = s.replace(' ', '_')

    # Also try the alias-based resolution: collapse underscores for tech
    # If the underscore form doesn't exist in graph but collapsed form does
    # via SKILL_ALIASES, prefer alias resolution.
    alias_form = s.replace('_', '')
    canonical = SKILL_ALIASES.get(alias_form)
    if canonical:
        return canonical

    return s


def get_search_variants(term: str) -> List[str]:
    """Return all known surface forms for a skill or keyword term.
    Used for text-searching: given 'Node', returns ['node', 'nodejs', 'node.js'].
    Given a keyword like 'backend', returns ['backend', 'back-end', 'back end', ...].
    """
    term_lower = term.lower().strip()
    term_norm = normalize(term)
    variants = {term_lower}  # Always include the original

    # Check keyword aliases first (literal text forms)
    if term_lower in KEYWORD_ALIASES:
        variants.update(KEYWORD_ALIASES[term_lower])

    # Check skill aliases — get canonical form, then all surface forms
    canonical = SKILL_ALIASES.get(term_norm)
    if canonical:
        # Add all aliases that resolve to the same canonical
        for alias, canon in SKILL_ALIASES.items():
            if canon == canonical:
                variants.add(alias)
        # Also add the canonical itself
        variants.add(canonical)

    # Add common suffix/prefix variants
    if term_lower.endswith('.js'):
        variants.add(term_lower.replace('.js', 'js'))  # node.js → nodejs
        variants.add(term_lower.replace('.js', ''))     # node.js → node
    elif term_lower.endswith('js') and not term_lower.endswith('.js'):
        base = term_lower[:-2]
        if base:  # nodejs → node, node.js
            variants.add(base)
            variants.add(base + '.js')

    return list(variants)


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
