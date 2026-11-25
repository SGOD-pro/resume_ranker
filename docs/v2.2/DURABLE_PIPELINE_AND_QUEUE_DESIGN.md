# SWYRA Sortlist v2.2 — Durable S3 + SQS Pipeline and Queue Design

> **Document Version:** 1.0.0  
> **Status:** Authoritative Architectural Design & Operational Runbook  
> **Target Release:** v2.2 (Durable Pipeline & Queue Architecture)

---

## 1. Executive Summary & Problem Statement

### 1.1 The Baseline Limitations
In previous iterations (v2.0 / v2.1), resume upload and extraction relied upon:
1. **Multipart HTTP API Buffering:** Resumes were uploaded directly to FastAPI endpoints (`POST /api/v2/jobs/{job_id}/resumes`) using multipart form data. When recruiters uploaded 40+ PDFs simultaneously, FastAPI buffered the payloads in memory or temp storage.
2. **Process-Local Locks & Global Rate Limits:** The global rate limiter enforced strict limits (`("/resumes", 15, 60)`), triggering HTTP `429 Too Many Requests` during bulk uploads. Furthermore, extraction synchronization depended on an in-memory dictionary of locks (`_extraction_locks = {}`), making horizontal scaling impossible and losing state on any worker restart.
3. **Synchronous or Un-durable Background Tasks:** FastAPI `BackgroundTasks` had no dead-letter queue, no message durability, no retry backoff, and no visibility into multi-stage layout fallbacks.

### 1.2 The v2.2 Architecture
Sortlist v2.2 introduces a **production-grade, decoupled S3 + SQS pipeline**:
- **Direct Browser-to-S3 Presigned Uploads:** The client requests presigned PUT URLs for all resumes in an upload session and uploads files directly to S3 with bounded client concurrency (4). File bytes never touch the FastAPI application server.
- **Durable Multi-Stage SQS Decoupling:** Work is split across dedicated SQS queues (`fast-parse`, `odl-batch`, `final-rank`, and a shared `dlq`), each with dedicated stateless worker routines and retry backoff.
- **DynamoDB Single-Table Barrier Synchronization:** Stage transitions are gated by atomic conditional evaluations in DynamoDB. Fast-parse and fallback workers atomically record document completions. When all documents reach terminal states, the pipeline triggers the final ranking stage.
- **Job Version Pinning:** Sessions capture `job_version` at initialization. If job criteria are modified during extraction, ranking executions with stale versions are rejected to prevent overwriting updated job requirements.

---

## 2. Architecture & Queue Topography

```
                    ┌──────────────────────────────────────────────┐
                    │               Recruiter Browser              │
                    └───────┬──────────────────────────────▲───────┘
                            │                              │
          1. Create Session │                              │ Real-Time SSE
       (POST /upload-sessions)                             │ Progress Stream
                            ▼                              │
                    ┌───────────────┐                      │
                    │  FastAPI API  ├──────────────────────┘
                    │    Server     │
                    └───┬───────┬───┘
     2. Return Presigned│       │ 4. Finalize Session
         PUT URLs       │       │    Enqueue Stage 1
                        ▼       ▼
    ┌─────────────┐   ┌───────────┐   ┌───────────────────────────┐
    │  Direct S3  │◄──┤  Browser  │   │      SQS Queue Tier       │
    │  Bucket     │   │  Upload   │   │                           │
    └──────┬──────┘   └───────────┘   │  ┌─────────────────────┐  │
           │                          │  │ fast-parse queue    │  │
           │ 5. Read PDF              │  └──────────┬──────────┘  │
           ▼                          │             │             │
    ┌───────────────┐                 │  ┌──────────▼──────────┐  │
    │  Fast-Parse   ├─────────────────┼─►│ odl-batch queue     │  │
    │    Worker     │                 │  └──────────┬──────────┘  │
    └──────┬────────┘                 │             │             │
           │ 6. Quality Gate & Write  │  ┌──────────▼──────────┐  │
           ▼    Extracted JSON        │  │ final-rank queue    │  │
    ┌───────────────┐                 │  └──────────┬──────────┘  │
    │   DynamoDB    │◄────────────────┼─────────────┘             │
    │ Single Table  │                 │  ┌─────────────────────┐  │
    └──────┬────────┘                 │  │ dead-letter queue   │  │
           │ 7. Barrier Trigger       │  │ (DLQ)               │  │
           ▼                          │  └─────────────────────┘  │
    ┌───────────────┐                 └───────────────────────────┘
    │  Final-Rank   │
    │    Worker     ├────────► S3 Scoring Snapshot & Ready Notification
    └───────────────┘
```

