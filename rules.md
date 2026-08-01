
# rules.md — Resume Ranker V2
> Engineering rules, coding standards, and linting/CI enforcements.

## 1. Architecture Rules
- **R-01 (Local-Cloud Split):** S3 and DynamoDB point to LocalStack. Bedrock calls hit real AWS. ODL parser uses Local Bypass: imports odl/main.py directly instead of invoking the cloud Lambda.
- **R-02 (No WebSockets):** SSE is the only real-time communication mechanism. Importing `websocket` or `ws` is a CI failure.
- **R-03 (Module Isolation):** `fitz` (PyMuPDF) MUST NOT be imported outside the Parsing Module (`src/extraction/structural_parsing_service.py`). The API/Scoring Module MUST NOT parse raw PDFs.
- **R-04 (No Table Scans):** Multi-attribute filtering on DynamoDB (score range, skill presence) MUST use the GSIs defined in `design.md`. `scan()` with `FilterExpression` is strictly prohibited for candidate queries.
- **R-05 (S3 Pointer Pattern):** SQS messages MUST only contain `document_id` and S3 keys. Never pass 50MB JSON payloads through SQS.
- **R-20 (Uniform ODL Error Handling):** `odl_client.py`'s `parse()` and `parse_batch()` functions MUST catch exceptions from BOTH the local-bypass and boto3.invoke paths inside themselves and return a uniform result type (success payload OR a typed ODLParseError). Callers never see raw ImportError, boto3 ClientError, or subprocess errors directly — only ODLParseError.
- **R-21 (ODL Batch Routing):** ODL calls for quality-gate-failed documents in the batch pipeline MUST use `odl_client.parse_batch()`. Direct per-document `odl_client.parse()` calls from the batch pipeline are prohibited. Exception: the standalone `/api/v2/ats-check` endpoint processes one PDF synchronously and MUST use `parse()` directly — batching would add up to `MaximumBatchingWindowInSeconds` latency to a live user-facing check.

## 2. Extraction & LLM Rules
- **R-06 (Pre-Extraction Quality Gate):** The PyMuPDF vs ODL routing decision MUST be based on a pre-extraction structural heuristic (x-coordinate clustering, reading order monotonicity, char density). It MUST NOT use the post-extraction composite presence score.
- **R-07 (LLM is Field-Level Infill):** The LLM fallback (Amazon Nova) is NOT a document parser. It is used to fill specific `UnresolvedChunk`s that the regex engine failed to parse.
- **R-08 (LLM Constraints):** Bedrock Converse API calls MUST use `temperature: 0.0` and `toolConfig` for strict JSON schema enforcement. LLM MUST NEVER overwrite a field resolved by the deterministic engine.
- **R-09 (Instrumentation):** Every extraction stage MUST emit a `StageTiming` record (duration, method, triggered_fallback) to S3. This is mandatory for tracking ODL/Nova fallback rates.

## 3. Scoring Rules
- **R-10 (Fixed IDF):** BM25 IDF is NEVER computed from the candidate pool. It MUST come from the fixed reference corpus (`registries/idf.pkl`).
- **R-11 (Synchronous Invocation):** The `boto3 lambda.invoke` call for ODL MUST use `InvocationType='RequestResponse'` and handle the response payload explicitly. MUST wrap the invoke() call in a try/except per ADR-09's degraded-path behavior. Bare/unhandled exceptions on this call are a CI-blocking code review failure.
- **R-12 (Deterministic ATS):** ATS scoring MUST be 100% deterministic bounding-box math. Zero LLM calls. ATS MUST NOT import from Extraction or Scoring contexts.
- **R-13 (Immutable Component Scores):** Component scores (skill, experience, education) are computed once and persisted. Composite scores are computed at read time.

## 4. Resiliency Rules
- **R-14 (Idempotency):** Lambda handlers and BackgroundTasks MUST check DynamoDB `status` before processing. If `status == 'SCORED'`, return immediately.
- **R-15 (Caching):** Upload endpoint MUST hash the PDF. If `content_hash` exists in DynamoDB, return cached `candidate_id` without re-processing.

## 5. Frontend Rules
- **R-16 (Zustand is Source of Truth):** Candidate list state lives in Zustand. TanStack Query is for GET requests only. Never replace Zustand state with TanStack Query polling.
- **R-17 (Client-Side Recompute):** Weight slider changes MUST NOT trigger API calls. Compute composite score in a Zustand derived selector (< 50ms). To persist, use `PATCH /api/v2/jobs/{id}/weights`, which does NOT re-trigger scoring.

## 6. CI/CD Enforcements
- **R-18 (Import Restrictions):** CI will run a script (`scripts/check_imports.py`) to verify `fitz` and `opendataloader_pdf` do not appear outside `structural_parsing_service.py`.
- **R-19 (Phase Gating):** PRs MUST map to an active phase in `phases.md`. A PR cannot merge if it breaks a previous phase's verification gate.
