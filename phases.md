# phases.md — Resume Ranker V2
> Strict implementation milestones. No phase begins until the prior is verified.

## Phase 1: Deep Context Absorption & V1 Restore (Days 1-3)
**Goal:** Revert to V1 working state on `/api/v2/` routes.
- Delete WebSocket code (`ws.py`, `sqs_handler.py`).
- Fix `jobs_v2.py` to return scored data from S3, not raw DynamoDB metadata.
- Fix frontend `CandidateListPanel` to read from Zustand.
- **Gate:** Full V1 flow works end-to-end on `/api/v2/`.

## Phase 2: Network Contract & 2-Lambda Infra (Days 4-6)
**Goal:** Set up SQS, DLQs, and Lambda A Docker image.
- Create `Dockerfile` for Lambda A.
- Implement SQS queues with DLQs.
- Implement Lambda A: Read SQS -> Download S3 -> PyMuPDF -> Quality Check -> ODL -> Save JSON -> Push SQS.
- **Gate:** Upload PDF -> Lambda A processes -> JSON appears in S3.

## Phase 3: V2 Evaluation Wiring (Days 7-10)
**Goal:** Wire V2 modules into Lambda B.
- Implement SQS consumer in Lambda B. Add idempotency check.
- Run Deterministic Extraction -> Batched Nova LLM Fallback.
- Implement SSE endpoint on Lambda B.
- **Gate:** Upload PDF -> Lambda A parses -> Lambda B extracts -> SSE updates frontend.

## Phase 4: Scoring, ATS & Full E2E Verification (Days 11-14)
**Goal:** Run V1 Scoring + V2 ATS, and verify the entire system using the E2E test suite.
- Run `ScoringService` (Fixed IDF) & `AtsScoringService` (Bbox math).
- Frontend: PDF viewer with bbox overlays.
- **Gate:** Run `e2e-api-test.ts`. 
  - All V1 scoring assertions MUST pass (JULIE MONROE knocked out, top candidate matches Python).
  - API response MUST include `ats_score` and `bounding_boxes`.