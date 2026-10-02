# SWYRA Sortlist — Architectural & Performance Claim Ledger

> **Reviewed Baseline Commit:** `c9124c3de334c4b9024239acac4752a9bbb88d7e`  
> **Target Release:** `v2.2 — Evidence Integrity, Serverless Pipeline, and Strict Relevance Scoring`  
> **Status:** Binding engineering claim registry with verifiable evidence links, measurement parameters, and verification labels.

---

## 1. Claim Verification Labels

Every technical claim in this repository is categorized using one of six strict verification states:

| Label | Definition | Required Evidence |
| :--- | :--- | :--- |
| **`locally verified`** | Executed and confirmed passing in the local development/test environment. | Exact command, environment details, terminal output, and passing tests. |
| **`real-AWS verified`** | Deployed and measured against live AWS infrastructure (Lambda, DynamoDB, SQS, S3). | CloudWatch logs, AWS execution ARNs, and real latency metrics. |
| **`implemented`** | Fully coded in source and configuration, but awaiting empirical verification gate. | Code links, unit tests, and architecture specs. |
| **`proposed`** | Planned architectural capability or optimization not yet completely implemented. | Design spec, ADR, or roadmap issue. |
| **`deprecated`** | Historical implementation or metric superseded by modern architecture. | Replacement link and deprecation rationale. |
| **`unverified`** | Unsubstantiated marketing claim, legacy assertion, or speculative estimate. | Flagged for audit, clarification, or retraction. |

---

## 2. Core Technical Claims Ledger

### A. Performance & Latency Claims

