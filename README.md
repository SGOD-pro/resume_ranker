# SWYRA Sortlist — Explainable Candidate Review Workspace (v2.2)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.x-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Status: v2.2](https://img.shields.io/badge/Release-v2.2.0-blue.svg)](docs/DOCUMENTATION_INDEX.md)

> **Core Promise:** Every recommendation is evidence-linked, configurable, reviewable, and reversible by a human recruiter.

SWYRA Sortlist is **NOT** an autonomous hiring system and **NOT** a generic enterprise ATS. It is a focused, explainable candidate-review workspace built for small hiring teams (2–15 recruiters) and boutique agencies who need transparent, audit-ready screening assistance.

---

## 📚 Authoritative Engineering & Release Specifications

All architectural, operational, scoring, and performance decisions are governed by authoritative specifications:

| Specification | Description |
| :--- | :--- |
| [**DOCUMENTATION_INDEX.md**](docs/DOCUMENTATION_INDEX.md) | Authoritative documentation registry mapping every tracked document to its topic owner, status, and reviewed commit. |
| [**CLEANUP_INVENTORY.md**](docs/CLEANUP_INVENTORY.md) | Architectural code inventory tracking canonical handlers, compatibility adapters, and pruning rules. |
| [**CLAIM_LEDGER.md**](docs/CLAIM_LEDGER.md) | Binding claim registry linking empirical benchmarks, memory measurements, and verification statuses. |
| [**architecture.md**](architecture.md) | Serverless architecture, SQS queue topologies, direct S3 upload flows, and compact lifecycle Mermaid diagrams. |
| [**docs/v2-release/ARCHITECTURE.md**](docs/v2-release/ARCHITECTURE.md) | Monolith-to-serverless transition guide, SQS worker topologies, and provider adapter specifications. |
| [**docs/v2-release/PRODUCT.md**](docs/v2-release/PRODUCT.md) | Product identity, target users, human decision workflows, core capabilities, and scope boundaries. |
| [**docs/v2-release/API-CONTRACTS.md**](docs/v2-release/API-CONTRACTS.md) | Complete REST API reference, direct S3 presigned upload sessions, SSE streams, and rate limits. |
| [**docs/v2-release/SCORING-POLICY.md**](docs/v2-release/SCORING-POLICY.md) | Binding scoring mathematics, allowed vs. prohibited inputs, knockout rules, and factor ledger schema. |
| [**docs/v2-release/TRUST-SAFETY-PRIVACY.md**](docs/v2-release/TRUST-SAFETY-PRIVACY.md) | Non-negotiable fairness policy, tenant data isolation, audit logging, and ATS checker privacy. |
| [**docs/v2-release/EVALUATION.md**](docs/v2-release/EVALUATION.md) | Evaluation methodology, gold-set validation, benchmark protocol, and audit of legacy claims. |

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

Previous prototype documents cited unvalidated claims, including a "97.8% domain classification accuracy" and an "86/100 production readiness score" on 3,856 resumes. **These metrics are unvalidated prototype claims** and are superseded by the empirical gold-set evaluation methodology detailed in [docs/v2-release/EVALUATION.md](docs/v2-release/EVALUATION.md) and [docs/CLAIM_LEDGER.md](docs/CLAIM_LEDGER.md).

---

## ⚡ Empirical Benchmark Results (1,000 Resumes)

Fresh empirical benchmark conducted on **1,000 real-world PDF resumes** using isolated processes (capped at 6 workers; PyMuPDF executed strictly single-threaded per process). Memory sampled concurrently every 50ms via `/proc/[pid]/statm` across parent and active workers.

### 1. Stage 1 Extraction Performance (6 Isolated Worker Processes)

| Metric | Measured Value | Measurement Details & Rigor |
| :--- | :--- | :--- |
| **Evaluated Corpus** | **1,000 Resumes** | 2,729 total pages (avg **2.73 pages/resume**), avg **118.5 KB/file** |
| **Wall-Clock Duration** | **6.76 seconds** | In-process extraction across 6 isolated OS processes |
| **Effective Throughput** | **147.94 resumes / sec** | **8,877 resumes / minute** sustained extraction rate |
| **Speedup vs. Baseline** | **5.53x speedup ratio** | **81.9% wall-clock time reduction** from ~37.40s sequential baseline |
| **Median (P50) Latency** | **32.95 ms** | Standard single/dual-page resume parse time |
| **Mean Latency per Doc** | **39.81 ms** | Average per-doc processing time across all pages |
| **P90 / P95 / P99 Latency** | **63.48 ms / 81.33 ms / 136.26 ms** | Dense multi-column and heavy tabular layouts |
| **Concurrent Peak RSS** | **618.3 MB** | Concurrent parent + 6 child workers sampled simultaneously |
| **Corpus Parity / Failures**| **0 parse failures (1,000/1,000)** | 100% completion accounting across full corpus |


> [!NOTE]
> **Scope Clarification:** The 6.76s result measures local in-memory Stage 1 parsing. It excludes network S3 transfer, DynamoDB round trips, and SQS serialization.

### 2. Candidate Scoring Performance (1,000 Candidates)

| Metric | Measured Value | Measurement Details |
| :--- | :--- | :--- |
| **Candidates Scored** | **1,000 candidates** | Multi-cohort ranking across 3 distinct job profiles (SWE, DevOps, Data Science) |
| **Scoring Wall-Clock** | **67.62 milliseconds** | Full BM25 cohort calculation, TF-IDF role matching, and factor ledger generation |
| **Scoring Peak RSS** | **139.0 MB** | In-process peak memory during full 1,000 candidate ranking run |
| **Observed Eligibility** | **100% on qualified fixtures** | Scorer-valid date ranges eliminate false knockout rejections |

### 3. Stage 1 Fallback Routing Decisions

```text
Total Resumes: 1,000
├── Clean Fast-Path (S2_DONE): 171 (17.1%) — Direct single-pass PyMuPDF completion
└── Fallback Required: 829 (82.9%) — Overlapping routing policy decisions
    ├── needs_odl = True: 688 (68.8%) — Multi-column / non-linear layout repair
    └── needs_nova = True: 440 (44.0%) — Name or critical section infill
```

> [!IMPORTANT]
> **Routing Decisions vs. Provider Calls:** The fallback counts (`829 total`, `688 needs_odl`, `440 needs_nova`) reflect **overlapping routing policy evaluations**, not disjoint counts and **not live cloud API calls**. A single document with complex layout and missing skills triggers both flags. In local runs without `ENABLE_ODL` or `ENABLE_NOVA`, no remote provider calls are made.

---

## 🛠️ Quick Start

### Prerequisites
- Python 3.13+ (managed via `uv`)
- Node.js 18+ and npm
- AWS LocalStack or AWS credentials (S3 & DynamoDB)

### 1. Backend Setup
```bash
cd backend

# Install dependencies with uv
uv sync

# Configure environment variables
cp ../.env.example ../.env

# Start development server
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` to access the workspace.

### 3. Running Verification Tests & Benchmark
```bash
cd backend

# Run all unit tests
uv run pytest tests/unit/

# Run integration tests
uv run pytest tests/integration/

# Run 1,000 resume empirical benchmark
uv run python scripts/run_1k_benchmark.py --workers 6
```

---

## 📄 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
