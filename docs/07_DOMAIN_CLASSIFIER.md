# 07 — Domain Classifier

## Overview

The Domain Classifier determines a candidate's (or JD's) professional domain from resume content using weighted keyword voting. This classification drives the **domain penalty** system, which prevents unrelated candidates from polluting rankings (e.g., a nurse appearing in software engineering results).

**Class:** `DomainClassifier` in `src/ranking/domain_classifier.py` (490 lines)

---

## Supported Domains (13)

| Domain | Example Titles |
|--------|---------------|
| `engineering` | Software Engineer, Civil Engineer, Mechanical Engineer |
| `healthcare` | Nurse, Physician, Pharmacist |
| `hr` | HR Manager, Recruiter, Talent Acquisition |
| `marketing` | Marketing Manager, SEO Specialist, Brand Manager |
| `finance` | Financial Analyst, Investment Banker |
| `accounting` | Accountant, Auditor, CPA |
| `legal` | Attorney, Paralegal, Legal Counsel |
| `education` | Teacher, Professor, Lecturer |
| `hospitality` | Hotel Manager, Chef, Concierge |
| `construction` | Construction Manager, Foreman, Builder |
| `admin` | Administrative Assistant, Office Manager |
| `sales` | Sales Manager, Account Executive, BDR |
| `unknown` | Insufficient signals |

---

## Engineering Subdomains (10)

When the primary domain is `engineering`, a secondary classification identifies the subdomain:

| Subdomain | Key Signals |
|-----------|------------|
| `software` | Python, JavaScript, React, Docker, API, Git |
| `civil` | AutoCAD, STAAD, Revit, Structural Analysis, Surveying |
| `mechanical` | SolidWorks, CATIA, ANSYS, CNC, HVAC, Thermodynamics |
| `electrical` | PLC, SCADA, PCB, Circuit, Transformer, Voltage |
| `data` | Spark, Hadoop, Kafka, Data Warehouse, ETL |
| `ml` | TensorFlow, PyTorch, Neural Network, NLP, Computer Vision |
| `frontend` | React, CSS, HTML, Responsive, UI/UX, Webpack |
| `backend` | API, Microservices, Database, SQL, REST API |
| `devops` | Terraform, Ansible, Jenkins, Kubernetes, Monitoring |
| `embedded` | Firmware, RTOS, Microcontroller, FPGA, Arduino |

---

## Classification Algorithm

### Candidate Classification

Three weighted signals are combined:

```
Signal 1: Experience keywords  (weight 3.0 for role title, 1.5 for description)
Signal 2: Project keywords     (weight 2.0)
Signal 3: Skills               (weight 1.0, via skill_graph domain mapping)
```

```python
def classify(candidate) -> (domain, confidence):
    domain_scores = {}

    # Signal 1: Experience
    for exp in candidate['experience']:
        role_domain = classify_text_snippet(exp['role'])        # weight 3.0
        desc_domain = classify_text_snippet(exp_full_text)       # weight 1.5

    # Signal 2: Projects
    for proj in candidate['projects']:
        proj_domain = classify_text_snippet(proj_full_text)      # weight 2.0

    # Signal 3: Skills (graph-based)
    for skill in candidate['skills']:
        skill_domain = skill_graph.get_domain(skill)             # weight 1.0

    best_domain = argmax(domain_scores)
    confidence = domain_scores[best_domain] / sum(domain_scores)
    return (best_domain, confidence)
```

### JD Classification

Similar but with different weights:
- Title: weight 4.0 (strongest signal)
- Department: weight 3.0
- Skills: weight 1.5
- Description: weight 1.0

---

## Keyword Dictionaries

Each domain has a list of `(keyword, weight)` tuples. Higher weight = stronger domain signal.

### Example: Healthcare Dictionary

```python
"healthcare": [
    ("nurse", 3.0), ("physician", 3.0), ("surgeon", 3.0),
    ("dentist", 3.0), ("pharmacist", 3.0),
    ("patient", 2.5), ("clinical", 2.5), ("hospital", 2.5),
    ("medical", 2.5), ("healthcare", 2.5),
    ("hipaa", 2.5), ("icu", 2.5), ("vital signs", 2.5),
    ("mbbs", 3.5), ("gnm", 3.0), ("anm", 3.0),
    # ...
]
```

### V9 Remediation (Key Changes)

The V9 benchmark identified that the healthcare dictionary was too broad, causing 67% of false positives. Changes made:

| Action | Terms | Reason |
|--------|-------|--------|
| **Removed from healthcare** | `monitoring`, `compliance`, `organization`, `assessment`, `research`, `distribution`, `quality`, `doctor` | Too generic — appear on engineering/business resumes |
| **Added to engineering** | 30+ civil/mechanical/electrical keywords | Engineers were misclassified as healthcare |
| **Reduced weights** | `compliance` (legal), `sourcing` (HR), `contract` (legal) | Cross-domain pollution |

---

## Domain Proximity Matrix

**File:** `src/registries/domain_proximity.json`

Defines penalties for domain mismatches between JD and candidate:

```json
{
  "penalties": {
    "engineering": {
      "healthcare": -80,
      "legal": -80,
      "hospitality": -70,
      "education": -50,
      "construction": 0,  // Related
      "hr": -60,
      "marketing": -60
    }
  },
  "sub_domain_penalties": {
    "engineering.civil": {
      "engineering.software": -30,
      "engineering.mechanical": -20,
      "engineering.electrical": -20
    }
  }
}
```

### Penalty Application Logic

```python
def _get_domain_penalty(jd_domain, cand_domain, jd_conf, cand_conf):
    # No penalty if:
    #   - Either domain is unknown
    #   - Either confidence < 0.4
    #   - Domains match
    #   - Unmapped pair defaults to -50

    return penalties[jd_domain][cand_domain]  # e.g., -80
```

**Applied to skill score only:**
```python
if penalty < 0:
    skill_score = skill_score * (1.0 + penalty / 100.0)
    # Example: penalty = -80 → skill_score *= 0.20
```

### Subdomain Penalties

If both JD and candidate are `engineering`, subdomain penalties apply instead:
- Civil JD + Software candidate → -30
- Civil JD + Mechanical candidate → -20
- Software JD + Software candidate → 0 (same subdomain)

---

## Domain Pre-Filter

In the main `rank()` method, candidates with **severe domain mismatch** (penalty ≤ -60) are filtered out before scoring begins:

```python
if jd_conf >= 0.35 and cand_conf >= 0.35:
    if penalty <= -60:
        continue  # Skip this candidate entirely
```

**Exemptions:**
- Engineering ↔ Construction (related domains, never filtered)
- Low confidence on either side (< 0.35) → no filtering

---

## Testing

**File:** `tests/test_domain_guardrails.py` — 7 permanent regression tests:

1. Civil engineer with AutoCAD + STAAD must NOT classify as healthcare
2. Mechanical engineer with SolidWorks + CATIA must NOT classify as healthcare
3. Electrical engineer with B.Tech EEE must NOT classify as healthcare
4. Nurse with ICU + GNM MUST classify as healthcare
5. MBBS candidate MUST classify as healthcare
6. Engineer with Compliance/Monitoring/Organization must stay engineering
7. Procurement engineer with contract terms must NOT classify as legal
