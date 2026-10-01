# memory.md — SWYRA Sortlist V2.2
> Context window, operational state, and architectural history for SWYRA Sortlist.
> Last updated: 2026-09-30 (V2.2 Modular Monolith & Durable Worker Pipeline)

---

## 1. Current Project State

- **Architecture Version:** V2.2 — Modular Monolith with Durable Worker Pipeline, DynamoDB Outbox Pattern, and PyMuPDF Fast-Path In-Memory.
- **Active Branch:** `v2.1`
- **Application Status:**
  - Backend and Frontend fully implemented, hardened, and verified.
  - All test suites passing (`test_phase1_6_durability.py`: 12/12, `test_v2_acceptance.py`: 11/11, `test_endpoints.py`: 1/1).
  - Frontend production build verified (`npm run build`: 0 errors).
  - Background processes: All local servers (`uvicorn`, `vite`) are **STOPPED** as requested.
- **Deployment & Runtime Mode:**
  - Localhost development environment (`127.0.0.1:8000` / `localhost:5173`).
  - S3 (`resume-ranker-documents-local`) & DynamoDB (`resume_ranker_v2_local`) backed by AWS / LocalStack.
  - SQS adapter: In-memory queues for local dev (`FAST_PARSE_QUEUE`, `ODL_BATCH_QUEUE`, `NOVA_QUEUE`, `FINAL_RANK_QUEUE`), pluggable to real SQS for cloud deployment.
  - Worker execution: Managed by `BackgroundWorkerDaemon` (`src/pipeline/worker_runner.py`) running sub-second worker loops and outbox reconciliation.

---

## 2. Core Architectural Principles (Non-Negotiable)

1. **Upload Architecture: Frontend -> Backend -> S3**
   - The browser **NEVER** communicates directly with AWS S3.
   - All document uploads are sent to the FastAPI backend via multipart HTTP (`POST /api/v2/jobs/{job_id}/resumes`).
   - The backend validates the `%PDF` magic bytes, streams the PDF to S3, writes file metadata to DynamoDB, increments the job barrier counter, and dispatches parsing.
   - S3 CORS is unnecessary and disabled, eliminating startup network stalls.
2. **Fast Startup (<50ms)**
   - Synchronous network calls (such as `put_bucket_cors`) have been removed from the FastAPI startup lifespan. Boot time is sub-50ms.
3. **Durable Multi-Stage Pipeline with Outbox Pattern**
   - Work is partitioned across 4 discrete stages:
     - **Stage 1 (Fast-Parse):** In-memory PyMuPDF (`fitz`) text extraction, reading-order layout clustering, and structural quality gate evaluation.
     - **Stage 2 (ODL JVM Fallback):** Multi-column and tabular layouts failing the quality gate are grouped into bounded microbatches (up to 20 documents, 20MB budget) to amortize JVM initialization.
     - **Stage 3 (LLM Fallback):** Missing critical fields (e.g. candidate name or unparsed sections) invoke Amazon Bedrock Nova Micro with atomic token budget reservation.
     - **Stage 4 (Deterministic Scoring):** Triggered once all files reach terminal states. Runs deterministic BM25 with fixed IDF, TF-IDF role matching, and component scoring.
4. **Crash Durability & Self-Healing**
   - **Worker Lease Tracking:** Each worker claims items with a lease timestamp (`claim_expires_at`).
   - **Outbox Reconciliation:** `reconcile_outbox()` in `files_repository.py` scans for expired worker leases across all active processing states (`UPLOADED`, `S1_PROCESSING`, `S2_PROCESSING`, `S1_DONE`). Stranded items are automatically re-enqueued, preventing hung jobs if a worker crashes or is SIGKILL'd.
   - **Barrier Self-Healing:** If all files reach terminal status (`S2_DONE`, `FAILED`, `REJECTED_DUPLICATE`) but the job counter `remaining > 0`, the outbox reconciler resets `remaining = 0`, updates `usable_files`, and triggers `ScoringWorker`.
   - **ODL Buffer Lifecycle Cleanup:** Files entering Stage 2 are registered in `ODL_BUFFER#` and immediately purged upon terminal transition or batch completion, preventing queue skip spam and memory leaks.
5. **Separation of System Recommendation and Human Decision**
   - System outputs: `SCORED`, `REVIEW_REQUIRED`, `ABSTAIN`.
   - Human decisions: `NEW`, `REVIEWING`, `SHORTLISTED`, `REJECTED`, `INTERVIEW`, `ARCHIVED`.
   - The system **never** auto-rejects candidates. Rejections require an evidence-based human rationale.
