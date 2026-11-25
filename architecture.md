# architecture.md — SWYRA Sortlist Architecture Specification

> **Reviewed Baseline Commit:** `c9124c3de334c4b9024239acac4752a9bbb88d7e`  
> **Target Release:** `v2.2 — Durable Serverless Pipeline, Evidence Integrity, and Strict Relevance Scoring`  
> **Status:** Authoritative system architecture, serverless infrastructure, and data flow specification.

---

## 1. Architectural Principles

SWYRA Sortlist is architected as an **auditable, evidence-linked candidate review workspace**. It employs a standard AWS Serverless topology in production and a lightweight self-contained modular monolith in local development.

### Core Architectural Guarantees
1. **Direct Browser-to-S3 Uploads (Zero API Buffering):** The primary production upload path issues presigned S3 URLs (`POST /api/v2/jobs` or `POST /api/v2/jobs/{job_id}/upload-sessions`). Browsers stream multi-megabyte PDF files directly to S3 with bounded client concurrency (4–6 parallel PUT/POSTs). This eliminates multi-megabyte PDF body buffering in API Lambda RAM, reserving Lambda memory strictly for sub-50ms JSON execution (`create`, `complete`, `finalize`). The legacy backend upload proxy (`POST /api/v2/jobs/{job_id}/resumes`) is maintained strictly for local development and fallback compatibility.
2. **Consolidated Python Lambda Event Dispatcher:** Document processing and API routing in AWS are consolidated into a single unified Python 3.13 Lambda function (`resume-ranker-preprod` in preproduction, `resume-ranking-api` in production) using `src.lambda_handler.handler`. SQS stage queues remain strictly decoupled through separate AWS Event Source Mappings:
   - **`Stage1Queue` Mapping:** Bounded concurrency 3, batch size 10. Runs in memory PyMuPDF parsing and reading order layout analysis. Clean documents transition directly to `S2_DONE`.
   - **`Stage2Queue` Mapping:** Bounded concurrency 2, batch size 5. Runs layout repair via shared external OpenDataLoader parser (`odl-parser-lambda-prod`) and critical field infill via Bedrock Amazon Nova Micro.
   - **`ScoringQueue` Mapping:** Bounded concurrency 2, batch size 1. Runs deterministic multi-signal candidate scoring and BM25 ranking.
   - **Dead Letter Queue Mappings (`Stage1DLQ`, `Stage2DLQ`, `ScoringDLQ`):** Bounded concurrency 2. Handles poison messages, prevents retry loops, and maintains atomic barrier accounting.
   - **EventBridge Recovery Mapping:** Rate(5 minutes) scheduled event executes autonomous outbox and stranded job reconciliation without requiring an active browser tab.
3. **Partial Batch Failure Isolation:** All Lambda SQS event source mappings enforce `ReportBatchItemFailures`. Visibility timeouts strictly exceed function execution timeouts (`Stage1Queue` 360s > 180s, `Stage2Queue` 600s > 180s, `ScoringQueue` 360s > 180s). Transient errors on a single document retry only that specific `messageId`, never re-driving peer records in the microbatch.
4. **DynamoDB Transactional Outbox Pattern:** All file uploads and stage transitions atomically write an `OUTBOX#` record within a DynamoDB `TransactWriteItems` transaction. Retries implement exponential backoff with jitter on `TransactionConflict`.
5. **Standalone Engine Boundary (ADR-07):** Application endpoints contain no in-app authentication, passwords, or user accounts. Public production access requires an external edge reverse proxy, API Gateway custom authorizer, or VPC boundary.

---

## 2. Serverless Component Topology

