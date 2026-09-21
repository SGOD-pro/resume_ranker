# SWYRA Sortlist v2 — Architecture Specification

> **Note:** This document replaces all previous architecture documents and serves as the authoritative architecture reference for SWYRA Sortlist v2.

## Architecture Pattern

The system follows a **modular monolith** design. There is a single deployable unit per tier.

- **Frontend**: React 18 + TypeScript + Vite + Zustand + shadcn/ui + Tailwind CSS
- **Backend**: Python 3.13 + FastAPI + Uvicorn
- **Database**: DynamoDB single-table design (PAY_PER_REQUEST)
- **Object Storage**: S3 (PDFs, extracted JSON, scoring JSON)
- **Optional**: AWS Lambda via Mangum adapter for serverless deployment

## Module Map

The backend is structured to separate concerns while remaining a single cohesive unit:

```text
backend/src/
├── api/              # FastAPI routes, middleware, dependencies
│   ├── routes/       # jobs_v2.py, health.py (future: auth.py)
│   ├── middleware/   # (future: auth, rate-limit, security headers)
│   └── dependencies/ # (future: get_current_user, get_db)
├── ats/              # ATS scoring service, B2B scorer
├── config/           # Settings, AWS client factory
├── extraction/       # V2 pipeline: structural parsing → ODL → regex → Nova
├── extractors/       # Field parsers: contact, skills, experience, education, projects, layout
├── infrastructure/   # DynamoDB models, repositories, S3 storage, health
│   ├── models/       # job.py, document.py, scoring.py, upload_session.py
│   ├── queue/        # sqs_client.py, queue_models.py (durable SQS abstraction)
│   ├── repositories/ # jobs_repo, docs_repo, upload_sessions_repo
│   └── storage/      # storage_service.py (S3 presigned PUT, CORS, document storage)
├── pipeline/         # Durable stage workers & daemon
│   ├── fast_parse_worker.py  # Stage 1: structural parse & extraction
│   ├── odl_batch_worker.py   # Stage 2: JVM ODL fallback parser
│   ├── final_rank_worker.py  # Stage 3: barrier synchronization & scoring
│   └── worker_daemon.py      # Background worker daemon
├── ranking/          # Scorer, BM25, TF-IDF, skill inference, domain classifier
├── registries/       # Skill registry, section registry, skill graph, domain proximity
├── schemas/          # Pydantic/dataclass DTOs for extraction and scoring
└── services/         # Supporting services
```

## Data Flow

The system processes resumes through a durable, multi-stage pipeline decoupling direct browser uploads, SQS work queues, barrier synchronization, and final ranking.

```mermaid
sequenceDiagram
    participant C as Client (Browser)
    participant A as API (FastAPI)
    participant S3 as S3 Storage
    participant DB as DynamoDB
    participant Q as SQS Queues
    participant W as Pipeline Workers (Daemon)

    %% 1. Direct Presigned Upload Session
    C->>A: POST /upload-sessions (filenames, sizes, hashes)
    A->>DB: Create UploadSessionItem (Status: UPLOADING, pinned job_version)
    A->>DB: Create DocumentItems (Status: UPLOAD_INITIALIZED)
    A->>S3: Generate presigned PUT URLs
    A-->>C: Return upload session & presigned URLs

    %% 2. Direct S3 Upload & Completion
    loop Parallel Uploads (Bounded concurrency = 4)
        C->>S3: PUT /resumes/{doc_id}.pdf (Direct to S3)
        C->>A: POST /documents/{doc_id}/complete
        A->>DB: Update DocumentStatus: UPLOADED
        A-->>C: Acknowledged
    end

    %% 3. Finalize & Stage 1 Queueing
    C->>A: POST /upload-sessions/{id}/finalize
    A->>DB: Transition UploadSession: FAST_PARSING
    A->>Q: Enqueue FastParseMessage for each document
    A-->>C: Finalized (READY / FAST_PARSING)

    %% 4. Stage 1: Fast Parse Worker
    W->>Q: Poll fast-parse queue
    W->>S3: Fetch PDF
    W->>W: Structural parsing & quality gate
    alt Quality Gate Pass
        W->>S3: Write extracted JSON
        W->>DB: DocumentStatus: STRUCTURED_PARSED
    else Low Quality / Complex Layout
        W->>DB: DocumentStatus: NEEDS_ODL
        W->>Q: Enqueue ODLBatchMessage
    end
    W->>DB: Evaluate Fast-Parse Barrier

    %% 5. Stage 2: ODL Fallback (if needed)
    opt Complex Layouts
        W->>Q: Poll odl-batch queue
        W->>W: Run ODL JVM extraction
        W->>S3: Write extracted JSON
        W->>DB: DocumentStatus: STRUCTURED_PARSED or REVIEW_REQUIRED
        W->>DB: Evaluate Barrier
    end

    %% 6. Barrier Synchronization & Stage 3: Final Rank
    Note over W,DB: When all documents reach terminal parse states:
    W->>DB: Transition UploadSession: FINAL_RANKING
    W->>Q: Enqueue FinalRankMessage(job_id, session_id, job_version)
    W->>Q: Poll final-rank queue
    W->>DB: Verify job_version matches current job
    W->>S3: Read all extracted JSONs for job
    W->>W: Run explainable multi-signal scorer
    W->>S3: Write scoring run JSON
    W->>DB: Save ScoringRunItem
    W->>DB: Transition UploadSession: READY (or READY_WITH_WARNINGS)
```