### 2.1 Queues & Routing Specifications

| Queue Name | Source / Producer | Consumer | Message Payload | DLQ Policy |
|---|---|---|---|---|
| `fast-parse` | `POST /finalize` API | `FastParseWorker` | `FastParseMessage(job_id, document_id, s3_key, session_id)` | MaxReceive: 3, DeadLetterTarget: `dlq` |
| `odl-batch` | `FastParseWorker` (on quality gate failure) | `ODLBatchWorker` | `ODLBatchMessage(job_id, document_id, s3_key, session_id)` | MaxReceive: 3, DeadLetterTarget: `dlq` |
| `final-rank` | Worker Barrier Check | `FinalRankWorker` | `FinalRankMessage(job_id, session_id, job_version)` | MaxReceive: 3, DeadLetterTarget: `dlq` |
| `dlq` | Exhausted retries from any stage | Operational Monitor | Any failed message payload with exception traceback | Retention: 14 days |

---

## 3. Upload & Stage Transition State Machine

#### 3.1 Upload Session States (`UploadSessionStatus`)

> **Decision Record — Binding:** *"Upload completion is not analysis completion."*  
> Uploading documents verifies S3 object existence, validates PDF headers, and executes fast preprocessing. Final ranking and fallback deep extraction are only triggered when the recruiter explicitly initiates analysis via `POST /api/v2/jobs/{job_id}/analysis`. The Analyze button in the frontend is unlocked as soon as uploads are registered, allowing immediate initiation or reconfiguration of criteria and scoring weights without waiting for background extraction to finish.

```
 [ UPLOADING ] ──(All files PUT & /finalize)──► [ FAST_PREPROCESSING ]
                                                       │
                                            (Fast-parse barrier)
                                                       │
                                                       ▼
                                              [ READY_TO_ANALYZE ]
                                                       │
                                   (Recruiter clicks Analyze / POST /analysis)
                                                       │
                                                       ▼
                                            [ ANALYSIS_REQUESTED ]
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           ▼                                                       ▼
                (Any doc needs ODL)                                      (All docs fast-parsed)
                           │                                                       │
                           │                                                       │
              [ FALLBACK_PROCESSING ]                                              │
                           │                                                       │
                           └───────────────────────────┬───────────────────────────┘
                                                       │
                                            (All parsing completed)
                                                       ▼
                                              [ FINAL_RANKING ]
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           ▼                                                       ▼
                 (All docs succeeded)                                    (Partial doc failures)
                           │                                                       │
                           ▼                                                       ▼
                       [ READY ]                                        [ READY_WITH_WARNINGS ]
```

