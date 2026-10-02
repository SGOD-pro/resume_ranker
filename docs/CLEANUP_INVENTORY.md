# SWYRA Sortlist — Code Cleanup & Architectural Inventory

> **Reviewed Baseline Commit:** `c9124c3de334c4b9024239acac4752a9bbb88d7e`  
> **Target Release:** `v2.2 — Serverless Pipeline, Evidence Integrity, and Strict Relevance Scoring`  
> **Status:** Authoritative maintainer reference for symbol, module, and data model classifications.

---

## 1. Classification Definitions

Every surveyed symbol, file, or pattern is assigned exactly one of the following seven standard classifications:

1. **`live canonical`**: Actively executed in production, current serverless handlers, or current frontend pathways. Must remain supported and maintained.
2. **`live compatibility`**: Actively used by existing integration tests, legacy clients, or backward-compatible API endpoints. Retained as a thin adapter delegating to canonical implementations.
3. **`duplicate implementation`**: Redundant logic performing identical or nearly identical operations. Must be consolidated onto canonical components with thin adapters where external callers exist.
4. **`unreachable`**: Completely orphaned code with zero internal, external, test, or configuration references. Safe to prune after verification.
5. **`historical evidence`**: Prior benchmark runs, audit notes, or exploratory prototypes preserved for empirical provenance. Retained without modification or build inclusion.
6. **`generated local output`**: Ephemeral local artifacts, cache files, test outputs, or virtual environments. Must not be tracked in version control.
7. **`unresolved`**: Ambiguous ownership or uncertain downstream dependencies. **Note: Unresolved is not permission to delete.** Requires explicit audit or deprecation cycle.

---

## 2. Cleanup Candidate Inventory

| Symbol / Path | References & Handlers | Classification | Proposed Action | Compatibility Impact | Validation Strategy |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **`src.pipeline.stage1_worker`** | `src.handlers.stage1.handler`, `infra/template.dev.yaml` (`Stage1WorkerFunction`), `run_1k_benchmark.py` | **`live canonical`** | Retain as the primary in-process PyMuPDF extraction engine for Stage 1. | Zero breaking change; primary production path. | Unit & integration tests; 1,000-resume benchmark. |
| **`src.pipeline.fast_parse_worker`** | `worker_runner.py`, `coordinator.py`, `test_durable_pipeline.py` | **`live compatibility`** / **`duplicate implementation`** | Retain as compatibility entrypoint for local execution; refactor shared parsing to common extraction routines. | Preserves local development runner and test assertions. | `pytest tests/integration/test_durable_pipeline.py`. |
| **`src.pipeline.stage2_worker`** | `src.handlers.stage2.handler`, `infra/template.dev.yaml` (`Stage2WorkerFunction`) | **`live canonical`** | Retain as the primary SQS worker for Stage 2 (handles both ODL layout repair and Bedrock/Nova field infill). | Zero breaking change; primary production path. | `pytest tests/unit/test_fallback_caps_and_stage2.py`. |
| **`src.pipeline.odl_batch_worker`** | `coordinator.py`, `worker_runner.py`, `test_durable_pipeline.py` | **`live compatibility`** | Retain as thin adapter delegating to ODL client routines for local runner mode. | Preserves legacy multi-worker local coordinator. | `pytest tests/integration/test_durable_pipeline.py`. |
| **`src.pipeline.nova_queue_worker`** | `coordinator.py`, `worker_runner.py`, `test_durable_pipeline.py` | **`live compatibility`** | Retain as thin adapter delegating to Nova fallback routines for local runner mode. | Preserves local test harnesses. | `pytest tests/integration/test_durable_pipeline.py`. |
| **`src.pipeline.scoring_worker`** | `src.handlers.scoring.handler`, `infra/template.dev.yaml` (`ScoringWorkerFunction`) | **`live canonical`** | Retain as primary Lambda SQS worker for candidate scoring, cohort BM25, and result publication. | Zero breaking change; primary production path. | `pytest tests/unit/test_lambda_handlers_and_batch_failures.py`. |
| **`src.pipeline.final_rank_worker`**| `coordinator.py`, `worker_runner.py`, `test_durable_pipeline.py` | **`live compatibility`** | Retain as compatibility layer delegating to `CandidateScorer` for local runner. | Preserves local background worker queue runner. | `pytest tests/integration/test_durable_pipeline.py`. |
| **`src.infrastructure.models.file.FileItem`** | `jobs_v2.py`, `files_repository.py`, `stage1_worker.py`, `stage2_worker.py`, `test_phase1_6_durability.py` | **`live canonical`** | Retain as authoritative entity model for the v2.2 durable serverless pipeline (`SK=FILE#{file_id}`). | Primary database model for file-level state machine. | All Phase 1.6 & v2.2 durability tests. |
| **`src.infrastructure.models.document.DocumentItem`** | `jobs_v2.py` (session PUT uploads), `documents_repository.py`, `fast_parse_worker.py`, `ResumeUploadZone.tsx` | **`live canonical`** | Retain as authoritative entity model for direct browser-to-S3 session-based uploads (`SK=DOC#{doc_id}`). | Powers frontend `uploadResumesViaSession` API contract. | Frontend upload integration & acceptance tests. |
| **`src.infrastructure.repositories.files_repository`** | `stage1_worker.py`, `stage2_worker.py`, `jobs_v2.py`, `dlq_consumers.py` | **`live canonical`** | Retain as primary repository for `FileItem` single-table operations and atomic decrements. | Core serverless data access layer. | Unit tests in `test_phase1_6_durability.py`. |
| **`src.infrastructure.repositories.documents_repository`**| `jobs_v2.py`, `fast_parse_worker.py`, `coordinator.py` | **`live canonical`** | Retain for `DocumentItem` session tracking and SHA-256 deduplication lookups. | Direct S3 PUT session workflow. | `test_endpoints.py`, `test_v2_acceptance.py`. |
| **`backend/deploy/`** (`template.yaml`, `samconfig.toml`) | SAM build/deploy configuration for legacy monolith | **`live compatibility`** / **`unresolved`** | Preserve legacy deployment templates alongside root `infra/template.dev.yaml`. Clarify in documentation that `infra/template.dev.yaml` is canonical for serverless v2.2. | Zero runtime impact; avoids breaking automated SAM CI scripts. | CloudFormation / SAM syntax linting. |
| **`backend/_1k_extracted_cache.json`** | Generated by local 1,000-resume benchmark | **`generated local output`** | Untracked from git via `git rm --cached`; ignored via `.gitignore`; preserved locally on disk. | Eliminates accidental exposure of sensitive resume texts in repository history. | `git status` verifies untracked; local script finds file. |
| **`backend/tests/benchmark_v4/`** | Benchmark logs, reports, and run artifacts | **`historical evidence`** | Retain unmodified as historical audit record for Phase 0 and Phase 3 performance milestones. | No production code imports these directories. | Read-only inspection; non-interference with `pytest`. |
| **`src.pipeline.coordinator`** | Local background pipeline runner | **`live compatibility`** | Retain for local dev-server execution where AWS Lambda and physical SQS are unavailable. | Allows backend to run self-contained locally via FastAPI background tasks. | Local end-to-end integration tests. |
| **`Logical Queue Aliases` vs `Physical SQS URLs`** | `queue_manager.py` vs `infra/template.dev.yaml` | **`live canonical`** | Standardize mapping in `QueueManager`: logical names (`STAGE1_QUEUE`, `STAGE2_QUEUE`, `SCORING_QUEUE`) dynamically resolve to environment SQS URLs in Lambda, or in-memory queues locally. | Ensures single unified queue interface for both local dev and AWS Lambda. | Tested in both local in-memory and simulated SQS modes. |

