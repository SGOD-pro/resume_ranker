# boundaries.md — Resume Ranker V2
> Strict system boundaries, service limits, and anti-corruption layers.

## 1. Execution & Module Boundaries (Strict)

The system is decoupled into a Parsing Module (Lambda A / Local BackgroundTask) and an API/Evaluation Module (Lambda B / FastAPI). These boundaries are absolute and enforced by CI.

- **Parsing Module (Lambda A / BackgroundTask):**
  - **Allowed:** `fitz` (PyMuPDF), `boto3` (S3/SQS/Lambda).
  - **Forbidden:** `src.api`, `src.scoring`, `src.ats`. It MUST NOT know what a "Job" or a "Score" is. It only transforms PDF bytes into `StructuralParse` JSON.
- **API/Evaluation Module (Lambda B / FastAPI):**
  - **Allowed:** `fastapi`, `boto3` (S3/DynamoDB/Bedrock), `scikit-learn`, `rank_bm25`.
  - **Forbidden:** `fitz`. It MUST NOT parse raw PDFs. It only reads the `StructuralParse` JSON from S3.

**Why?** Lambda B is a ZIP package. If it imports JVM or heavy PDF libraries, the deployment package will exceed 250MB and fail. Furthermore, mixing parsing and scoring logic creates God-classes that are impossible to test.

## 2. Anti-Corruption Layers (ACLs)

To ensure no vendor SDK logic leaks into domain math, external dependencies are wrapped in single classes. Nothing else in the codebase imports the vendor SDK.

| Dependency | Allowed ONLY In | Purpose |
|---|---|---|
| `fitz` (PyMuPDF) | `src/extraction/structural_parsing_service.py` | Fast-path text extraction and layout quality scoring. |
| `boto3` (Lambda) | `src/extraction/structural_parsing_service.py` | Invokes the external `odl-parser-lambda` for slow-path parsing. Direct HTTP or SDK imports of `opendataloader_pdf` are prohibited. |
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