6. **Zero Prohibited Scoring Factors**
   - The scoring engine strictly enforces zero bias:
     - **No university prestige bonus** (all accredited degrees equal).
     - **No employer prestige bonus** (FAANG/Fortune 500 bonuses eliminated).
     - **No career gap penalties** (employment gaps are never penalized).
     - **No demographic factors** (age, gender, ethnicity, religion, photos, and proxies are prohibited).
7. **Client-Side Weight Recalculation**
   - Slider adjustments for component weights (Skills, Experience, Keywords, Education) are recomputed in-memory in the frontend using memoized selectors. Zero network requests or re-scoring calls on slider changes.
8. **Real-Time Communication via SSE**
   - Server-Sent Events (`GET /api/v2/jobs/{job_id}/extract`) stream live extraction and scoring progress. No WebSockets or poll loops.

---

## 3. Key Bug Fixes & Hardening Log

### Durability, Worker, and Startup Fixes
| Issue / Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| **Backend hangs for 24+ seconds on boot** | `src/main.py` called `put_bucket_cors` synchronously over network TLS to AWS `ap-south-1` during startup. | Removed `put_bucket_cors` from startup. Browser uploads to FastAPI proxy, so S3 CORS is unnecessary. Startup reduced from ~24s to <50ms. |
| **Processing hangs indefinitely at "Processing Resumes..."** | A worker task was terminated mid-run, leaving 1 file in `S1_PROCESSING` with an expired lease (`claim_expires_at`). Outbox reconciler only checked `S1_DONE`. Job barrier `remaining` stayed at 1. | Updated `reconcile_outbox` in `files_repository.py` to scan all files when `rem > 0`. Any file in `UPLOADED` or `S1_PROCESSING` with an expired lease is re-enqueued to `FAST_PARSE_QUEUE`. |
| **Worker log spam: "already terminal (FileStatus.S2_DONE), skipping"** | Files entering Stage 2 were registered in `ODL_BUFFER#` but only removed if routed through the JVM batch chunk. Bypassed or completed files remained in buffer. | Added buffer cleanup to `files_repository.py` (`transition_file_terminal`) and `stage2_worker.py` (`process_stage2_batch`). Stale items purged from DynamoDB. |
| **Non-PDF files causing silent worker crashes** | Upload endpoint accepted any file stream without magic bytes verification. | Added `%PDF` header validation in `upload_resumes_multipart`. Invalid files are rejected upfront with descriptive error payloads. |
| **Cross-tenant / cross-session security leakage** | Session ownership checks were permissive for cross-org requests. | Added strict org-level matching in `enforce_session_ownership`, returning HTTP 403 Forbidden on tenant mismatch. |

### Frontend UI & Data Display Fixes
| Issue / Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| **Candidates missing from UI after scoring completes** | When candidates had criteria knockouts (e.g. experience exceeding max or missing must-haves), they received `signal: 'knockout'`. `candidate-store.ts` had `showKnockouts: false` by default, hiding all candidates. | Changed `candidate-store.ts` default to `showKnockouts: true`, matching `docs/v2-release/SCORING-POLICY.md`. All candidates are visible, with knockouts properly badged. |
| **Upload bar stuck at 0% then disappears** | Upload progress bar was listening to stale upload state rather than active multipart progress events. | Updated `ResumeUploadZone.tsx` and `UploadProgressBar.tsx` to accurately bind to multi-file upload progress. |
| **Browser showing Direct S3 URL errors** | Frontend previously attempted presigned direct S3 PUTs. | Switched strictly to `POST /api/v2/jobs/{job_id}/resumes` multipart proxy through FastAPI backend. |

---

## 4. Empirical 1,000 Resume Benchmark

Empirical benchmark conducted on **1,000 real-world PDF resumes** (2,729 total pages, avg 2.73 pages/resume, avg 118.5 KB/file) on localhost (`127.0.0.1:8000`):

### Extraction Throughput & Latency
- **Total Wall-Clock Time:** 292.75 seconds (~4.88 minutes) across 16 worker threads.
- **Sustained Extraction Throughput:** **3.42 resumes / second (~205 resumes / minute)**.
- **Latency Distribution:**
  - Median (P50): **3,909 ms**
  - P90: **8,761 ms**
  - P95: **10,246 ms**
  - P99: **15,657 ms** (long-form CVs, 5+ pages)
  - Min / Max: 232.56 ms / 42.43 s