```mermaid
flowchart TD
    subgraph Browser ["Client Browser (React 18 + Zustand)"]
        UI["Recruiter Review Workspace"]
        UploadZone["Resume Upload Zone (Presigned S3 PUT/POST)"]
    end

    subgraph Dispatcher ["Consolidated Python Lambda (resume-ranker-preprod / resume-ranking-api)"]
        Router["Unified Handler<br/>(src.lambda_handler.handler)"]
        API["FastAPI HTTP Router<br/>(/api/v2/jobs, /ats-check)"]
        W1["Stage 1 Worker<br/>(PyMuPDF Fast-Pass)"]
        W2["Stage 2 Worker<br/>(ODL & Nova Dispatch)"]
        W3["Scoring Worker<br/>(BM25 & ATS Math)"]
        W_DLQ["DLQ Consumer<br/>(Barrier Accounting)"]
        REC["Outbox Recovery<br/>(Scheduled Reconciler)"]
    end

    subgraph StorageLayer ["Persistence Tier (AWS ap-south-1)"]
        S3[("AWS S3 Bucket<br/>Raw PDFs & Extracted JSON")]
        DDB[("AWS DynamoDB<br/>ResumePlatform Single-Table")]
    end

    subgraph QueueLayer ["SQS Queue Tier (Separate ESMs)"]
        Q1["Stage1Queue<br/>(Vis: 360s, MaxConc: 3)"]
        Q2["Stage2Queue<br/>(Vis: 600s, MaxConc: 2)"]
        Q3["ScoringQueue<br/>(Vis: 360s, MaxConc: 2)"]
        DLQ["Dead Letter Queues<br/>(Vis: 300s, MaxConc: 2)"]
    end

    subgraph ExternalServices ["External AWS Services"]
        ODL["Shared ODL Parser Lambda<br/>(odl-parser-lambda-prod)"]
        NOVA["Amazon Bedrock<br/>(Nova Micro Infill)"]
        EB["Amazon EventBridge<br/>(rate 5 minutes)"]
    end

    %% Event Routing
    UploadZone -->|"1. Direct S3 Upload"| S3
    UploadZone -->|"2. Complete / Analyze"| Router
    Router -->|"HTTP Event"| API
    API -->|"Write Outbox & Metas"| DDB
    API -->|"Enqueue"| Q1

    %% SQS Event Source Mappings
    Q1 -->|"ESM Trigger"| Router
    Q2 -->|"ESM Trigger"| Router
    Q3 -->|"ESM Trigger"| Router
    DLQ -->|"ESM Trigger"| Router
    EB -->|"Scheduled Event"| Router

    Router -->|"SQS Stage 1"| W1
    Router -->|"SQS Stage 2"| W2
    Router -->|"SQS Scoring"| W3
    Router -->|"SQS DLQ"| W_DLQ
    Router -->|"Schedule"| REC

    W1 -->|"In-Memory Parse"| S3
    W1 -->|"Fallback Needed"| Q2
    W2 -->|"Invoke JVM Parser"| ODL
    W2 -->|"Critical Field Infill"| NOVA
    W2 -->|"Terminal S2_DONE"| DDB
    W3 -->|"Read JSONs & Rank"| S3
    W3 -->|"Persist Results"| DDB
    REC -->|"Scan Pending Outbox"| DDB
```

---

## 3. Measured AWS Preproduction Benchmark Results

Empirical results measured against deployed AWS preproduction (`resume-ranker-preprod`, `ap-south-1`):

| Workload Category | Batch Size | Wall-Clock Duration | Processing Rate | Estimated Compute Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Clean Path (PyMuPDF)** | 1 resume | **2.49s** | 0.40 res/s | $0.0001 |
| **Clean Path (PyMuPDF)** | 5 resumes | **3.77s** | 1.33 res/s | $0.0004 |
| **Clean Path (PyMuPDF)** | 47 resumes | **24.81s** | 1.89 res/s | $0.0017 |
| **Clean Path (PyMuPDF)** | 100 resumes | **52.14s** | 1.92 res/s | $0.0037 |
| **Mixed Fallback (ODL+Nova)** | 1 resume | **3.13s** | 0.32 res/s | $0.0002 |
| **Mixed Fallback (ODL+Nova)** | 5 resumes | **7.04s** | 0.71 res/s | $0.0007 |
| **Mixed Fallback (ODL+Nova)** | 47 resumes | **29.11s** | 1.61 res/s | $0.0022 |
| **Mixed Fallback (ODL+Nova)** | 100 resumes | **71.13s** | 1.41 res/s | $0.0047 |

- **Peak Observed Lambda Memory:** 288 MB of 1024 MB (28.1% of ceiling).
- **Lambda Invocations & Throttles:** 0 throttles, 0 execution timeouts, 0 DLQ deliveries.
- **Resource Cleanup:** 100% ephemeral S3 staging objects purged post extraction.

---

## 3. Core Lifecycle & Recovery Path Diagrams

### Lifecycle 1: Analyze Before, During, and After Stage 1

