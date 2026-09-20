# SWYRA Sortlist — Explainable Candidate Review Workspace (v2 Release)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.x-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Status: v2-Release](https://img.shields.io/badge/Release-v2.0.0-blue.svg)](docs/v2-release/PRODUCT.md)

> **Core Promise:** Every recommendation is evidence-linked, configurable, reviewable, and reversible by a human recruiter.

SWYRA Sortlist is **NOT** an autonomous hiring system and **NOT** a generic enterprise ATS. It is a focused, explainable candidate-review workspace built for small hiring teams (2–15 recruiters) and boutique agencies who need transparent, audit-ready screening assistance.

---

## 📚 Authoritative Release Specifications

All architectural, product, scoring, and safety decisions for the v2 public release are documented in the authoritative specifications under [`docs/v2-release/`](docs/v2-release/):

| Specification | Description |
| :--- | :--- |
| [**AUDIT.md**](docs/v2-release/AUDIT.md) | Full technical audit of implemented vs. planned behavior, tech debt, and security findings. |
| [**PRODUCT.md**](docs/v2-release/PRODUCT.md) | Product identity, target users, decision workflows, core capabilities, and scope boundaries. |
| [**ARCHITECTURE.md**](docs/v2-release/ARCHITECTURE.md) | Modular monolith architecture, data flow, DynamoDB/S3 layouts, and provider interfaces. |
| [**DATA-MODEL.md**](docs/v2-release/DATA-MODEL.md) | DynamoDB single-table schema, S3 key patterns, entity lifecycles, and TypeScript contracts. |
| [**API-CONTRACTS.md**](docs/v2-release/API-CONTRACTS.md) | Complete REST API reference, request/response DTOs, rate limits, and authentication. |
| [**SCORING-POLICY.md**](docs/v2-release/SCORING-POLICY.md) | Binding scoring mathematics, allowed vs. prohibited inputs, knockout rules, and factor ledger. |
| [**TRUST-SAFETY-PRIVACY.md**](docs/v2-release/TRUST-SAFETY-PRIVACY.md) | Non-negotiable fairness policy, data retention, audit logging, and ATS checker privacy. |
| [**EVALUATION.md**](docs/v2-release/EVALUATION.md) | Evaluation methodology, gold-set validation, benchmark protocol, and audit of legacy claims. |
| [**IMPLEMENTATION-PLAN.md**](docs/v2-release/IMPLEMENTATION-PLAN.md) | Phased delivery plan across P0 Security, P1 Evidence Workflow, and P2 ATS Diagnostics. |
| [**ACCEPTANCE-TESTS.md**](docs/v2-release/ACCEPTANCE-TESTS.md) | Acceptance test suites, test IDs, verification criteria, and quality gates. |
| [**MIGRATION.md**](docs/v2-release/MIGRATION.md) | Migration guide from v1 prototype to v2 public release. |

> [!NOTE]
> All root legacy documentation files (`projectrequirement.md`, `project.md`, `architecture.md`, `design.md`, `rules.md`, `phases.md`, etc.) are superseded by the specifications in `docs/v2-release/`.

---

## ⚖️ Non-Negotiable Fairness Policy

Sortlist is built on strict algorithmic transparency and fairness:

1. **Prohibited Ranking Inputs:** The system **never** uses, infers, ranks, filters, or exposes as a recommendation factor:
   - Age, date of birth, gender, race, caste, religion, nationality, disability, marital status, photo, or address beyond city level.
   - Name-based or location-based demographic proxies.
   - **University prestige** (degrees are evaluated by accredited educational level, not institutional elitism).
   - **Employer prestige** (all past employers are evaluated equally; FAANG/Fortune 500 bonuses are disabled).
   - **Career gaps** (employment gaps are not scored or penalized).
   - Inferred "culture fit" or subjective traits.
2. **Separation of Concerns:** System recommendations (`SCORED`, `REVIEW_REQUIRED`, `ABSTAIN`) and Human Decisions (`NEW`, `REVIEWING`, `SHORTLISTED`, `REJECTED`, `INTERVIEW`, `ARCHIVED`) are stored as strictly separate fields. The system cannot auto-reject candidates.
3. **Mandatory Rejection Rationale:** Recruiters documenting a candidate rejection must provide an evidence-based rationale, ensuring human accountability.

---

## 🔬 Note on Legacy Metrics (Truthful Reporting)

Previous prototype documents cited unvalidated claims, including a "97.8% domain classification accuracy" and an "86/100 production readiness score" on 3,856 resumes. **These metrics are unvalidated prototype claims** and are superseded by the empirical gold-set evaluation methodology detailed in [docs/v2-release/EVALUATION.md](docs/v2-release/EVALUATION.md).

---

## 🚀 Core Capabilities

- **Versioned Job Criteria:** Define criteria with explicit weights (Skills, Experience, Keywords, Education) and tracked `job_version` lineage.
- **Asynchronous PDF Extraction:** Dual-pass PyMuPDF parser with reading-order layout clustering and optional ODL fallback.
- **Graph-Based Skill Inference:** Transparent inference engine supporting direct, alias, implication, and related skills with explicit confidence weighting.
- **Evidence-First Inspector:** Clickable provenance linking candidate scores to verified resume sections and page regions.
- **B2B ATS Health Diagnostic:** Ephemeral, candidate-facing parseability check with layout risk overlays and transparent limitations disclaimer.
- **Security & Multi-Tenancy:** Multi-tenant organization scoping, signed session tokens (httpOnly cookies), rate limiting, security headers, and cascading deletion endpoints.

---

## 🛠️ Quick Start

### Prerequisites
- Python 3.13+
- Node.js 18+ and npm
- AWS LocalStack or AWS credentials (S3 & DynamoDB)

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Configure environment variables
cp ../.env.example ../.env

# Start development server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` to access the workspace.

### 3. Running Tests
```bash
cd backend
PYTHONPATH=. pytest tests/
```

---

## 📄 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