- **`UPLOADING`**: Session created, presigned URLs issued. Waiting for browser to PUT files and call completion.
- **`FAST_PREPROCESSING`**: Finalize called. Documents queued in `fast-parse`. Structural parsing in progress. Analysis has not yet been requested by the recruiter.
- **`READY_TO_ANALYZE`**: Fast-parse barrier reached. Fast structural parsing complete. Awaiting recruiter analysis trigger.
- **`ANALYSIS_REQUESTED`**: Recruiter clicked Analyze (`POST /api/v2/jobs/{job_id}/analysis`). Background pipeline engaged.
- **`FALLBACK_PROCESSING`**: One or more complex multi-column documents routed to the JVM ODL parser.
- **`FINAL_RANKING`**: All documents have reached terminal parsing states. Ranking worker is scoring candidates against the pinned job description and recruiter weights.
- **`READY`**: All documents parsed and ranked successfully. Results available in DynamoDB and S3.
- **`READY_WITH_WARNINGS`**: Some documents failed parsing (e.g., corrupt PDF, unsupported font encoding), but valid documents were scored and ranked.
- **`FAILED`**: Critical session failure (e.g., all documents unparseable or job criteria deleted).

### 3.2 Document Extraction States (`DocumentStatus`)

- `UPLOAD_INITIALIZED` → `UPLOADED` (via lightweight Range header magic-bytes check, returns HTTP 202)
- `FAST_PARSE_QUEUED` → `FAST_PARSING`
- Terminal Fast-Parse States:
  - `STRUCTURED_PARSED`: Clean single-column layout extracted.
  - `NEEDS_ODL`: Complex column or reading order detected, routed to Stage 2.
  - `REVIEW_REQUIRED`: Extraction complete but confidence below threshold.
  - `REJECTED_DUPLICATE`: Document has identical SHA-256 to another document in the job.
  - `FAILED`: Document corrupt, non-PDF, or exceeded page limits.
- Terminal Fallback States:
  - `STRUCTURED_PARSED`: ODL extraction succeeded.
  - `REVIEW_REQUIRED`: ODL completed with warnings.
  - `FAILED`: ODL parser failed or timed out.

---

## 4. Barrier Synchronization & Concurrency Control

### 4.1 Fast-Parse Barrier & Recruiter Decoupling
When `FastParseWorker` completes processing a document:
1. It updates the document state to `STRUCTURED_PARSED`, `NEEDS_ODL`, `REVIEW_REQUIRED`, `REJECTED_DUPLICATE`, or `FAILED`.
2. It queries all documents associated with the `session_id`.
3. If all documents have completed fast-parse:
   - If `session.analysis_requested` is False: the session transitions to `READY_TO_ANALYZE` and pauses. No ODL or final ranking is run until the recruiter triggers analysis.
   - If `session.analysis_requested` is True:
     - If any document is in `NEEDS_ODL`, the session transitions to `FALLBACK_PROCESSING` and enqueues ODL batch messages.
     - If zero documents need ODL, the session transitions to `FINAL_RANKING` and enqueues a `FinalRankMessage`.

### 4.2 Fallback Barrier
When `ODLBatchWorker` completes a document batch:
1. It isolates per-document failures (recording `error_reason` without failing the entire batch) and updates document states to `STRUCTURED_PARSED`, `REVIEW_REQUIRED`, or `NEEDS_NOVA`.
2. It checks all session documents. If every document has reached a terminal parsing state (`STRUCTURED_PARSED`, `REVIEW_REQUIRED`, or `FAILED`), it transitions the session to `FINAL_RANKING` and enqueues `FinalRankMessage`.

### 4.3 Idempotency, Duplicate Detection & Stale Rank Protection
1. **Lightweight Completion:** `POST /documents/{doc_id}/complete` performs an S3 HEAD check and Range-request (`bytes=0-9`) magic-bytes check, marks `UPLOADED`, enqueues `FAST_PARSE_QUEUE`, and returns HTTP 202 immediately. It never downloads the full PDF or runs PyMuPDF on the HTTP request thread. Calling it multiple times for the same document returns HTTP 202 idempotently without duplicating SQS messages.
2. **Asynchronous Duplicate Detection:** Full PDF download and SHA-256 calculation occur inside `FastParseWorker`. If another document in the same job shares the identical content hash, the worker marks the duplicate `REJECTED_DUPLICATE`.
3. **Job Version Pinning:** When the recruiter triggers analysis (`POST /api/v2/jobs/{job_id}/analysis`), any updated weights or job criteria increment `job_version`. The session is pinned to this `job_version`. When `FinalRankWorker` dequeues a `FinalRankMessage`, it verifies `message.job_version == job.job_version`. If criteria changed while ranking was in-flight, the stale ranking run is safely discarded.
4. **Daemon & Draining Discipline:** `BackgroundWorkerDaemon` is strictly gated behind `RUN_LOCAL_WORKERS=true` in FastAPI lifespan and is never run by default in production or containerized environments. FastAPI HTTP request handlers never invoke `drain_all_queues_sync()`.