```mermaid
sequenceDiagram
    participant UI as Browser UI
    participant API as ApiGatewayFunction
    participant DDB as DynamoDB (Job & Files)
    participant S1 as Stage1WorkerFunction
    participant S2 as Stage2WorkerFunction
    participant SC as ScoringWorkerFunction

    Note over UI,API: BEFORE STAGE 1 (Upload & Job Setup)
    UI->>API: POST /jobs/{job_id}/upload-sessions
    API->>DDB: Create JobItem (total_files=N, remaining=N, analyze_requested=false)
    UI->>API: POST /jobs/{job_id}/upload-sessions/{id}/finalize
    API->>DDB: Set JobStatus: READY_TO_ANALYZE

    Note over UI,S1: USER CLICKS "ANALYZE"
    UI->>API: POST /jobs/{job_id}/analyze
    API->>DDB: Set analyze_requested = true
    API->>S1: Trigger Stage1Queue

    Note over S1,S2: DURING STAGE 1 (Fast-Path PyMuPDF)
    S1->>S1: In-memory text & reading order extraction
    alt Clean Layout (Quality >= 0.90)
        S1->>DDB: Update File: S2_DONE (remaining -= 1)
    else Fallback Required (ODL or Nova)
        S1->>DDB: Update File: S1_DONE
        S1->>S2: Enqueue Stage2Queue (since analyze_requested=true)
    end

    Note over S2,SC: AFTER STAGE 1 (Tail Processing & Scoring)
    opt Stage 2 Processing
        S2->>S2: Execute ODL layout repair / Bedrock Nova infill
        S2->>DDB: Update File: S2_DONE (remaining -= 1)
    end
    Note over DDB,SC: Barrier Check: When remaining == 0
    DDB->>SC: Enqueue ScoringQueue
    SC->>DDB: Set JobStatus: SCORED
    SC-->>UI: Results ready for recruiter review
```

---

### Lifecycle 2: Partial Browser Uploads & Barrier Reconciliation

```mermaid
sequenceDiagram
    participant Browser as Browser Uploader
    participant S3 as AWS S3 Storage
    participant API as API Lambda
    participant DDB as DynamoDB

    Browser->>API: POST /jobs/{job_id}/upload-sessions (Request N files)
    API->>DDB: Create session with expected_count = N
    API-->>Browser: Return N presigned S3 URLs

    Note over Browser,S3: Partial Upload Occurs (K of N succeed)
    par Successful Uploads (K files)
        Browser->>S3: PUT file_1.pdf (200 OK)
        Browser->>API: POST /complete (file_1)
        API->>DDB: Set file_1 status: UPLOADED
    and Aborted / Failed Uploads (N - K files)
        Browser-xS3: Network drop / file too large / user cancels
    end

    Note over Browser,DDB: Finalize Barrier Reconciliation
    Browser->>API: POST /upload-sessions/{id}/finalize (uploaded_count = K)
    API->>DDB: Mark (N - K) uncompleted files as REMOVED / FAILED
    API->>DDB: Reconcile Job: total_files = K, remaining = K
    API->>DDB: Delete ACTIVE_SESSION# pointer
    API-->>Browser: Session finalized (usable_files = K, barrier sealed)
```

---

### Lifecycle 3: SQS Worker Fallback Tail & Batch Item Failure Isolation

```mermaid
flowchart LR
    subgraph Ingestion ["Stage 1 PyMuPDF Ingestion"]
        S1_Batch["SQS Microbatch (10 records)"]
        S1_Proc["Stage1WorkerFunction"]
    end

    subgraph FastPath ["Fast-Path (80-90%)"]
        Clean["Clean Single-Column Layouts"]
        S2_Done["Status: S2_DONE<br/>(Atomic Barrier Decrement)"]
    end

    subgraph FallbackTail ["Fallback Tail (10-20%)"]
        S2_Queue["Stage2Queue"]
        S2_Proc["Stage2WorkerFunction<br/>(ReportBatchItemFailures)"]
        ODL["ODL JVM<br/>(Multi-Column Repair)"]
        Nova["Nova LLM<br/>(Targeted Infill)"]
    end

    S1_Batch --> S1_Proc
    S1_Proc -->|"Quality >= 0.90"| Clean --> S2_Done
    S1_Proc -->|"needs_odl or needs_nova"| S2_Queue

    S2_Queue --> S2_Proc
    S2_Proc -->|"needs_odl"| ODL
    S2_Proc -->|"needs_nova"| Nova
    ODL & Nova --> S2_Done
    S2_Proc -.->|"Transient 429 Throttling"| Retry["Return batchItemFailures<br/>(Retry Failed MessageId Only)"]
```

