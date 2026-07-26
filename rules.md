# rules.md — Resume Ranker V2
> Engineering rules and CI enforcements.

## 1. Architecture Rules
- **R-01:** Lambda A is packaged via Docker. Lambda B is packaged via ZIP.
- **R-02:** No WebSockets. SSE is the only real-time communication mechanism.
- **R-03:** BM25 IDF is NEVER computed from the candidate pool.
- **R-04:** ATS scoring NEVER imports from Extraction or Scoring contexts.
- **R-05:** LLM temperature is 0.0. Always.

## 2. Resiliency Rules
- **R-06 (Idempotency):** Lambda handlers MUST check DynamoDB `status` before processing. If `status == 'SCORED'`, return immediately.
- **R-07 (Caching):** Upload endpoint MUST hash the PDF. If `content_hash` exists in DynamoDB, return cached `candidate_id` without re-processing.

## 3. Frontend Rules
- **R-08:** Candidate list state lives in Zustand. TanStack Query is for GET requests only.
- **R-09:** Weight slider changes MUST NOT trigger API calls. Compute composite score in Zustand selector.

## 4. E2E Testing Rules
- **R-10:** The E2E test suite (`e2e-api-test.ts`) is a hard gate. No V2 feature is complete until the JULIE MONROE knockout and Backend Python ranking assertions pass.