### Field Extraction Quality
- **Skills Coverage:** **96.9%** (969/1,000 resumes, avg 9.3 verified skills).
- **Experience Coverage:** **84.3%** (843/1,000 resumes, avg 2.6 past roles).
- **Education Coverage:** **59.0%** (590/1,000 resumes, avg 1.7 degrees).
- **Email / Phone:** 72.3% email, 76.3% phone.
- **Human Name Guardrails:** 54.8% clean pass without noise. Candidates with ambiguous identity headers are gated for Stage 2 fallback rather than guessing or hallucinating names.

### Scoring Engine Performance
- **Pool Size:** 1,000 candidates scored against job criteria.
- **Total Scoring Wall-Clock:** **11.37 seconds (11,374 ms)**.
- **Per-Candidate Scoring Latency:** **11.37 ms / candidate**.
- **Scoring Throughput:** **88 candidates / second**.

---

## 5. Key File Map (V2.2 Hot Path)

```text
backend/src/
├── api/
│   ├── routes/
│   │   ├── jobs_v2.py               # Multipart upload, SSE stream, scoring, audit routes
│   │   └── health.py                # Liveness & readiness probes
│   └── middleware/
│       └── rate_limit.py            # Token bucket & session rate limiting
├── extraction/
│   ├── extraction_pipeline.py       # Multi-stage extraction orchestrator
│   ├── structural_parsing_service.py# PyMuPDF fast-path + reading order clustering
│   ├── markdown_extraction_service.py # Regex field extractors
│   ├── odl_client.py                # ODL JVM client
│   └── fallback/nova_service.py     # Bedrock Nova LLM fallback
├── infrastructure/
│   ├── models/
│   │   ├── job.py                   # JobItem & JobStatus
│   │   ├── document.py              # FileItem & FileStatus
│   │   └── scoring.py               # ScoringRunItem
│   ├── repositories/
│   │   ├── jobs_repository.py       # Job CRUD & atomic barrier counters
│   │   └── files_repository.py      # File items, lease management, outbox reconciliation
│   ├── queue/
│   │   ├── queue_models.py          # QueueMessage schema
│   │   ├── sqs_client.py            # SQS client adapter
│   │   └── in_memory_queue.py       # Local in-memory queue adapter
│   └── storage/
│       └── storage_service.py       # S3 storage service (proxied file storage)
├── pipeline/
│   ├── coordinator.py               # Pipeline state coordinator
│   ├── fast_parse_worker.py         # Stage 1: PyMuPDF worker
│   ├── stage2_worker.py             # Stage 2: ODL microbatch worker & buffer management
│   ├── nova_queue_worker.py         # Stage 3: Nova LLM worker
│   ├── final_rank_worker.py         # Stage 4: ScoringWorker & barrier synchronization
│   └── worker_runner.py             # BackgroundWorkerDaemon for local development
└── ranking/
    ├── scorer.py                    # CandidateScorer (deterministic multi-signal scoring)
    ├── bm25_scorer.py               # BM25 scoring with precomputed IDF
    ├── skill_inference.py           # Skill graph inference
    └── domain_classifier.py         # Domain classification & guardrails

frontend/src/
├── lib/
│   ├── api.ts                       # Typed API client (proxying uploads to backend)
│   └── mapScoredCandidate.ts        # Backend DTO to frontend model mapping
├── store/
│   ├── app-store.ts                 # UI phase, upload progress, connection status
│   ├── candidate-store.ts           # Candidate state, filters, sorting (showKnockouts: true)
│   └── job-store.ts                 # Job criteria & component weights
├── components/
│   ├── candidates/
│   │   ├── CandidateListPanel.tsx   # Candidate list with virtualized rendering
│   │   ├── CandidateRow.tsx         # Single candidate row with badges & score
│   │   └── ResumeUploadZone.tsx     # Multipart resume upload dropzone
│   ├── detail/
│   │   ├── CandidateDetailPanel.tsx # Deep inspector with provenance highlights
│   │   └── MatchScoreSection.tsx    # Component breakdown & factor ledger
│   └── layout/
│       ├── AppHeader.tsx            # Header with navigation & branding
│       └── UploadProgressBar.tsx    # Live upload progress bar
└── pages/
    ├── DashboardPage.tsx            # Recruiter review workspace
    └── AtsCheckerPage.tsx           # B2B ATS Health Diagnostic tool
```

---

## 6. V2.2 Measured Reliability & Latency Refactor (Production State)

