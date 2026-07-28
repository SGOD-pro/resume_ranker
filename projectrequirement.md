# projectrequirement.md — Resume Ranker V2
> Hard constraints and functional requirements. No fluff. Rev 4.

## 1. Functional Requirements

### 1.1 Resume Ingestion & Processing
- **FR-01** System MUST accept PDF resumes (up to 50 files per job).
- **FR-02** Processing pipeline MUST support both Local and Prod environments:
  - **Local:** FastAPI `BackgroundTasks` executes the parsing pipeline.
  - **Prod:** S3 Upload → SQS (`DocumentQueue`) → Lambda A → SQS (`ExtractQueue`) → Lambda B.
- **FR-03** Real-time progress MUST be delivered via SSE (Server-Sent Events). No WebSockets.

### 1.2 Extraction (Tiered Routing)
- **FR-04** Lambda A (or Local BackgroundTask) MUST first try PyMuPDF (`fitz`).
- **FR-05** A Pre-Extraction Structural Quality Gate MUST run *before* regex parsing. It MUST calculate a heuristic score based on x-coordinate clustering, reading order monotonicity, char density, and table detection.
- **FR-06** If the structural quality score `< 0.90`, the system MUST fall back to `opendataloader-pdf` (JVM) to resolve multi-column layouts and extract bounding boxes.
- **FR-07** The system MUST NOT use the post-extraction composite presence score for routing fallbacks.

### 1.3 Evaluation & LLM Fallback (Lambda B)
- **FR-08** Lambda B MUST read the `StructuralParse` JSON and run V1 ported regex parsers.
- **FR-09** If regex yields `UnresolvedChunk`s, the system MUST batch them (up to 10) and invoke Amazon Nova (Bedrock) for structured fallback extraction.
- **FR-10** LLM fallback MUST use tool-use constrained decoding (`toolConfig`), `temperature=0.0`, and MUST NEVER overwrite a field resolved by the deterministic engine.

### 1.4 Scoring & ATS
- **FR-11** BM25 IDF MUST come from a fixed reference corpus (`registries/idf.pkl`), not the candidate pool.
- **FR-12** ATS scoring MUST be 100% deterministic bounding-box math. Zero LLM calls.
- **FR-13** Frontend weight adjustments MUST NOT trigger backend re-extraction or re-scoring. Composite scores computed client-side in Zustand.

### 1.5 Data & Filtering
- **FR-14** Candidate filtering (score range, skill presence, status) MUST use DynamoDB Global Secondary Indexes (GSI1, GSI2, GSI3). Table scans with `FilterExpression` are prohibited.
- **FR-15** System MUST deduplicate resumes by SHA-256 content hash.

## 2. Non-Functional Requirements
- **NFR-01** The application MUST run locally without AWS SQS or Lambda networking.
- **NFR-02** Evaluation hot path (Scoring + ATS) MUST execute in < 50ms on pre-computed DTOs.
- **NFR-03** Every extraction stage MUST emit a `StageTiming` record for latency and fallback-rate instrumentation.
- **NFR-04** AWS Lambda SSE stream MUST use Function URLs with `RESPONSE_STREAM` or API Gateway HTTP API to bypass the 29-second REST timeout.
- **NFR-05** AWS Lambda execution time for both Lambda A (Parsing) and Lambda B (Extraction/Scoring) MUST stay strictly under the 15-minute maximum timeout. Long-running batches MUST be chunked or handled via SQS batch windowing to prevent Lambda truncation.

## 3. Hard Constraints (Non-Negotiable)
| # | Constraint |
|---|-----------|
| HC-01 | No Authentication layer. Endpoints are open. |
| HC-02 | No WebSockets. SSE is the ONLY real-time mechanism. |
| HC-03 | `fitz` (PyMuPDF) and `opendataloader_pdf` are ALLOWED ONLY in the Parsing Module. Forbidden in API/Scoring. |
| HC-04 | Lambda A MUST be a Docker container image (JVM + ODL > 250MB). |
| HC-05 | Lambda B MUST be a ZIP package (FastAPI + Python). |
| HC-06 | No Postgres. DynamoDB strictly used with purpose-built GSIs. |
| HC-07 | BM25 IDF is NEVER computed from the candidate pool. |
| HC-08 | LLM temperature is 0.0. Always. |
| HC-09 | ATS scoring MUST NOT call any LLM. |
| HC-10 | Frontend candidate list state lives in Zustand. TanStack Query is for GETs only. |