---

## 3. Ten Rules of Clean Architecture Adherence

1. **Rule 1 (Preserve Handlers):** All handler entry points defined in `infra/template.dev.yaml` (`stage1.lambda_handler`, `stage2.lambda_handler`, `scoring.lambda_handler`, `api.handler`) remain intact with strict signatures.
2. **Rule 2 (Consolidate Pipelines):** PyMuPDF page parsing, text extraction, and bounding box geometry are unified under `src.extraction.structural_parsing_service`.
3. **Rule 3 (Thin Adapters):** Legacy worker files (`fast_parse_worker.py`, `final_rank_worker.py`) are kept as thin wrappers to prevent test breakage.
4. **Rule 4 (Data Models):** `FileItem` (`FILE#`) and `DocumentItem` (`DOC#`) are explicitly documented as coexisting for separate upload contracts (presigned POST vs presigned PUT session).
5. **Rule 5 (Queue Unification):** Queue manager cleanly distinguishes between physical AWS SQS URLs and local in-process queue adapters.
6. **Rule 6 (Prune Dead Code):** No speculative or dead mock branches left unmaintained; unused temporary test stubs removed.
7. **Rule 7 (Preserve Security):** Tenant isolation (`org_id`), signed S3 URLs, atomic DynamoDB decrements, and scoring guardrails are 100% preserved.
8. **Rule 8 (Test Retention):** All existing test files under `backend/tests/unit/` and `backend/tests/integration/` are preserved and passing.
9. **Rule 9 (Scoring Invariance):** Relevance scoring formulas, BM25 pool math, and fairness constraints remain mathematically identical.
10. **Rule 10 (Clean Imports):** Deprecated imports and duplicate parsing passes eliminated from hot execution paths.