### 4.4 Transactional Outbox Pattern for Zero Message Loss
To prevent the crash window between DynamoDB state writes and SQS message publishing:
1. When `POST /complete` executes, `write_outbox_and_send` records a `PENDING` outbox record in DynamoDB with a 24-hour TTL before publishing to SQS.
2. Upon successful SQS publication, the outbox record is immediately deleted.
3. If an unexpected server failure occurs before SQS send, the record remains in DynamoDB.
4. An outbox relay worker (`relay_pending_outbox`) periodically scans for orphaned `PENDING` records every 30 seconds and safely replays them to SQS.

---

## 5. Rate Limiting & 429 Elimination

### 5.1 The Root Cause of Legacy 429s
In Sortlist v2.0, `RateLimitMiddleware` applied a blanket per-client limit:
```python
("/resumes", 15, 60) # 15 requests per 60 seconds
```
Uploading 40 resumes sequentially or in parallel triggered HTTP 429 after the 15th file.

### 5.2 The v2.2 Fix
1. **Presigned Upload Session Endpoint:** `POST /api/v2/jobs/{job_id}/upload-sessions` registers the entire batch (up to 100 files) in a single request.
2. **Direct S3 Uploads:** S3 bucket PUT requests do not pass through the FastAPI application server or its rate limit middleware. S3 handles thousands of concurrent PUT requests natively.
3. **Completion Route Exemption:** Lightweight status acknowledgments (`POST /documents/{doc_id}/complete`) are scoped to legitimate authenticated sessions and exempt from aggressive multipart throttling.

---

## 6. Operational Runbook & Deployment Architecture

### 6.1 Monitoring Metrics
- **SQS Queue Depth:** Alert if `ApproximateNumberOfMessagesVisible` on `fast-parse` > 100 for > 5 minutes.
- **DLQ Alarm:** Alert immediately if `dlq` depth > 0.
- **Worker CPU & Memory:** Monitor container memory during high-volume PyMuPDF extraction.
- **Barrier Timeout:** If an upload session remains in `FAST_PARSING` or `FALLBACK_PROCESSING` for > 15 minutes, mark session `READY_WITH_WARNINGS` and rank available documents.

### 6.2 Dead Letter Queue Replay Procedure
To inspect and replay failed extraction messages:
```bash
# 1. Inspect DLQ messages
aws sqs receive-message --queue-url <DLQ_URL> --max-number-of-messages 10

# 2. Identify failure cause (e.g. S3 permission or corrupt file)
# 3. After resolution, redrive messages back to source queue
aws sqs start-message-move-task --source-arn <DLQ_ARN> --destination-arn <FAST_PARSE_ARN>
```

### 6.3 Local Development vs Cloud Execution
- **Local Dev Mode (`USE_REAL_SQS=False`):** Uses in-memory FIFO queue simulation. When `POST /finalize` is called, test runners or local servers drain queues synchronously via `drain_all_queues_sync(10)`.
- **Cloud Mode (`USE_REAL_SQS=True`):** Real AWS SQS queues and S3 buckets are utilized. The `BackgroundWorkerDaemon` polls queues continuously in background threads.