---

### Lifecycle 4: Expired Worker Lease & DLQ Recovery

```mermaid
sequenceDiagram
    participant SQS as SQS Stage Queue
    participant W as Worker Lambda
    participant DLQ as Dead Letter Queue
    participant DDB as DynamoDB
    participant R as DlqConsumerFunction / Recovery Lambda

    Note over SQS,W: Visibility Timeout Exceeds Function Timeout
    SQS->>W: Deliver Message (ReceiveCount = 1, VisTimeout = 180s)
    W->>W: Process starts (Lambda timeout = 120s)
    Note over W: Worker times out or OOMs at 120s
    Note over SQS: VisTimeout expires at 180s (Message becomes visible again)
    
    SQS->>W: Redrive Message (ReceiveCount = 2)
    Note over W: Worker crashes again
    SQS->>W: Redrive Message (ReceiveCount = 3)
    Note over W: Final attempt fails

    Note over SQS,DLQ: Poison Pill Routed to DLQ
    SQS->>DLQ: Route to DLQ (maxReceiveCount = 3 exceeded)
    DLQ->>R: Trigger DlqConsumerFunction
    R->>DDB: Mark FileStatus: S1_FAILED or S2_FAILED
    R->>DDB: Atomic Decrement Job Barrier (remaining -= 1)
    R->>SQS: Delete DLQ Message (Self-Heals Barrier Deadlock)
```

---

### Lifecycle 5: Selected-Cohort Publication & Explainable Scoring

```mermaid
flowchart TD
    subgraph Trigger ["Scoring Trigger"]
        Barrier["DynamoDB Barrier: remaining == 0"]
        ScoringQ["ScoringQueue"]
    end

    subgraph Scorer ["Deterministic CandidateScorer"]
        Load["Load S3 Extracted JSONs for Job"]
        BM25["BM25 Skill Matching<br/>(Cohort IDF Matrix)"]
        Exp["TF-IDF Role Cosine +<br/>Experience Duration Math"]
        KW["Keyword & Education Matching"]
        Knockout["Knockout Rule Evaluation<br/>(Preserves Explainable Sub-Scores)"]
        Ledger["Factor Ledger Generation<br/>(Transparent Provenance)"]
    end

    subgraph Publication ["Results Publication"]
        S3_Results[("S3: jobs/{job_id}/results/scoring_{id}.json")]
        DDB_Job[("DynamoDB: JobStatus = SCORED")]
        UI["Recruiter UI:<br/>Instant Client-Side Weight Recalculation"]
    end

    Barrier --> ScoringQ --> Load
    Load --> BM25 & Exp & KW
    BM25 & Exp & KW --> Knockout --> Ledger
    Ledger --> S3_Results & DDB_Job
    S3_Results -.-> UI
```

---

## 4. Key Architectural Clarifications

### A. Base-Table Key-Prefix Session Queries
- Active upload session verification queries DynamoDB using `PK=ORG#{org_id}` and `SK begins_with('ACTIVE_SESSION#')`.
- **Reality:** This is **not an $O(1)$ constant query, not a Global Secondary Index (GSI), and does not guarantee 1 RCU**.
- **Scalability:** It scans and reads all matching session pointers in the organization partition. To ensure predictable costs, active pointers are strictly deleted when sessions transition to `READY_TO_ANALYZE` or reach terminal states (`EXPIRED`, `FAILED`). Stale pointers are reconciled during admission.

### B. Direct S3 Upload Memory Reality
- **Client Direct Uploads:** Resumes are uploaded directly from the client browser to AWS S3 using presigned URLs.
- **Lambda Memory Reality:** Direct S3 uploads eliminate buffering multi-megabyte PDF bodies through the API Lambda memory. However, the API Lambda still consumes minimal memory for JSON requests (`create-upload-session`, `complete`, `finalize`). Memory size is set to 512 MB to support fast JSON serialization and low-latency crypto token generation.

### C. Concurrency: 6 Local Workers vs. AWS Lambda
- **Local Microbenchmark:** Spawns a maximum of 6 isolated operating system processes (`ProcessPoolExecutor`). PyMuPDF executes strictly single-threaded within each process to prevent C-library memory corruption.
- **AWS Lambda Scaling:** Lambda concurrency is **independent of local process limits**. In AWS Lambda, each invocation runs in its own isolated Firecracker microVM. Lambda scaling is governed by SQS trigger batch sizes (up to 10 records) and AWS account concurrency quotas. Six local processes does not mean six Lambda invocations.

