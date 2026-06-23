# 09 — Registry System

## Overview

Registries are externalized dictionaries and graphs that drive the system's matching, classification, and normalization logic. They are the primary mechanism for extending the system to new skills, section headers, and domains without code changes.

---

## 1. Skill Registry

**File:** `src/registries/skill_registry.py` (321 lines)

The single source of truth for skill normalization and matching across the entire system.

### Components

#### `SKILL_ALIASES` — 118 entries

Maps normalized skill names to canonical forms:

```python
SKILL_ALIASES = {
    'js': 'javascript',
    'ts': 'typescript',
    'k8s': 'kubernetes',
    'react': 'reactjs',
    'node': 'nodejs',
    'node.js': 'nodejs',
    'pg': 'postgresql',
    'postgres': 'postgresql',
    # ... 118 total
}
```

**Coverage:** Programming languages, DevOps tools, cloud providers, databases, frameworks, data/AI/ML, APIs, marketing/business, security, and common typos.

#### `KEYWORD_ALIASES` — 30 entries

Maps JD keywords to all known surface forms for text searching:

```python
KEYWORD_ALIASES = {
    'microservices': ['microservices', 'micro-services', 'micro services'],
    'backend': ['backend', 'back-end', 'back end', 'server-side'],
    'database': ['database', 'databases', 'db', 'data store', 'rdbms'],
    # ...
}
```

#### `SINGLE_CHAR_SKILLS`

```python
SINGLE_CHAR_SKILLS = {'r', 'c'}  # Valid single-char programming languages
```

### Core Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `normalize(s)` | `str → str` | Lowercase, strip dots/dashes/spaces: `"React.js"` → `"reactjs"` |
| `normalize_for_graph(s)` | `str → str` | Graph-key form: `"Financial Modeling"` → `"financial_modeling"` |
| `match(candidate, jd)` | `str, str → bool` | Fuzzy match: alias resolution, substring matching (≥3 chars), single-char safety |
| `find_matches(cand_skills, jd_skills)` | `List, List → (matched, missing)` | Batch matching of JD skills against candidate skills |
| `get_search_variants(term)` | `str → List[str]` | All known surface forms: `"Node"` → `["node", "nodejs", "node.js"]` |

### Match Logic (Detailed)

```python
def match(candidate_skill, jd_skill):
    cn, jn = normalize(candidate), normalize(jd)

    # 1. Exact match after normalization
    if cn == jn: return True

    # 2. Single-char skills (R, C): alias-only, no substring
    if len(cn) <= 1 or len(jn) <= 1:
        return SKILL_ALIASES.get(cn) == SKILL_ALIASES.get(jn)

    # 3. Short skills (2 chars: JS, AI): alias-only, no substring
    if len(cn) <= 2 or len(jn) <= 2:
        return alias_match(cn, jn)

    # 4. Substring matching for 3+ char strings
    if cn in jn or jn in cn: return True

    # 5. Alias resolution
    return SKILL_ALIASES.get(cn) == SKILL_ALIASES.get(jn)
```

---

## 2. Section Registry

**File:** `src/registries/section_registry.py` (269 lines)

Maps raw resume section headers to canonical section names.

### Canonical Sections (11)

```python
CANONICAL_SECTIONS = [
    "summary", "experience", "education", "projects", "skills",
    "certifications", "languages", "awards", "achievements",
    "publications", "references"
]
```

### Section Aliases (200+)

Maps uppercase raw headers to canonical names. Coverage includes:

| Canonical | Sample Aliases |
|-----------|---------------|
| `summary` | PROFILE, ABOUT ME, OBJECTIVE, CAREER OBJECTIVE, EXECUTIVE SUMMARY |
| `experience` | WORK EXPERIENCE, EMPLOYMENT HISTORY, CLINICAL EXPERIENCE, LEGAL EXPERIENCE, MILITARY SERVICE |
| `education` | ACADEMIC BACKGROUND, QUALIFICATIONS, EDUCATIONAL BACKGROUND |
| `projects` | PERSONAL PROJECTS, OPEN SOURCE, CASE STUDIES, RESEARCH PROJECTS, CLIENT PROJECTS |
| `skills` | TECHNICAL SKILLS, CORE COMPETENCIES, TECHNOLOGIES, CLINICAL SKILLS |
| `certifications` | CERTIFICATES, COURSES, TRAINING, LICENSES, BAR ADMISSIONS |

