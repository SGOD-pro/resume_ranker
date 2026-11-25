# SWYRA Sortlist v2 — Architecture Specification

> **Reviewed Baseline Commit:** `c9124c3de334c4b9024239acac4752a9bbb88d7e`  
> **Release Target:** `v2.2 — Serverless Pipeline, Evidence Integrity, and Strict Relevance Scoring`  
> **Authoritative Companion:** See [`architecture.md`](file:///home/swyra/projects/resume_ranker/architecture.md) for full serverless diagrams and queue lifecycle specifications.

---

## 1. Architecture Overview: Modular Serverless Topology

SWYRA Sortlist combines the architectural simplicity of a modular codebase with the elastic durability of AWS Serverless.

- **Frontend:** React 18, TypeScript, Vite, Zustand, Tailwind CSS, shadcn/ui.
- **Backend API:** Python 3.13, FastAPI, Mangum adapter for AWS Lambda.
- **Persistence Tier:** AWS DynamoDB single-table design (`PAY_PER_REQUEST` billing mode) + AWS S3 for binary PDF resumes, structured extraction JSONs, and scoring snapshots.
- **Queueing & Async Execution:** AWS SQS queues (`Stage1Queue`, `Stage2Queue`, `ScoringQueue`, and DLQs) triggering isolated AWS Lambda worker functions.
- **Local Dev Monolith:** Self-contained background runner (`worker_runner.py`) using in-memory queues and a 6-process isolated PyMuPDF worker pool.

---

## 2. Ingestion Paths: Presigned Direct S3 vs. Local Proxy

### A. Canonical Production Path: Direct Browser-to-S3 Uploads
1. **Presigned Upload Request:** Client requests presigned upload capabilities via `POST /api/v2/jobs` (presigned POST) or `POST /api/v2/jobs/{job_id}/upload-sessions` (presigned PUT).
2. **Direct Browser Streaming:** Resumes are uploaded directly from the browser to AWS S3. Client-side concurrency is strictly bounded to 4–6 parallel streams.
3. **Zero Buffer in Lambda:** Large multi-megabyte PDF bodies bypass API Lambda RAM completely. API Lambda memory is reserved for sub-50ms JSON request processing.
4. **Finalize Barrier:** Once uploads complete, client invokes `/finalize`. The backend marks any uncompleted files as `REMOVED`, initializes the atomic barrier `job.remaining = usable_files`, and triggers Stage 1 extraction.

### B. Compatibility Path: Backend Upload Proxy
- Endpoint: `POST /api/v2/jobs/{job_id}/resumes` (multipart/form-data).
- Preserved strictly for local development without AWS credentials, automated curl tests, and backwards compatibility.

---

## 3. Serverless Execution Stages & Queues

| Stage / Queue | Lambda Worker Function | Timeout / Visibility | Purpose & Processing Engine |
| :--- | :--- | :---: | :--- |
| **`Stage1Queue`** | `Stage1WorkerFunction` | 120s / 180s | In-memory PyMuPDF text & reading order extraction. Clean layouts ($\ge 0.90$) transition directly to `S2_DONE` and decrement the barrier. |
| **`Stage2Queue`** | `Stage2WorkerFunction` | 180s / 300s | Fallback engine handling ODL JVM layout reconstruction (`needs_odl`) and Amazon Bedrock Nova Micro infill (`needs_nova`). |
| **`ScoringQueue`** | `ScoringWorkerFunction` | 120s / 240s | Deterministic candidate scoring, BM25 skill calculation, and factor ledger generation. |
| **`DLQs`** | `DlqConsumerFunction` | 60s / 120s | Consumes exhausted messages (maxReceiveCount = 3), marks file status `FAILED`, and decrements the barrier counter to prevent deadlocks. |

---

## 4. Concurrency & Safety Controls

1. **PyMuPDF Thread Safety:** PyMuPDF runs strictly single-threaded per process. Six workers in local benchmark execution are managed as 6 isolated operating system processes, never threads within a shared process.
2. **Independent Concurrency Limits:** 6 local worker processes does not equal 6 Lambda invocations. AWS Lambda scales automatically based on SQS batch size and concurrency configurations.
3. **Session Query Scalability:** Active session verification queries DynamoDB using `PK=ORG#{org_id}` and `SK begins_with('ACTIVE_SESSION#')`. This is an **org-partition key-prefix query, not an O(1) constant or GSI, and does not guarantee 1 RCU**. Pointers are pruned on finalization and expiry.
4. **Batch Item Failures:** `ReportBatchItemFailures` is enabled on all SQS event source mappings. When Bedrock or downstream dependencies encounter throttling, only the specific failed `messageId` is returned for retry.

---

## 5. Non-Negotiable Scoring & Ethics Policy

- **Relevance Scoring Only:** Scores reflect alignment with explicit job requirements, never subjective "hiring quality".
- **Zero Protected Attributes:** Age, gender, race, nationality, religion, disability, photo, and proxies are never extracted or scored.
- **No Prestige or Gap Penalties:** FAANG bonuses, university prestige scoring, and career gap penalties are permanently eliminated.
- **Auditable Factor Ledgers:** Every candidate score includes a complete breakdown of points, sources, confidence scores, and rule versions.
