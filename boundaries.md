# boundaries.md — Resume Ranker V2
> Strict system boundaries, service limits, and anti-corruption layers.

## 1. Execution & Module Boundaries (Strict)

The system deploys a single consolidated Python Lambda dispatcher in preproduction (`resume-ranker-preprod`) and production (`resume-ranking-api`), while isolating heavy JVM execution in the shared external parser (`odl-parser-lambda-prod`). Module boundaries inside the Python codebase are absolute:

- **Stage 1 Fast Parse Worker:**
  - **Allowed:** `fitz` (PyMuPDF), in memory layout parsing, reading order analysis, and S3 raw key download.
  - **Forbidden:** `src.ats`, `src.ranking`, `odl_client`. It MUST NOT score resumes or invoke external parsers. It converts raw PDF bytes into Stage 1 JSON and updates file status.
- **Stage 2 Fallback Worker:**
  - **Allowed:** `odl_client` (invoking `odl-parser-lambda-prod` via S3 pointer pattern), `nova_service` (Bedrock Amazon Nova Micro infill).
  - **Forbidden:** Raw PDF geometry rendering, job scoring, or direct database mutations outside file status and outbox.
- **Scoring & Evaluation Worker:**
  - **Allowed:** BM25 scoring with fixed reference corpus, TF-IDF role matching, deterministic ATS geometry scoring, candidate decision persistence.
  - **Forbidden:** `fitz`, Bedrock, or JVM imports. It strictly consumes standardized extraction JSON payloads from S3.
- **External Network Boundary (ADR-07):**
  - Application endpoints are open and standalone (no user logins, passwords, or JWT validation).
  - Production deployments MUST sit behind an external reverse proxy (CloudFront, API Gateway authorizer, or VPC boundary) to prevent unauthorized public access.

**Why?** Consolidating the Python workers into a single Lambda function with separate SQS event source mappings simplifies deployment and keeps memory under 288 MB, while keeping the heavy JVM runtime strictly isolated in the shared ODL container.

## 2. Anti-Corruption Layers (ACLs)

To ensure no vendor SDK logic leaks into domain math, external dependencies are wrapped in single classes. Nothing else in the codebase imports the vendor SDK.

| Dependency | Allowed ONLY In | Purpose |
|---|---|---|
| `fitz` (PyMuPDF) | `src/extraction/structural_parsing_service.py` | Fast-path text extraction and layout quality scoring. |
| `boto3` (Lambda) | `src/extraction/structural_parsing_service.py` | Invokes the external `odl-parser-lambda` for slow-path parsing. Direct HTTP or SDK imports of `opendataloader_pdf` are prohibited. |
| ODL Failure Handling | `src/extraction/structural_parsing_service.py` | Centralizes try/except blocks and fallback routing for odl-parser-lambda, preventing scattered error handling (ADR-09). |
| `boto3` (Bedrock) | `src/extraction/fallback/nova_service.py` | Isolates LLM API from extraction logic. |
| `boto3` (S3/DynamoDB) | `src/infrastructure/` | Isolates AWS SDK from repositories. |

## 3. Database & State Boundaries

- **DynamoDB:** Stores Job metadata, weights, and processing state (`PENDING`, `PARSED`, `SCORED`). It also stores candidate metadata for list querying.
  - **Strict Rule:** Multi-attribute filtering (score range, skill presence) MUST use the GSIs defined in `design.md`. `scan()` with `FilterExpression` on the base table is strictly prohibited.
- **S3:** Stores raw PDFs, `StructuralParse` JSON, and `ScoringResult` JSON. Large payloads are never passed through SQS; SQS messages only contain pointers (IDs and S3 Keys).

## 4. Real-Time Communication Boundary

- **SSE Only:** Server-Sent Events (SSE) via FastAPI `StreamingResponse` is the ONLY real-time mechanism. 
- **Forbidden:** WebSockets (`ws://`, `websocket`, `websockets` library). Lambda is stateless; WebSockets require connection mapping which adds unnecessary complexity and failure points.

## 5. Frontend State Boundary

- **Zustand is the Source of Truth:** The candidate list state lives in Zustand (`candidate-store.ts`). 
- **TanStack Query:** Used ONLY for fetching static config or initial job data. It MUST NOT be used to poll for the candidate list. The candidate list is populated by the `POST /score` response and pushed into Zustand.
- **Weight Recompute:** Weight adjustments MUST NOT trigger backend API calls. The composite score is computed locally in a Zustand derived selector. To persist weights, a lightweight `PATCH /api/v2/jobs/{id}/weights` is called, but it does NOT re-trigger scoring.

## 6. Extraction Routing Boundary

- The PyMuPDF vs ODL routing decision MUST be based on a *pre-extraction structural heuristic* (x-coordinate clustering, reading order, char density). 
- It MUST NOT use the post-extraction composite presence score (e.g., "did we find a name?"). A garbled layout can still produce non-empty but incorrect fields, which would falsely pass a presence check and bypass the ODL fallback.
```