## Key Design Decisions

1. **Direct Browser-to-S3 Uploads with Presigned PUTs**: Uploads bypass the API server entirely via short-lived, presigned S3 PUT URLs with strict CORS configurations. The API server never buffers 40+ PDFs in memory, eliminating process bottlenecks and 429 rate limit errors.
2. **Durable Multi-Stage SQS Pipelines**: Extraction and ranking are decoupled into discrete SQS queues (`fast-parse`, `odl-batch`, `final-rank`, and `dlq`). Failed messages undergo exponential backoff with jitter before routing to the DLQ, ensuring zero data loss.
3. **Barrier Synchronization**: Final ranking is gated by a barrier condition in DynamoDB. Only when all documents in an upload session reach a terminal parse state (`STRUCTURED_PARSED`, `REVIEW_REQUIRED`, or `FAILED`) does the pipeline enqueue the `FinalRankMessage`. Partial failures resolve to `READY_WITH_WARNINGS`.
4. **Job Version Pinning & Stale Rank Rejection**: Upload sessions and ranking messages pin the exact `job_version` active at session creation. If criteria change before ranking begins, stale ranking runs are dropped without overwriting updated criteria.
5. **Stateless Resumability & No In-Memory Locks**: Process-local locks (`_extraction_locks`) and FastAPI `BackgroundTasks` have been eliminated. Workers are completely stateless and horizontally scalable; workers can crash and restart without losing session or document progress.
6. **SSE for Real-Time Observability**: Clients monitor real-time extraction progress via Server-Sent Events (`GET /api/v2/jobs/{job_id}/upload-sessions/{session_id}/events`), streaming durable DynamoDB status changes.
7. **Deterministic Scoring**: All scoring is deterministic given the same inputs. BM25 uses dynamic pool IDF. No LLM or non-deterministic component is used in score computation.

## Optional Adapters (Feature-Flagged)

| Adapter | Purpose | Flag | Default |
|---------|---------|------|---------|
| ODL (JVM) | Multi-column PDF parsing | `ENABLE_ODL` | `false` (degrades gracefully) |
| Bedrock/Nova | LLM field infill | `ENABLE_NOVA` | `false` (degrades gracefully) |

## What Is NOT In This Architecture

- No microservices
- No Kubernetes
- No vector databases or RAG
- No WebSockets
- No agent frameworks
- No new cloud products beyond S3, DynamoDB, and SQS

## Deployment Modes

1. **Local Dev**: FastAPI + Vite dev server. Uses LocalStack or real AWS for S3/DynamoDB/SQS with sync queue drain fallbacks.
2. **Docker**: Backend Dockerfile (Python 3.13-slim + uv), frontend served via Vercel/nginx. Worker daemon runs concurrently in the FastAPI lifespan.
3. **Serverless**: Lambda via Mangum adapter (optional, not the default).

