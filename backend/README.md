# SWYRA Sortlist — Backend Engine (v2.2)

FastAPI-powered modular monolith for durable candidate resume extraction, layout parsing, and explainable ranking.

---

## ⚡ 1,000 PDF Empirical Benchmark Summary

Evaluated on **1,000 real PDF resumes** across 16 worker threads on localhost (`127.0.0.1:8000`):

| Metric | Measured Value | Operational Significance |
| :--- | :--- | :--- |
| **Total Resumes Processed** | **1,000 resumes** (2,729 pages) | Avg 2.73 pages/resume, avg 118.5 KB/file |
| **Wall-Clock Processing Time** | **292.75 seconds** (~4.88 minutes) | Full end-to-end extraction across 16 worker threads |
| **Extraction Throughput** | **3.42 resumes / second (~205 resumes / minute)** | Sustained multi-threaded throughput |
| **Median (P50) Latency** | **3,909 ms** | Standard single/dual-page resume |
| **P90 Latency** | **8,761 ms** | 3–4 page dense structured resumes |
| **P95 Latency** | **10,246 ms** | Heavy multi-column documents |
| **P99 Latency** | **15,657 ms** | Long-form multi-page CVs (5+ pages) |
| **Skills Extraction Rate** | **96.9%** | Average 9.3 verified skills per resume |
| **Experience Extraction Rate** | **84.3%** | Average 2.6 past roles per resume |
| **Education Extraction Rate** | **59.0%** | Average 1.7 degrees/programs per resume |
| **Full Pool Scoring Time (1,000 Candidates)** | **11.37 seconds (88 candidates / second)** | Single-pass precomputed BM25 IDF ($O(N)$) |

---

## 🏗️ Architecture & Core Components

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
```

### Pipeline Stages
1. **Frontend -> Backend -> S3 Upload Proxy (`POST /api/v2/jobs/{job_id}/resumes`):**
   - Direct multipart file uploads. Validates `%PDF` magic bytes upfront.
   - Files are streamed to S3, records written to DynamoDB, and messages pushed to `FAST_PARSE_QUEUE`.
   - Bypasses S3 CORS entirely, enabling sub-50ms server boot.
2. **Stage 1 (PyMuPDF In-Memory Fast-Path):**
   - High-throughput C-based parsing (`fitz`) with reading order layout reconstruction and structural quality evaluation.
   - Clean documents ($\ge 0.90$) transition immediately to `S2_DONE` and decrement the job barrier.
3. **Stage 2 (ODL JVM Microbatching):**
   - Documents with complex multi-column or tabular layouts ($< 0.90$) route to `ODL_BATCH_QUEUE`.
   - Processed in bounded microbatches (up to 20 documents / 20MB budget) to amortize JVM initialization.
   - Buffer items are immediately purged from `ODL_BUFFER#` upon terminal transition.
4. **Stage 3 (Bedrock Nova LLM Infill):**
   - Target field infill invoked via `NOVA_QUEUE` only for unresolved critical fields. Protected by atomic session token budgets.
5. **Stage 4 (Barrier Synchronization & Deterministic Scoring):**
   - Atomic barrier counter (`remaining == 0`) automatically triggers `ScoringWorker`.
   - 100% deterministic ranking using precomputed BM25 IDF, TF-IDF role title cosine similarity, and zero prohibited attributes.
6. **Live SSE Streaming (`GET /api/v2/jobs/{job_id}/extract`):**
   - Streams real-time progress events directly to the frontend, eliminating poll loops.

---

## 🛡️ Durability & Self-Healing

- **Worker Lease Management:** All worker tasks claim items with a lease timestamp (`claim_expires_at`).
- **Outbox Reconciliation:** Periodic background sweep (`reconcile_outbox()`) identifies expired leases across `UPLOADED`, `S1_PROCESSING`, `S2_PROCESSING`, and `S1_DONE`, restoring stranded items to work queues if a worker crashes.
- **Barrier Self-Healing:** If all document records are terminal (`S2_DONE`, `FAILED`, `REJECTED_DUPLICATE`) but the job counter `remaining > 0`, the reconciler automatically self-heals the counter to `0` and dispatches `FinalRankWorker`.

---

## 🚀 Running Locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Start development server
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
