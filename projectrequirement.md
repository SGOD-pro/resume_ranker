# projectrequirement.md — Resume Ranker V2
> Hard constraints and functional requirements. No fluff. Rev 4.

## 1. Functional Requirements

### 1.1 Resume Ingestion & Processing
- **FR-01** System MUST accept PDF resumes (up to 100 files per batch in preproduction and production).
- **FR-02** Processing pipeline MUST support both Local and Cloud environments:
  - **Local:** In memory worker queues and background workers process jobs deterministically.
  - **Cloud (AWS Preproduction & Production):** Consolidated single Lambda dispatcher routing API Gateway HTTP API v2 requests, SQS stage queues (Stage1Queue, Stage2Queue, ScoringQueue), Dead Letter Queues, and EventBridge scheduled recovery rules through dedicated event source mappings.
- **FR-03** Real time progress updates delivered via Server Sent Events (SSE) or responsive status polling. No WebSockets.
- **FR-03a** Transactional outbox pattern in DynamoDB ensures all stage transitions and queue dispatches are atomic. Automatic outbox recovery runs autonomously via EventBridge schedule and opportunistic status triggers without requiring an active browser tab.

### 1.2 Extraction (Tiered Routing)
- **FR-04** Lambda A (or Local BackgroundTask) MUST first try PyMuPDF (`fitz`).
- **FR-05** A Pre-Extraction Structural Quality Gate MUST run *before* regex parsing. It MUST calculate a heuristic score based on x-coordinate clustering, reading order monotonicity, char density, and table detection.
- **FR-06** If the structural quality score `< 0.90`, the system MUST fall back to `opendataloader-pdf` (JVM) to resolve multi-column layouts and extract bounding boxes.
- **FR-07** The system MUST NOT use the post-extraction composite presence score for routing fallbacks.

### 1.3 Evaluation & LLM Fallback (Lambda B)
- **FR-08** Lambda B MUST read the `StructuralParse` JSON and run V1 ported regex parsers.
- **FR-09** If regex yields `UnresolvedChunk`s, the system MUST batch them (up to 10) and invoke Amazon Nova (Bedrock) for structured fallback extraction.
- **FR-09a** Nova MUST only be triggered when at least one **critical** field is unresolved after deterministic parsing. Critical fields are: `name`, `email`, `phone`, `experience`, `skills`. Non-critical fields (`education`, `projects`, `github`, `location`) are **best-effort only** — they will remain null on regex-miss and MUST NOT independently trigger a Nova call. This is an explicit product policy: completeness for non-critical fields is not guaranteed. (See ADR-11.)
- **FR-10** LLM fallback MUST use tool-use constrained decoding (`toolConfig`), `temperature=0.0`, and MUST NEVER overwrite a field resolved by the deterministic engine.

### 1.4 Scoring & ATS
- **FR-11** BM25 IDF MUST come from a fixed reference corpus (`registries/idf.pkl`), not the candidate pool.
- **FR-12** ATS scoring MUST be 100% deterministic bounding-box math. Zero LLM calls.
- **FR-13** Frontend weight adjustments MUST NOT trigger backend re-extraction or re-scoring. Composite scores computed client-side in Zustand.

### 1.5 Data & Filtering
- **FR-14** Candidate filtering (score range, skill presence, status) MUST use DynamoDB Global Secondary Indexes (GSI1, GSI2, GSI3). Table scans with `FilterExpression` are prohibited.
- **FR-15** System MUST deduplicate resumes by SHA-256 content hash.

## 2. Non-Functional Requirements
- **NFR-01** The application MUST run locally without AWS SQS or external Lambda infrastructure, using in memory queue adapters and local execution. Calls to the external shared ODL parser and Bedrock Nova infill use live AWS endpoints when enabled.
- **NFR-02** Authoritative candidate scoring hot path MUST execute deterministically on extracted DTOs.
- **NFR-03** Every extraction stage MUST emit StageTiming and provenance metadata (pymupdf, pymupdf+ODL, pymupdf+Nova) for latency, reliability, and fallback auditability.
- **NFR-04** Measured AWS preproduction benchmark targets:
  - Clean path: 1 resume in 2.49s, 5 resumes in 3.77s, 47 resumes in 24.81s, 100 resumes in 52.14s.
  - Mixed fallback path: 1 resume in 3.13s, 5 resumes in 7.04s, 47 resumes in 29.11s, 100 resumes in 71.13s.
  - Peak observed Lambda memory MUST remain under 300 MB (measured: 288 MB of 1024 MB).
- **NFR-05** AWS Lambda execution timeout configured to 180s for preproduction and production functions. Bounded SQS concurrency caps (Stage 1: 3, Stage 2: 2, Scoring: 2) prevent downstream throttling.
- **NFR-06** Browser lifecycle state recovery: Ephemeral session identifiers stored strictly in browser sessionStorage. Resume file contents and candidate personal data MUST NEVER be written to persistent browser storage (localStorage).

## 3. Hard Constraints (Non-Negotiable)
| # | Constraint |
|---|-----------|
| HC-01 | No in-app Authentication layer. Endpoints are standalone and open (ADR-07 requires external edge reverse proxy). |
| HC-02 | No WebSockets. SSE and polling are the ONLY real time mechanisms. |
| HC-03 | PyMuPDF (fitz) is restricted to Stage 1 parsing. Forbidden in API Gateway and Scoring layers. |
| HC-04 | Consolidated Python 3.13 Lambda function dispatches API, SQS stage queues, DLQs, and EventBridge recovery. |
| HC-05 | Shared external ODL parser (odl-parser-lambda-prod) is unmodified and invoked via S3 pointer pattern. |
| HC-06 | Single table DynamoDB design with atomic transactional transitions and exponential backoff retry. |
| HC-07 | BM25 IDF is NEVER computed from the candidate pool; derived from fixed reference corpus. |
| HC-08 | LLM temperature is 0.0 with toolConfig schema enforcement. |
| HC-09 | ATS scoring MUST NOT call any LLM; 100% deterministic bounding box geometry. |
| HC-10 | Frontend candidate list state lives in Zustand with client side weight recalculation. |