### 6.4 Standalone Worker Deployment (Production)
In production, queue consumption must be decoupled from the API web process:
- Dedicated worker process: `python backend/worker.py`
- Fail-fast enforcement: The worker exits immediately with code 1 if `USE_REAL_SQS != true` or queue URLs are missing.
- Supervisor Unit: Provided at `infra/resume-ranker-worker.service` (systemd service with graceful SIGTERM termination and auto-restart).
- Outbox Relay: Replays stuck messages every 30 seconds automatically.

### 6.5 Infrastructure as Code (IaC)
- **Provisioning Script:** `infra/queues.sh` (idempotent bash provisioning script with `--check` mode).
- **CloudFormation Template:** `infra/queues.yaml` (full SQS queues, DLQ, SNS topic, subscriptions, and CloudWatch alarms for DLQ and queue depth).

---

## 7. Verification Test Matrix

### 7.1 Durable Pipeline Integration Scenarios (`tests/integration/test_durable_pipeline.py`)

| Scenario ID | Test Function | Verified Behavior |
|---|---|---|
| **Scenario 1** | `test_scenario_1_bulk_40_resumes_upload_session_no_429` | 40 PDFs uploaded via direct presigned URLs without 429 rate limits, fast-parsed, and ranked. |
| **Scenario 2** | `test_scenario_2_duplicate_completion_and_duplicate_sqs_idempotency` | Duplicate S3 completions and duplicate SQS messages are handled idempotently. |
| **Scenario 3** | `test_scenario_3_stage_routing_odl_and_nova` | Clean PDFs route directly to fast-parse terminal state; complex layouts route to ODL fallback. |
| **Scenario 4** | `test_scenario_4_barrier_synchronization_before_fast_parse_completion` | Final ranking is strictly blocked until all documents finish fast-parsing. |
| **Scenario 5** | `test_scenario_5_partial_failure_diagnostics_and_ready_with_warnings` | Corrupt files fail gracefully; valid files are ranked; session reaches `READY_WITH_WARNINGS`. |
| **Scenario 6** | `test_scenario_6_stateless_worker_restart_resumability` | Workers resume sessions and documents directly from DynamoDB and S3 without in-memory state. |
| **Scenario 7** | `test_scenario_7_job_version_pinning_and_stale_rank_rejection` | Stale ranking messages generated against old job versions are rejected. |
| **Scenario 8** | `test_scenario_8_scoring_policy_and_ats_compatibility` | Scorer enforces strict fairness (0 prestige bonus, 0 gap penalty, strict identity resolution). |

### 7.2 Hardening & Unit Scenarios (`tests/unit/test_v2_2_hardening.py`)

| Test ID | Test Function | Verified Behavior |
|---|---|---|
| **Hardening 1** | `test_complete_document_upload_lightweight_returns_202` | `POST /complete` performs lightweight Range read (bytes=0-9) and returns HTTP 202 without downloading full PDF. |
| **Hardening 2** | `test_duplicate_completion_is_idempotent` | Multiple `/complete` requests return 202 without creating duplicate queue messages. |
| **Hardening 3** | `test_duplicate_pdf_marked_rejected_duplicate_in_worker` | Duplicate PDF content by SHA-256 is accurately identified and flagged as `REJECTED_DUPLICATE` in worker. |
| **Hardening 4** | `test_finalize_upload_session_fast_preprocessing_analysis_unrequested` | Session finalization pauses at `READY_TO_ANALYZE` without enqueuing final rank until explicit Analyze trigger. |
| **Hardening 5** | `test_trigger_analysis_sets_analysis_requested_and_pins_job_version` | Analyze trigger updates criteria, increments `job_version`, sets `analysis_requested=True`, and advances session. |
| **Hardening 6** | `test_odl_batch_worker_bounded_batches_and_isolation` | Bounded ODL batch isolates document failures, preventing whole-batch failure when one document is corrupt. |
| **Hardening 7** | `test_structured_429_error_diagnostics` | Exceeding active session quota produces structured JSON 429 error with `Retry-After: 60`. |