### Assembler Compatibility Layer

The legacy `ResumeAssembler` used different internal keys:

```python
ASSEMBLER_KEY_MAP = {
    "experience": "employment",
    "summary": "profile",
    "certifications": "courses",
    "achievements": "accomplishments",
}
```

`to_assembler_key()` converts canonical names back for assembler compatibility.

### Resolution API

```python
resolve("Employment History")   # → "experience"
resolve("CLINICAL EXPERIENCE")  # → "experience"
resolve("Cases")                # → "projects"
resolve("random text")          # → None
```

Also handles trailing special characters: `"Skills / Tools"` → strips ` / Tools` → resolves `"SKILLS"`.

---

## 3. Skill Graph

**File:** `src/registries/skill_graph.json` (~80KB)

A directed graph of 200+ skills with implies, related, and alias edges.

### Node Structure

```json
{
  "reactjs": {
    "display": "React",
    "aliases": ["react", "react.js"],
    "domain": "engineering",
    "implies": ["javascript"],
    "related": ["angular", "vuejs", "svelte"]
  }
}
```

### Edge Types

| Edge | Semantics | Example |
|------|-----------|---------|
| `implies` | "Knowing A means you know B" | Next.js → React, Node.js |
| `related` | "A and B are in the same family" | React ↔ Angular, Vue |
| `aliases` | "These are names for the same thing" | react, React.js, reactjs |

### Domain Tags

Every skill node has a `domain` field used by the `DomainClassifier`:

```
"engineering", "healthcare", "finance", "legal", "marketing",
"hr", "education", "hospitality", "construction", "sales", "accounting"
```

### V9 Additions

26 engineering skills were added in V9 to fix domain misclassification:
```
autocad, solidworks, catia, ansys, staad, revit, matlab,
hvac_systems, cnc_programming, plc_programming, scada_systems,
civil_engineering, mechanical_engineering, electrical_engineering, ...
```

---

## 4. Domain Proximity Matrix

**File:** `src/registries/domain_proximity.json` (~5KB)

Defines cross-domain and cross-subdomain penalty values.

### Structure

```json
{
  "penalties": {
    "engineering": {
      "healthcare": -80,
      "legal": -80,
      "finance": -50,
      "construction": 0
    },
    "healthcare": {
      "engineering": -80,
      "legal": -70,
      "hospitality": -60
    }
  },
  "sub_domain_penalties": {
    "engineering.civil": {
      "engineering.software": -30,
      "engineering.mechanical": -20
    },
    "engineering.software": {
      "engineering.civil": -40,
      "engineering.mechanical": -30
    }
  }
}
```

### Interpretation

| Penalty | Meaning |
|---------|---------|
| 0 | No penalty (same or related domains) |
| -20 to -30 | Mild penalty (adjacent engineering subdomains) |
| -50 | Default for unmapped domain pairs |
| -60 to -70 | Severe penalty (triggers pre-filter exclusion) |
| -80 | Maximum penalty (completely unrelated domains) |

---

## Extending the Registries

### Adding a New Skill Alias

1. Add entry to `SKILL_ALIASES` in `skill_registry.py`
2. If the skill has implies/related edges, add a node to `skill_graph.json`
3. No code changes needed — all matching uses the registry functions

### Adding a New Section Header

1. Add entry to `SECTION_ALIASES` in `section_registry.py`
2. Map to one of the 11 canonical sections
3. Use UPPERCASE key

### Adding a New Domain

1. Add keyword dictionary to `_DOMAIN_KEYWORDS` in `domain_classifier.py`
2. Add penalty entries to `domain_proximity.json`
3. Add domain tag to relevant skills in `skill_graph.json`
