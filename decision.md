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
