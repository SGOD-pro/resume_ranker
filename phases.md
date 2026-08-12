1# phases.md — Resume Ranker V2
> Strict implementation milestones. No phase begins until the prior is verified. Rev 4 (Fresh Build from V1).

## Phase 1: V2 Route Foundation & V1 Migration (Days 1–3)
**Goal:** Create the `/api/v2/` route prefix and migrate the exact V1 synchronous flow to it. No async, no SQS, no new extraction logic yet. Just ensure the app works exactly as it does in V1, but on V2 routes.
- Read `mamori.md` to understand the V1 synchronous flow.
- Create `jobs_v2.py`. Mirror V1 endpoints under `/api/v2/` (POST /jobs, POST /resumes, GET /extract, POST /score).
- Frontend API client (`api.ts`) points to `/api/v2/` endpoints.
- Ensure `CandidateListPanel` and `CandidateDetailPanel` read from Zustand as they did in V1.
- **Gate:** Full V1 flow works end-to-end on `/api/v2/` locally. The E2E test suite passes (JULIE MONROE knocked out, Python ranks #1 for Backend).

## Phase 2: Local Async Decoupling (Days 4–6)
**Goal:** Decouple the V1 synchronous extraction into a FastAPI `BackgroundTask` locally to stop blocking the API thread and fix the infinite spinner issue.
- In `POST /api/v2/jobs/{id}/resumes`, if `ENVIRONMENT == 'local'`, schedule the extraction function via `BackgroundTasks` instead of running it synchronously.
- Update DynamoDB state transitions (`PENDING` -> `PARSING` -> `PARSED` -> `SCORED`) inside the BackgroundTask.
- Refactor `GET /api/v2/jobs/{id}/extract` SSE endpoint to poll DynamoDB every 2 seconds and emit events based on state transitions.
- **Gate:** Upload PDF -> API returns 202 immediately -> Background task updates DB -> SSE pushes progress to frontend -> Spinner stops on completion. No infinite loading. Killing the Lambda B process mid-stream (simulated locally by raising an exception mid-poll-loop) and re-opening the EventSource resumes progress display without duplicate processing or lost documents.

## Phase 3: Tiered Extraction & V2 Scoring Engine (Days 7–10)
**Goal:** Replace V1 PyMuPDF with the Tiered Extraction pipeline and wire V2 Scoring/ATS modules.
- Inside the `BackgroundTask`, implement the pre-extraction structural quality gate (x-coordinate clustering, reading order).
- If structural quality < 0.90, run `opendataloader-pdf` (JVM). Save `StructuralParse` JSON (Markdown + bbox).
- Run V1 ported regex parsers on the clean Markdown. Collect `UnresolvedChunk`s.
- Batch unresolved chunks and call Amazon Bedrock (Nova Micro) with `temperature=0` and `toolConfig`.
- Run V2 `ScoringService` (Fixed IDF) & `AtsScoringService` (100% bbox math) in parallel.
- Emit `StageTiming` records for instrumentation.
- **Gate:** Upload 2-column PDF -> ODL triggers -> Score response includes `ats_score` and `bounding_boxes`. DynamoDB status transitions to `SCORED`.

## Phase 4: 2-Lambda Production Infrastructure (Days 11–14)
**Goal:** Containerize Lambda A and wire SQS for production deployment.
- Create `Dockerfile.lambda_a` (Python 3.12 + JRE 17 + ODL + PyMuPDF).
- Implement `ENVIRONMENT == 'production'` logic: Push to SQS `DocumentQueue` instead of `BackgroundTasks`.
- Define SQS queues, DLQs, and Lambda event mappings in `template.yaml`. Include `OdlBatchQueue` event source mapping (`BatchSize=10, MaximumBatchingWindowInSeconds=60`).
- Wire quality-gate-failed documents to `OdlBatchQueue` (send_message) instead of direct `parse()` invocation — per R-21.
- Configure API Gateway HTTP API or Lambda Function URL with `RESPONSE_STREAM` for the SSE endpoint.
- **Gate:** `sam build` succeeds. Deployment to AWS works without local code changes. Production SSE stream does not hit 29-second timeout. ODL Lambda timeout budget and Reserved Concurrency value are set from Phase 3 measured data, not estimated (ADR-09). **ODL batch deliverable gate: CloudWatch logs confirm exactly ONE `odl-parser-lambda` invocation per batch window flush (not N invocations for N quality-failed docs). Verify with a 15-resume upload where ~8 fail the quality gate.**

## Phase 5: Frontend V2 Features & Polish (Days 15–17)
**Goal:** Build V2 UI features (ATS overlays, standalone checker, client-side weight recompute).
- Implement PDF viewer with bounding box overlays (Red = severe, Yellow = warning).
- Add standalone `/ats-checker` page (unauthenticated, calls `POST /api/v2/ats-check`).
- Implement weight sliders with Zustand derived selector for < 50ms client-side recompute.
- Implement DynamoDB GSI queries for score-range and skill-presence filtering on the candidate list.
- **Gate:** Full E2E manual test passes. Weight slider adjustments instantly re-sort the list with zero network requests. ATS bounding boxes render precisely over the PDF.