### Architecture & Pipeline Corrections
1. **Three Canonical Queues**:
   - `STAGE1_INGESTION_QUEUE` (`stage1_ingestion_queue`): Ingestion and PyMuPDF structural parsing.
   - `STAGE2_FALLBACK_QUEUE` (`stage2_fallback_queue`): Unified fallback queue handling both ODL microbatching and Bedrock Nova field infill.
   - `SCORING_QUEUE` (`scoring_queue`): Final ranking and scoring.
   - Bidirectional normalization in `LocalQueueAdapter` and `SqsQueueAdapter` preserves backwards compatibility for legacy aliases (`fast_parse_queue`, `odl_batch_queue`, `nova_queue`, `final_rank_queue`).
2. **Process-Isolated Stage 1 Execution**:
   - Official PyMuPDF documentation prohibits concurrent multithreaded use. Replaced all multithreaded `ThreadPoolExecutor` and `asyncio.to_thread` fitz parsing with bounded `concurrent.futures.ProcessPoolExecutor` worker processes (`max_workers=min(4, os.cpu_count() or 1)`), eliminating C-level memory corruption.
3. **Single Producer Path**:
   - API endpoints (`POST /api/v2/jobs/{job_id}/upload-sessions/.../complete`, `/finalize`, `/analysis`) strictly write to DynamoDB and enqueue messages / write outbox records. Eliminated direct background thread-pool submissions (`_fast_parse_pool.submit(...)`).
4. **Direct-to-S3 Presigned Upload Sessions**:
   - `POST /api/v2/jobs/{job_id}/upload-sessions` registers document metadata prior to generating signed PUT instructions.
   - `POST /api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{document_id}/complete` validates S3 object presence and checks PDF magic bytes using HTTP Range `bytes=0-9` without downloading full PDF bodies into API memory. Returns HTTP 202.
   - Bounded client upload scheduler (concurrency 4) prevents browser and network saturation.
5. **Decoupled Asynchronous Analysis**:
   - `POST /api/v2/jobs/{job_id}/analysis` and `/analyze` freeze immutable analysis parameters, increment `job_version`, accept in-flight uploads and pending Stage 1 parsing, describe pending counts, and return HTTP 202 immediately (<1s).
6. **Unified Stage 2 Routing**:
   - Handoff between ODL microbatches and Nova infill in `worker_runner.py`, `odl_batch_worker.py`, and `nova_queue_worker.py` ensures messages dispatched to `STAGE2_FALLBACK_QUEUE` route seamlessly according to message stage (`ODL_BATCH` vs `NOVA`), preventing dropped fallback tasks.

### Verification Suite Evidence
- **Unit Tests:** 90 passed / 90 total (100% pass rate) in 90s.
  - Hardening Suite (`test_v2_2_hardening.py`): 10 passed / 10 total.
  - Scoring Policy Suite (`test_scoring_policy_v2_2.py`): 7 passed / 7 total.
  - Phase 1.6 Durability Suite (`test_phase1_6_durability.py`): 12 passed / 12 total.
  - Presigned Post Limits (`test_presigned_post_and_limits.py`): 5 passed / 5 total.
  - Candidate Identity Resolver (`test_candidate_identity_resolver.py`): 2 passed / 2 total.
  - DLQ & Race Safety (`test_dlq_and_race_safety.py`): 5 passed / 5 total.
  - Terminal State Accounting (`test_terminal_state_accounting.py`): 6 passed / 6 total.
- **Integration Tests:** 19 passed / 19 total (100% pass rate) in 151s.
  - `test_endpoints.py`: 1 passed.
  - `test_scorer.py`: 8 passed.
  - `test_v2_acceptance.py`: 11 passed (Auth, tenant isolation, security headers, magic bytes, fairness policy, deterministic scoring).
- **Durable Pipeline Scenarios:** 8 passed / 8 total (100% pass rate) in `test_durable_pipeline.py`.
  - Scenario 1: 40-resume bulk upload session with concurrency 4, zero 429s, durable barrier.
  - Scenario 2: Duplicate completion & duplicate SQS message idempotency.
  - Scenario 3: Stage routing for clean PyMuPDF, ODL, and Nova.
  - Scenario 4: Barrier synchronization before fast parse completion.
  - Scenario 5: Partial failure diagnostics & READY_WITH_WARNINGS.
  - Scenario 6: Stateless worker restart & resumability.
  - Scenario 7: Job version pinning & stale rank rejection.
  - Scenario 8: Scoring policy & ATS diagnostic compatibility.
- **Total Backend Test Coverage:** 117 tests passing (100% pass rate).
- **Frontend Build:** `tsc -b && vite build` succeeded in 810ms with 0 errors.