---

## 5. Browser Lifecycle & State Recovery

- **Ephemeral Storage Scoping:** The active `job_id` is tracked exclusively in browser `sessionStorage`. Closing the tab or opening a new browser session starts cleanly with a blank state (`No Results Yet`).
- **Zero LocalStorage PII:** Resume contents, extracted text, contact details, and candidate evaluations are NEVER stored in persistent browser storage (`localStorage`).
- **In Flight Recovery:** A page reload or network reconnect during upload, extraction, or scoring queries `GET /api/v2/jobs/{job_id}/status`, seamlessly reattaching to the active DynamoDB processing state without duplicate job creation.

---

## 6. Environment Isolation & Deployment Boundaries

- **Preproduction Environment (`resume-ranker-preprod`):**
  - Dedicated DynamoDB single table (`ResumePlatformPreprod-445567096027`).
  - Dedicated S3 storage bucket (`resume-ranker-preprod-445567096027`).
  - Dedicated SQS stage and dead-letter queues (`resume-ranker-stage1-preprod`, etc.).
  - Isolated from production queues, tables, and production resume documents.
- **Shared ODL Service:**
  - Shared external parser `odl-parser-lambda-prod` is invoked using an isolated staging prefix (`pdf-test-bucket-09/preprod-staging/`), ensuring zero cross-environment contamination.
- **Edge Reverse Proxy Requirement (ADR-07):**
  - The application backend operates as an unauthenticated standalone engine.
  - Production deployments MUST enforce reverse proxy protection (CloudFront, API Gateway custom authorizer, or VPC endpoint) to prevent unauthorized public access.

---

## 7. Production Migration & Rollback Procedures

### Updating Production Lambda (`resume-ranking-api`)
```bash
# 1. Build and package consolidated artifact
sam build -t infra/template.yaml

# 2. Deploy updated code to existing production function
aws lambda update-function-code \
  --function-name resume-ranking-api \
  --s3-bucket resume-ranker-prod-storage \
  --s3-key deployments/v2.1-release.zip \
  --region ap-south-1 \
  --profile aws

# 3. Execute smoke verification
curl -s https://<prod-api-id>.execute-api.ap-south-1.amazonaws.com/health | jq .
```

### Rollback Procedure
```bash
# Instant rollback to previous verified Lambda CodeSha256
aws lambda update-function-code \
  --function-name resume-ranking-api \
  --s3-bucket resume-ranker-prod-storage \
  --s3-key deployments/v2.0-previous.zip \
  --region ap-south-1 \
  --profile aws
```


---

## 8. Architecture Diagrams

### High-Level System Architecture
```mermaid
flowchart LR
    FE["React Frontend"] --> APIGW["API Gateway HTTP API v2"]
    APIGW --> LAMBDA["Consolidated Python Lambda"]
    LAMBDA --> DDB["DynamoDB (Single Table + Outbox)"]
    LAMBDA --> S3["Amazon S3 (PDFs & Extracted JSON)"]
    LAMBDA --> SQS["Amazon SQS (Stage 1 / 2 / Scoring + DLQs)"]
    SQS --> LAMBDA
    LAMBDA -.->|"Slow Path"| ODL["odl-parser-lambda-prod (JVM)"]
    LAMBDA -.->|"Field Recovery"| NOVA["Amazon Bedrock Nova"]
```

### Consolidated Lambda Event Dispatcher
```mermaid
flowchart TD
    HTTP["API Gateway HTTP API v2"] --> LAMBDA["src.lambda_handler.handler"]
    Q1["SQS Stage 1 / 2 / Scoring / DLQs"] --> LAMBDA
    EB["EventBridge Schedule (reconcile_outbox)"] --> LAMBDA
    LAMBDA --> H_API["src.handlers.api"]
    LAMBDA --> H_WRK["src.handlers.stage1 / stage2 / scoring / dlq"]
    LAMBDA --> H_REC["src.handlers.recovery"]
```

### Minimum EventBridge IAM Policy Required for `EnableSchedule=true`
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutRule",
        "events:DescribeRule",
        "events:DeleteRule",
        "events:PutTargets",
        "events:RemoveTargets"
      ],
      "Resource": "arn:aws:events:ap-south-1:445567096027:rule/resume-ranker-recovery-*"
    }
  ]
}
```
