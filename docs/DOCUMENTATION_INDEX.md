# SWYRA Sortlist — Documentation Index & Authority Registry

> **Reviewed Baseline Commit:** `c9124c3de334c4b9024239acac4752a9bbb88d7e`  
> **Release Target:** `v2.2 — Evidence Integrity, Serverless Pipeline, and Strict Relevance Scoring`  
> **Rule:** Exactly one authoritative document per topic. Historical, superseded, or scratchpad documents are clearly labeled with direct links to their canonical replacement.

---

## 1. Documentation Index Table

| Path | Topic Owner | Status | Reviewed SHA | Replacement Link / Canonical Authority | Summary & Scope |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `README.md` | Product & Architecture | **Canonical** | `c9124c3` | — | Repository entry point, capabilities, quickstart, serverless architecture summary, and limitations. |
| `AGENT.md` | Core Architecture | **Canonical** | `c9124c3` | — | Developer implementation protocol, phase contracts, and non-negotiable coding rules. |
| `architecture.md` | Infrastructure & Backend | **Canonical** | `c9124c3` | — | End-to-end serverless topology, physical SQS queues, logical stages, and barrier coordination. |
| `boundaries.md` | Core Architecture | **Canonical** | `c9124c3` | — | Non-negotiable architectural boundaries (PyMuPDF in-memory isolation, no scans, no websockets). |
| `decision.md` | Architecture | **Canonical** | `c9124c3` | — | Architectural Decision Records (ADRs): S3 presigned PUT, SQS queue stages, DynamoDB single-table. |
| `rules.md` | Core Architecture | **Canonical** | `c9124c3` | — | 10 golden rules for code safety, concurrency, idempotency, and bias-free scoring. |
| `design.md` | Backend & Data | **Canonical** | `c9124c3` | — | System design, component responsibilities, state machines, and data stores. |
| `mamori.md` | Maintainer | **Canonical** | `c9124c3` | — | Memory bridge recording V1 decisions, lessons learned, and V2.2 evolution. |
| `memory.md` | Maintainer | **Canonical** | `c9124c3` | — | Active development phase status, completed milestones, and immediate roadmap. |
| `phases.md` | Maintainer | **Canonical** | `c9124c3` | — | Formal phase definitions, scope boundaries, and verification gate exit criteria. |
| `project.md` | Product | **Canonical** | `c9124c3` | — | Business value, target users, problem statement, and product identity. |
| `projectrequirement.md` | Product | **Canonical** | `c9124c3` | — | Core functional and non-functional requirements and constraints. |
| `benchmark_methodology.md`| Evaluation | **Canonical** | `c9124c3` | — | Principles of benchmark truthfulness, measurement rigor, and anti-hallucination standards. |
| `prmopt.md`, `resume.md`, `tests.md`, `one_shot_doc.md` | Maintainer | **Removed** | `c9124c3` | [`AGENT.md`](file:///home/swyra/projects/resume_ranker/AGENT.md), [`docs/DOCUMENTATION_INDEX.md`](file:///home/swyra/projects/resume_ranker/docs/DOCUMENTATION_INDEX.md) | Obsolete scratchpad markdown files removed from repository. |
| `backend/README.md` | Backend Engineering | **Canonical** | `c9124c3` | — | Backend service setup, testing commands, module architecture, and environment configuration. |
| `backend/docs/` (`DOMAIN_DECISION.md`, `IMPLEMENTATION.md`, `implementation_plan.md`, `PROJECT_STRUCTURE.md`, `SCORING_ARCHITECTURE.md`) | Maintainer | **Removed** | `c9124c3` | [`docs/v2-release/ARCHITECTURE.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/ARCHITECTURE.md), [`docs/v2-release/SCORING-POLICY.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/SCORING-POLICY.md) | Obsolete V1 backend docs removed; canonical specifications in `docs/v2-release/`. |
| `backend/tests/benchmark_v4/ROOT_CAUSE_REPORT.md` | Evaluation | **Historical Evidence** | `c9124c3` | [`docs/v2.2/BASELINE_AND_GAPS.md`](file:///home/swyra/projects/resume_ranker/docs/v2.2/BASELINE_AND_GAPS.md) | Phase 0 benchmark root cause diagnostic analysis. |
| `backend/tests/benchmark_v4/V9_REPORT.md` | Evaluation | **Historical Evidence** | `c9124c3` | [`docs/v2-release/EVALUATION.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/EVALUATION.md) | V9 domain intelligence remediation report. |
| `backend/tests/benchmark_v4/phase3_strict_report.md` | Evaluation | **Historical Evidence** | `c9124c3` | [`docs/v2-release/EVALUATION.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/EVALUATION.md) | Phase 3 strict extraction benchmark report. |
| `backend/tests/benchmark_v4/report.md` | Evaluation | **Historical Evidence** | `c9124c3` | [`docs/v2-release/EVALUATION.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/EVALUATION.md) | Benchmark v7 ranking integrity report. |
| `docs/00_CLEANUP_RECOMMENDATIONS.md` through `docs/13_FILE_MAP.md`, `docs/project_report.md` | Maintainer | **Removed** | `c9124c3` | [`docs/v2-release/ARCHITECTURE.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/ARCHITECTURE.md), [`docs/CLEANUP_INVENTORY.md`](file:///home/swyra/projects/resume_ranker/docs/CLEANUP_INVENTORY.md) | Legacy V1 modular documentation series removed; canonical specifications in `docs/v2-release/`. |
| `docs/v2-release/PRODUCT.md` | Product Management | **Canonical** | `c9124c3` | — | Binding product specification: capabilities, decision states, fairness. |
| `docs/v2-release/ARCHITECTURE.md` | Core Architecture | **Canonical** | `c9124c3` | — | Authoritative architecture: serverless tiers, modular monolith, queues. |
| `docs/v2-release/SCORING-POLICY.md`| Ranking & Fairness | **Canonical** | `c9124c3` | — | Authoritative scoring policy: allowed/prohibited inputs, formulas, audit ledger. |
| `docs/v2-release/TRUST-SAFETY-PRIVACY.md` | Trust & Safety | **Canonical** | `c9124c3` | — | Auth, tenant isolation, PII policy, and prohibited discriminatory attributes. |
| `docs/v2-release/API-CONTRACTS.md` | API Layer | **Canonical** | `c9124c3` | — | Authoritative OpenAPI/REST and SSE contracts, error schemas, rate limits. |
| `docs/v2-release/DATA-MODEL.md` | Data Engineering | **Canonical** | `c9124c3` | — | DynamoDB single-table schema (PK/SK patterns), S3 key hierarchy. |
| `docs/v2-release/EVALUATION.md` | Evaluation & QA | **Canonical** | `c9124c3` | — | Benchmark methodology, gold set specification, and metric definitions. |
| `docs/v2-release/ACCEPTANCE-TESTS.md` | Quality Assurance | **Canonical** | `c9124c3` | — | Acceptance test criteria for security (P0), workflow (P1), scoring, and ATS. |
| `docs/v2-release/IMPLEMENTATION-PLAN.md` | Maintainer | **Canonical** | `c9124c3` | — | Phased engineering implementation roadmap. |
| `docs/v2-release/MIGRATION.md` | Data & Operations | **Canonical** | `c9124c3` | — | Migration plan from V1/early V2 to current architecture. |
| `docs/v2-release/AUDIT.md` | Maintainer | **Historical Evidence** | `c9124c3` | [`docs/CLAIM_LEDGER.md`](file:///home/swyra/projects/resume_ranker/docs/CLAIM_LEDGER.md) | Factual audit before v2 release. |
| `docs/v2.2/BASELINE_AND_GAPS.md` | Maintainer | **Canonical** | `c9124c3` | — | Technical gap analysis, name extraction heuristics audit, and fixes. |
| `docs/v2.2/DURABLE_PIPELINE_AND_QUEUE_DESIGN.md` | Infrastructure | **Canonical** | `c9124c3` | — | S3 presigned direct upload, SQS queue physical topologies, and barrier synchronization. |
| `docs/v2.2/EXTRACTION_QUALITY_AND_METRICS.md` | Extraction | **Canonical** | `c9124c3` | — | Single-pass layout signals, fallback routing reasons, and `/extraction-metrics` endpoint. |
| `docs/v2.2/IDENTITY_RESOLUTION.md` | Extraction | **Canonical** | `c9124c3` | — | Visual header extraction, contact adjacency scoring, and confidence gating. |
| `docs/v2.2/ATS_DIAGNOSTICS.md` | ATS Engineering | **Canonical** | `c9124c3` | — | ATS parseability scoring, bounding box geometry, and candidate feedback rules. |
| `docs/v2.2/PER_SESSION_LIMITS_LIMITATION.md` | Security | **Canonical** | `c9124c3` | — | Org-partition active session query semantics, rate limit bypass analysis, and mitigations. |
| `docs/v2.2/GIT_FILTER_REPO_PLAN.md` | Operations | **Canonical Plan** | `c9124c3` | — | Operational protocol for git history sanitization via `git-filter-repo`. |
| `docs/v2.2/POSTMORTEM_AB2C372C.md` | Operations | **Historical Evidence** | `c9124c3` | — | Concurrency-4 run incident postmortem and root cause findings. |
| `docs/v2.2/PRE_DELETION_SAFETY_CHECK.md` | Operations | **Canonical** | `c9124c3` | — | Safety verification protocol before file deletion or schema pruning. |
| `docs/v2.2/RELEASE_NOTES.md` | Maintainer | **Canonical** | `c9124c3` | — | Official release notes for v2.2. |
| `docs/v2.2/SAM_DEV_DEPLOY_GUIDE.md`| Infrastructure | **Canonical** | `c9124c3` | — | Step-by-step AWS SAM deployment guide for dev environment. |
| `docs/v2.2/STAGE2_PACKAGING_REPORT.md` | Infrastructure | **Canonical** | `c9124c3` | — | Container image packaging and size analysis for Stage 2 worker Lambda. |
| `docs/v2.2/PHASE1_6_VERIFICATION_REPORT.md` | Maintainer | **Historical Evidence** | `c9124c3` | — | Phase 1.6 verification gate evidence and pass sign-off. |
| `docs/v2.2/PHASE2_FRONTEND_CONTRACT.md` | Frontend & API | **Canonical** | `c9124c3` | — | Frozen frontend API integration contract for Phase 2. |
| `frontend/README.md` | Frontend Engineering | **Canonical** | `c9124c3` | — | Frontend architecture, Zustand stores, components, and build instructions. |
| `docs/CLEANUP_INVENTORY.md` | Maintainer | **Canonical** | `c9124c3` | — | Audit of code cleanup candidates, consolidation status, and verification. |
| `docs/CLAIM_LEDGER.md` | Maintainer & Evaluation | **Canonical** | `c9124c3` | — | Authoritative claim ledger reconciling performance, memory, accuracy, and serverless claims. |
