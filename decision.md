# decision.md — Resume Ranker V2
> Architecture Decision Records (ADRs). Rev 4.

## ADR-01: 2-Lambda Split & Local Bypass
**Status:** Accepted
**Context:** `opendataloader-pdf` requires a JVM. AWS Lambda deployment limits (250MB unzipped) make bundling JRE + Python dependencies impossible in a single ZIP package. However, forcing local development to rely on AWS SQS and Lambda infrastructure breaks the developer loop and causes integration hallucinations.
**Decision:** In Production, split the backend into Lambda A (Docker image with JRE + ODL + PyMuPDF) and Lambda B (Python ZIP with FastAPI + Scoring). In Local Dev, use FastAPI `BackgroundTasks` to run Lambda A's parsing logic in a background thread, bypassing SQS entirely.
**Consequences:** Requires an `ENVIRONMENT` check in the upload route. Local dev is fully functional without AWS networking. Production requires container image deployment for Lambda A.

## ADR-02: SSE over WebSockets
**Status:** Accepted
**Context:** AWS Lambda is stateless. Implementing WebSockets requires API Gateway WebSocket API + DynamoDB connection mapping, adding massive operational complexity and failure points for a unidirectional progress bar.
**Decision:** Use FastAPI `StreamingResponse` (Server-Sent Events). The client opens an SSE stream; Lambda B polls DynamoDB for state changes and emits events. 
**Consequences:** One-way communication only (sufficient for progress bars). The `/extract` endpoint must be configured with AWS Lambda Function URLs (`RESPONSE_STREAM` mode) or API Gateway HTTP API to avoid the 29-second REST API timeout.

## ADR-03: Tiered Extraction (PyMuPDF → Structural Quality Gate → ODL)
**Status:** Accepted
**Context:** `opendataloader-pdf` (ODL) is slow and heavy. Running it on every resume is a waste of compute. However, V1's PyMuPDF fails on multi-column layouts. We cannot use V1's post-extraction "composite presence score" to route fallbacks, because a garbled layout might still produce a non-empty (but wrong) `experience` field.
**Decision:** Run PyMuPDF first. Calculate a *pre-extraction structural heuristic* (x-coordinate clustering, reading order monotonicity, char density, table detection) BEFORE any regex parsing. If the structural quality score `< 0.90`, fall back to ODL.
**Consequences:** ODL fallback rate is empirically measurable via `StageTiming` instrumentation. The structural quality gate formula must be strictly maintained and cannot be swapped for a post-extraction metric.

**Aug 2026 Formula Revision (after 200-resume empirical benchmark):**
- **Root-cause finding:** `reading_order_monotonicity` cannot distinguish garbled 2-column text from clean text. PyMuPDF Y-coordinates remain monotonically non-decreasing even in 2-column layouts, so the signal is flat (~0.95) for all valid text PDFs.
- **Fix:** Shifted all discriminating weight onto `col_penalty` (weighted 0.35, binary 1.0/0.0). X-clustering gap raised from 20 px → 50 px to detect true structural columns only.
- **Formula change:** `0.35×col_penalty + 0.30×reading_order + 0.20×char_density + 0.15×not_table_heavy`  *(was: `0.40×reading_order + 0.35×char_density + 0.15×not_table_heavy + 0.10×col_penalty`)*
- **Threshold:** Lowered from 0.90 → 0.70 to prevent excessive ODL triggering on sparse-but-clean resumes.
- **Before (200 resumes, v1 formula, threshold 0.90):** PyMuPDF 37.5% / ODL 4.5% / Nova 58.0%
- **After (200 resumes, v2 formula, threshold 0.70):** PyMuPDF 35.5% / ODL 2.0% / Nova 62.5%
- **Observation:** ODL rate dropped (not increased) because the 50 px x-clustering is flagging some 1-column resumes with right-aligned date columns as 2-column, pushing them into ODL→Nova path (counts as Nova in layer breakdown). Further calibration of the x-clustering gap or switching to absolute page-width fraction is a tracked follow-up item.