| ID | Claim Description | Baseline / Target | Measured Reality | Status | Evidence & Artifact Links |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **PERF-01** | Stage 1 local extraction speed for 1,000 PDF resumes across 6 isolated worker processes. | ~37.40s baseline (early sequential/unoptimized) | **6.76 seconds wall-clock** (147.94 docs/sec, 8,877 docs/min). Mean per-doc latency: 39.81ms, P50: 32.95ms, P99: 136.26ms. | **`locally verified`** | Artifact: [`backend/benchmark_1k_results.json`](file:///home/swyra/projects/resume_ranker/backend/benchmark_1k_results.json)<br>Command: `uv run python scripts/run_1k_benchmark.py --workers 6`<br>Note: Measures local Stage 1 extraction only; excludes network S3 transfer, DynamoDB round trips, and SQS serialization. |
| **PERF-02** | Local extraction optimization speedup vs original v2.1 baseline. | Unsubstantiated "10x-20x" claims | **5.53x speedup ratio** (81.9% wall-clock time reduction from 37.40s to 6.76s). | **`locally verified`** | Comparative run between unoptimized single-process sequential parse and 6-worker isolated PyMuPDF process pool. |
| **PERF-03** | End-to-end multi-cohort candidate scoring latency for 1,000 resumes. | Unspecified | **67.62ms wall-clock** total across 3 domain cohorts (SWE, DevOps, Data Science) with full BM25, TF-IDF, experience parsing, and factor ledger generation. | **`locally verified`** | Benchmark output in [`backend/benchmark_1k_results.json`](file:///home/swyra/projects/resume_ranker/backend/benchmark_1k_results.json). |
| **PERF-04** | Live deployed AWS upload-to-final-results duration for 1,000 resumes. | "Under 60 seconds" | Awaiting formal staging cluster benchmark. Expected bounded by SQS concurrency and DynamoDB write scaling. | **`unverified`** / **`proposed`** | Real-AWS verification gate planned for multi-worker staging deployment. No live AWS timing claimed without CloudWatch telemetry. |

---

### B. Memory Consumption Claims

| ID | Claim Description | Theoretical Target | Measured Reality | Status | Evidence & Measurement Rigor |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **MEM-01** | Stage 1 extraction peak memory across 6 worker processes during full 1,000 resume run. | < 1,024 MB | **618.3 MB concurrent peak RSS** (parent process + 6 child workers sampled simultaneously at 50ms intervals via `/proc/[pid]/statm`). | **`locally verified`** | `ConcurrentMemorySampler` in [`backend/scripts/run_1k_benchmark.py`](file:///home/swyra/projects/resume_ranker/backend/scripts/run_1k_benchmark.py). Eliminates erroneous summation of non-overlapping child lifetimes. |
| **MEM-02** | CandidateScorer in-process peak memory during 1,000 candidate multi-cohort ranking. | < 256 MB | **139.0 MB peak RSS** for in-memory corpus scoring, BM25 term matrices, and factor ledgers. | **`locally verified`** | Dedicated scoring phase memory sampling in benchmark runner. |
| **MEM-03** | Direct browser-to-S3 upload memory impact on backend API Lambda. | Zero MB on backend | **Direct S3 upload eliminates multipart file body buffering in Lambda RAM** (no 10MB PDF chunks in memory). API Lambda RAM usage is strictly limited to minimal JSON request/response payloads (`create-upload-session`, `complete`, `finalize`). | **`locally verified`** | Architecture in `jobs_v2.py` and `infra/template.dev.yaml`. API Lambda memory sized to 512 MB. |

---

### C. Concurrency & Architectural Limits

| ID | Claim Description | Configured Limit | Architectural Reality | Status | Rigor & Constraints |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **CONC-01** | In-process PyMuPDF worker thread safety. | Single-threaded PyMuPDF per OS process | PyMuPDF runs strictly single-threaded per process. Six workers are spawned as **six isolated operating system processes** (`ProcessPoolExecutor`), never multi-threaded within one process. | **`locally verified`** | Enforced in `stage1_worker.py` and `run_1k_benchmark.py`. Prevents MuPDF C-library global state corruption. |
| **CONC-02** | Relationship between 6 local benchmark workers and AWS Lambda concurrency. | 6 local worker processes != 6 Lambda invocations | Independent limits. In AWS Lambda, each invocation runs in its own sandboxed execution environment. Lambda concurrency is governed by SQS trigger batch size (10) and account reserved concurrency, not in-process process pools. | **`implemented`** | Documented in `infra/template.dev.yaml` and `docs/DOCUMENTATION_INDEX.md`. |
| **CONC-03** | Organization active upload session limits and query scalability. | Bounded concurrent uploads per org | Active session lookup uses an **org-partition base-table key-prefix query** (`PK=ORG#{org_id}`, `SK begins_with('ACTIVE_SESSION#')`). This is **not O(1), not a GSI, and does not guarantee 1 RCU**; it consumes RCUs proportional to matching session pointer count and item size. Stale pointers are reconciled during admission and finalized on completion. | **`locally verified`** | Tested in `test_presigned_post_and_limits.py` and documented in `docs/v2.2/PER_SESSION_LIMITS_LIMITATION.md`. |

---

### D. Queueing, Batching & Retries

| ID | Claim Description | Target Behavior | Verified Implementation | Status | Evidence & Test Suite |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **QUEUE-01**| SQS Partial Batch Failure isolation via `ReportBatchItemFailures`. | Failed messages must not re-drive the entire microbatch | Enabled on all SQS event source mappings (`Stage1Queue`, `Stage2Queue`, `ScoringQueue`, and DLQ triggers). Workers catch per-record exceptions and return `batchItemFailures: [{"itemIdentifier": msg_id}]`. Only failed items are retried. | **`locally verified`** | Configured in `infra/template.dev.yaml`; unit tested in `test_lambda_handlers_and_batch_failures.py`. |
| **QUEUE-02**| SQS Visibility Timeout fencing strictly exceeding Lambda execution timeouts. | VisibilityTimeout > Function Timeout | Configured across all queues:<br>• `Stage1Queue`: 180s visibility > 120s timeout.<br>• `Stage2Queue`: 300s visibility > 180s timeout.<br>• `ScoringQueue`: 240s visibility > 120s timeout.<br>• `DLQ`: 120s visibility > 60s timeout. | **`locally verified`** | Validated via `infra/template.dev.yaml` and `test_lambda_handlers_and_batch_failures.py`. |
| **QUEUE-03**| Bedrock / Nova rate limit backoff and error isolation in Stage 2 microbatches. | Throttling on one file must not fail peer files in microbatch | Individual file failures (including Bedrock 429 throttling) are caught per record, marking the individual message failed while allowing valid peer extractions to succeed. | **`locally verified`** | Tested in `backend/tests/unit/test_lambda_handlers_and_batch_failures.py`. |

---

### E. Extraction & Ranking Accuracy Claims

| ID | Claim Description | Historical Claim | Verified Status & Ground Truth | Status | Truthfulness & Evidence |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **ACC-01** | "97.8% Domain Classification Accuracy" and "86/100 Production Readiness". | Claimed in legacy v1 documents | **UNVALIDATED legacy marketing claims.** Explicitly retracted. Current accuracy is measured via versioned gold sets with labeled ground truth. | **`deprecated`** / **`unverified`** | Documented in [`docs/v2-release/EVALUATION.md`](file:///home/swyra/projects/resume_ranker/docs/v2-release/EVALUATION.md). |
| **ACC-02** | Field presence is evidence of extraction coverage, not precision/recall. | Field presence implies accuracy | Field presence metrics indicate parser yields, not ground-truth correctness. Precision, recall, and identity accuracy require hand-annotated gold sets. | **`locally verified`** | Documented in `docs/v2.2/EXTRACTION_QUALITY_AND_METRICS.md`. |
| **ACC-03** | Stage 1 fallback routing decisions vs live provider calls. | 829 fallbacks, 688 ODL, 440 Nova | These are **overlapping routing policy evaluations**, not mutually exclusive counts and **not live cloud API calls**. A single document with complex layout and missing skills triggers both `needs_odl=True` and `needs_nova=True`. In local runs without `ENABLE_ODL` or `ENABLE_NOVA`, no remote network calls are made. | **`locally verified`** | Detailed in benchmark provenance logs and `docs/v2.2/BASELINE_AND_GAPS.md`. |
| **ACC-04** | Synthetic candidate mutation fixture eligibility in benchmark tests. | Qualified candidates falsely knocked out | Mutated synthetic candidates in `run_1k_benchmark.py` were previously missing calendar date strings, causing experience parser to yield 0.0 years and trigger knockouts. Added explicit `years` fallback in `compute_total_experience_years` and valid calendar dates to fixtures, resulting in **100% eligibility for qualified candidates**. | **`locally verified`** | Fixed in `src/ranking/similarity.py`; verified in fresh benchmark run. |

---

### F. Security, Privacy & Sensitive Data Remediation

| ID | Remediation Item | Prior Vulnerability | Remediation Executed | Status | Verification |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **SEC-01** | Tracking of sensitive candidate resume cache in git repository. | `backend/_1k_extracted_cache.json` tracked real candidate details in git history. | File untracked via `git rm --cached backend/_1k_extracted_cache.json`. Added `_1k_extracted_cache.json`, `*_extracted_cache.json`, and `*.cache.json` to `.gitignore`. Local bytes preserved on disk for benchmark reproducibility without committing to git. | **`locally verified`** | `git status` verifies file is staged for deletion from index and ignored. |
| **SEC-02** | Tenant isolation and IDOR prevention. | Potential cross-tenant data leaks | Every DynamoDB partition key is scoped by `ORG#{org_id}`. S3 object storage prefixes enforce `jobs/{job_id}/` tenant separation. Every API endpoint enforces session authentication and validates organization ownership. | **`locally verified`** | Acceptance tests in `tests/integration/test_v2_acceptance.py`. |
| **SEC-03** | Elimination of bias and prohibited scoring attributes. | Historical FAANG prestige bonus, university prestige, and career gap penalties | **100% removed.** Scorer contains zero prestige bonus functions, zero gap penalty logic, and zero demographic proxies. | **`locally verified`** | Tested in `tests/unit/test_scoring_policy_v2_2.py` and `tests/integration/test_scorer.py`. |