## ADR-04: DynamoDB with Purpose-Built GSIs (No Postgres Migration)
**Status:** Accepted
**Context:** V1 uses DynamoDB. V2 requirements (score-range filtering, skill-presence filtering, CSV export) cannot be efficiently supported by DynamoDB base table scans. A migration to PostgreSQL was considered to solve this natively.
**Decision:** Remain on DynamoDB to minimize V1 migration risk. Solve multi-attribute filtering by implementing specific Global Secondary Indexes (GSIs) up front: GSI1 (bucketed score ranges), GSI2 (sparse skill presence), GSI3 (status). 
**Consequences:** `scan()` with `FilterExpression` is strictly prohibited for candidate queries. Score ranges require client-side bucket math. DynamoDB access patterns are locked and must not be improvised.

## ADR-05: Amazon Nova Micro for LLM Fallback
**Status:** Accepted
**Context:** The deterministic regex engine fails on ~10% of fields (e.g., weird date formats, ambiguous startup titles). Claude Sonnet is too expensive for bulk structured infill.
**Decision:** Use Amazon Nova Micro via Bedrock. Use `toolConfig` to enforce strict JSON schema (constrained decoding). Batch up to 10 unresolved chunks per API call. Temperature = 0.0.
**Consequences:** Near-zero hallucination due to constrained decoding and zero temperature. Fractions of a cent per 1000 resumes. LLM is strictly prohibited from overwriting deterministic-resolved fields.

## ADR-06: Fixed Reference-Corpus BM25 IDF
**Status:** Accepted
**Context:** V1 computed BM25 IDF dynamically over the candidate pool. This meant a candidate's score changed depending on who else was in the batch, breaking incremental/streaming UX and single-resume previews.
**Decision:** Pre-compute a global IDF table from a 10,000+ resume reference corpus. Ship it as `registries/idf.pkl`. 
**Consequences:** Single-resume scoring is deterministic and stable. Scores are comparable across different jobs and time periods. The IDF table requires periodic offline recomputation as the reference corpus grows.

## ADR-07: No Authentication Layer (HC-01)
**Status:** Accepted
**Context:** V2 stores candidate PII (resumes, contact info) and provides endpoints for creating jobs and scoring candidates. Implementing JWT/OAuth adds infrastructure complexity (Cognito/Auth0) and development overhead that currently bottlenecks rapid iteration. 
**Decision:** All `/api/v2/` endpoints are unauthenticated (open). The standalone `/api/v2/ats-check` endpoint is IP-rate-limited to prevent abuse.
**Consequences:** This is an explicit, accepted product risk for the V2 MVP. The system MUST NOT be deployed to a public-facing production environment without a reverse proxy (e.g., API Gateway with a custom authorizer or Cognito) in front of it. PII redaction in logs is strictly enforced to mitigate data leakage during local/development access.

## ADR-08: Standalone ODL Lambda via ECR
**Status:** Accepted
**Context:** `opendataloader-pdf` requires a JVM. Bundling it in Resume Ranker complicates deployments.
**Decision:** Deploy ODL as a standalone Lambda container image. Resume Ranker calls it synchronously via `boto3` using the S3 Pointer Pattern.
**Consequences:** Adds network latency (~1-2s) for complex PDFs. Requires configuring `boto3` to point to real AWS even when `ENVIRONMENT=local`.

## ADR-09: ODL-Lambda Invocation Resilience (Timeout, Retry, Concurrency)
**Status:** Accepted
**Context:** Lambda A invokes odl-parser-lambda synchronously (RequestResponse). This blocks and bills Lambda A for the full duration of odl-parser-lambda's cold start + JVM boot + parse time. Three failure modes were previously unspecified: (1) Lambda A timing out before odl-parser-lambda returns, (2) odl-parser-lambda erroring or throttling, (3) concurrent invocation limits under batch load.
**Decision:**
  - Lambda A's own timeout MUST be set to at least [odl-parser-lambda p99 duration + 10s buffer]. This value MUST be empirically determined via StageTiming data in Phase 3 before Phase 4 infrastructure is finalized — do not hardcode a guess.
  - If odl-parser-lambda invocation raises (error, throttle, or timeout), Lambda A MUST catch the exception, mark the document's StageTiming record with triggered_fallback=false and an error reason, set DynamoDB status to PARSE_FAILED (not silently skip), and route the document directly to Nova fallback using RAW PyMuPDF output as the input chunk (degraded but non-blocking).
  - odl-parser-lambda MUST be deployed with Reserved Concurrency set to a fixed value (define in template.yaml, initial value: 10). Lambda A invocations beyond that concurrency limit MUST retry with exponential backoff (max 2 retries) before falling through to the PARSE_FAILED path above.
**Consequences:** Adds a defined degraded path so no document silently disappears from the pipeline. Requires Phase 3 benchmark data before Phase 4 timeout values can be finalized — Phase 4 gate criteria must include "ODL Lambda timeout value confirmed via Phase 3 StageTiming data," not a placeholder. The Local Bypass (direct Python import of odl/main.py, see architecture.md) uses a different failure surface than the production boto3.invoke() path — import errors and in-process exceptions instead of cold-start/throttle/concurrency errors. Both paths MUST funnel into the same PARSE_FAILED handling in odl_client.py via a single try/except wrapping both branches, so callers (Phase 3 pipeline code) never need to know which environment they're in. Do not duplicate error-handling logic across the two branches.

## ADR-10: Multi-PDF Batch convert() Support and Partial Failures
**Status:** Accepted
**Context:** ODL's `convert()` is expensive per-file due to JVM boots. Passing an array of files processes them sequentially in a single JVM run, yielding ~2.4× throughput speedups (from 1.06s/file down to 0.44s/file, measured locally on 5 same-size PDFs). However, if any PDF in the batch is corrupted, `convert()` finishes processing valid files but exits with return code 1, which raises a `CalledProcessError` in Python.
**Decision:**
  - Change the event contract to accept an array of documents (`{"documents": [...]}`). 
  - Wrap `convert()` in a try/except block. Since the output for valid files is still written despite the exception, `lambda_handler` MUST rely strictly on the existence of `.md`/`.json` output files to determine success — not on exit code or exception absence.
  - Return `{ "results": [...], "failed": [...] }`.
  - `odl_client.py` exposes `parse_batch(documents: List[DocDescriptor]) -> BatchParseResult` which maps `failed` doc_ids to per-document `ODLParseError` entries. Callers never see a batch-level exception.
**Partial-failure behavior (empirically confirmed):** When a corrupt PDF is in a batch of N, `convert()` processes all valid files, writes their `.md` and `.json` outputs, then raises `CalledProcessError` (exit code 1). The lambda catches this, then checks for output files: docs with files get `results`, docs without get `failed`. The pipeline degrades the failed doc to PyMuPDF text and marks it `PARSE_FAILED` — no silent drop.
**UX tradeoff:** In production, `MaximumBatchingWindowInSeconds=60` means a single quality-failed document on low-traffic periods may wait up to 60 seconds for its batch window to flush. This is an explicit, accepted tradeoff: ODL is used for layout-scrambled multi-column PDFs where the extra latency is preferable to garbled extraction output. The `/ats-check` path is exempt and uses `parse()` directly (synchronous, user-facing).
**Consequences:** Substantially increases batch throughput and eliminates N-1 JVM cold starts. Requires callers to adapt to the batch API and explicitly handle partial failures returned in the `"failed"` list.

## ADR-11: Nova Trigger Scoped to Critical Fields Only
**Status:** Accepted  
**Context:** Step 0 classification on 200 resumes showed 151 Nova invocations (75.5% fallback rate). Analysis of unresolved chunks showed Nova was being triggered by missing `education` entries and other non-critical fields even when `name`, `email`, `phone`, `experience`, and `skills` were all resolved. Every Nova call costs ~4s (rate-limit floor) and real Bedrock spend. Triggering it for `education` alone is a cost/latency regression with no product-quality upside for the ranking use-case.  
**Decision:** Nova MUST only fire when at least one of the five **critical** fields (`name`, `email`, `phone`, `experience`, `skills`) is unresolved after deterministic parsing. `education`, `projects`, `github`, and `location` are **best-effort only** — they will remain null on regex-miss. This is a permanent product policy change (not an optimization tweak): these fields carry no scoring weight in the composite formula and are not part of the 93% composite target.  
**Tradeoff explicitly accepted:**
- **Savings:** Eliminates Nova invocations for docs where only non-critical fields are missing. Expected Nova rate reduction: see benchmark post-fix.
- **Cost:** `education` field will be null for any resume where the regex parser fails and all critical fields are present. This is accepted: education is not in the 5-field composite score.  
**Implementation:** `markdown_extraction_service.py` already contains the critical-fields gate (lines 39–46). This ADR locks that gate definition and forbids expanding it to include `education` or other non-critical fields without an explicit ADR update.  
**Benchmark baseline (pre-fix, 200 docs, seed=42):** Nova fallback 75.5% (151/200). Post-fix target: 5–8%.

