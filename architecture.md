# architecture.md — Resume Ranker V2
> System architecture, tech stack, and data flow. Every component justified.
> **Rev 3** — Rev 2 corrected the extraction pipeline (deterministic-first, LLM fallback). Rev 3 corrects the deployment target: Lambda, not ECS Fargate — matching V1's existing Mangum-based Lambda deployment, and replacing Celery+Redis batching with native SQS batch windows.

---

## 0. What Changed From Rev 1 → Rev 2 → Rev 3

**Rev 1's mistake:** routing 100% of resumes through an LLM. Wrong on cost, latency, and evidence — V1's benchmark (`benchmark_v4/report.json`) shows the skill matching engine hit **100% F1** and the regex/dictionary layer hit **85%+ field extraction** on structured resumes. The real failure was layout geometry (PyMuPDF pixel-clustering breaking on 2-column/table layouts, capping extraction at 72/100), not the matching logic.

**Rev 2's fix:** hybrid pipeline. Deterministic engine handles ~90% of resumes end-to-end for free, in milliseconds. LLM (Amazon Nova Micro/Lite via Bedrock, batched, constrained-decoding tool calls, temperature=0) only touches the ~10% flagged unparseable. ATS scoring is 100% deterministic bounding-box math.

**Rev 2's remaining mistake:** it argued ECS Fargate was required because `opendataloader-pdf` is a JVM process and Celery needs a persistent process for its batching-window state. That's true for a Celery-based buffer — but it's solving a self-inflicted problem. **Rev 3 fix:** drop the application-level Redis buffer entirely and use **SQS's native batch trigger** (`batchSize` + `maxBatchingWindowInSeconds`), which is a first-class Lambda event-source feature, not a workaround. The JVM cold-start problem is real but is solved with a **Lambda container image + provisioned concurrency**, not by moving the whole runtime to Fargate. This also matches what V1 already runs — `lambda_handler.py` already wraps the FastAPI app with Mangum. Rev 3 is a continuation of existing infrastructure, not a rebuild of it.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT (Browser)                            │
│  React 18 + TS + Vite + Zustand + TanStack Query + WebSocket client  │
│  Recruiter Dashboard | Candidate Detail | Standalone ATS Checker     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS / WSS
┌──────────────────────────────▼───────────────────────────────────────┐
│         API — FastAPI + Mangum on AWS Lambda (API Gateway)           │
│  /api/v2/jobs  /api/v2/candidates  /api/v2/ats-check  (REST)         │
│  API Gateway WebSocket API → separate connect/disconnect/message     │
│  Lambda handlers, connection state in DynamoDB                       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ SQS: DocumentProcessingQueue
┌──────────────────────────────▼───────────────────────────────────────┐
│      WORKER — Lambda (container image, JVM bundled, SQS-triggered,   │
│                provisioned concurrency keeps JVM warm)                │
│                                                                       │
│  Stage 1: STRUCTURAL EXTRACTION (opendataloader-pdf, deterministic)  │
│    PDF → kids[] (heading/paragraph/table/list) + bbox + hidden flag  │
│                          │                                            │
│         ┌────────────────┴────────────────┐                          │
│         ▼                                  ▼                          │
│  Stage 2A: V1 DETERMINISTIC ENGINE   Stage 2B: ATS DETERMINISTIC     │
│    (ported regex/dict/skill-graph)     ENGINE (bbox-only, parallel,  │
│    contact/exp/edu/skills/certs        never blocks candidate score) │
│         │                                  │                          │
│    ~90% success  │  ~10% unparsed chunks   │                          │
│         │                  │               │                          │
│         │         Stage 3: NOVA FALLBACK   │                          │
│         │         (SQS UnresolvedChunkQueue│                          │
│         │          batchSize=10, window=5m │                          │
│         │          → Lambda, Bedrock       │                          │
│         │          tool-use, temp=0)       │                          │
│         │                  │               │                          │
│         └────────┬─────────┘               │                          │
│                  ▼                         │                          │
│         MERGED CandidateDocument           │                          │
│                  │                         │                          │
│                  ▼                         ▼                          │
│         Stage 4: JD SCORING          ATS SCORE + FIX SUGGESTIONS      │
│         (BM25 + skill-graph +                                        │
│          knockouts — deterministic)                                  │
│                  │                         │                          │
│                  └───────────┬─────────────┘                          │
│                              ▼                                        │
│                    Composite result → Postgres → WebSocket push       │
└─────────────────────────────────────────────────────────────────────┘
```

**Design invariant:** ATS scoring and JD scoring are independent parallel branches. A resume with a terrible ATS score (two-column, hidden text) is **never hidden from the recruiter** — it still gets a JD match score. ATS is a warning layer, not a filter.

---

## 2. Tech Stack — Every Choice Justified

### 2.1 Extraction Layer (the part that actually changes)

| Component | Choice | Justification |
|---|---|---|
| **Structural parsing** | `opendataloader-pdf` | Replaces PyMuPDF's pixel-wise clustering. Produces `kids[]` with `type` (heading/paragraph/table/list), `bounding box`, and `hidden text` flags. This is the fix for the 72/100 extraction ceiling — it's a layout problem, solved with layout data, not language understanding. |
| **Deterministic field extraction** | Ported V1 engine: `skill_registry.py`, `section_registry.py`, `experience_parser.py`, `education_parser.py`, `contact_parser.py`, run against ODL's clean markdown/JSON instead of raw PyMuPDF geometry | **Keep, don't replace.** This code already scores 100% F1 on skill matching in the V1 benchmark. The regex was never the problem — feeding it garbled column-scrambled text was. Same regex, clean input, expect accuracy to jump without touching matching logic. |
| **LLM fallback** | Amazon Nova Micro (primary) / Nova Lite (complex edge cases) via Bedrock `Converse` API, **tool-use / constrained decoding**, not prompt-based JSON | AWS's own data: constrained decoding tool calls cut structured-output errors >95% vs prompting the model to "please output valid JSON." Temp=0. Batched every 5–10 resumes or 5 minutes — never one API call per resume. |
| **ATS scoring** | Pure Python bbox clustering on ODL output. Zero LLM calls. | An LLM cannot spatially reason about x/y coordinates reliably. Two-column detection is arithmetic (cluster `bbox[0]` gaps), not language understanding. Free, instant, 100% deterministic — same input always gives same output, which matters when a job-seeker refreshes the page expecting the same score. |

**Cost consequence of the fix:** Rev 1 = 1 LLM call per resume (100%). Rev 2 = 1 batched LLM call per ~5–10 resumes, only when the deterministic engine fails (~10% of docs). That's roughly a **98% reduction in LLM invocations** at typical volume, not "90% cheaper" — the batching multiplies the failure-rate reduction.

### 2.2 Why Amazon Nova, Not Claude, for the Fallback

Rev 1 specified Claude for extraction. That's now wrong for two reasons:
1. **This is bulk, low-stakes, structured infill work** — not reasoning. Nova Micro is purpose-built for exactly this (cheapest, fastest, strict schema via tool calls) and Nova Lite covers the harder 1% (ambiguous startup titles, non-standard date formats) if Micro's confidence is low.
2. **Tool-use constrained decoding on Bedrock is a hard reliability guarantee, not a prompting trick.** AWS reports >95% error reduction using tool schemas vs. system-prompt JSON instructions. We are extracting structured fields from a résumé — this is precisely the use case constrained decoding was built for.

Claude stays available as a config-swappable provider (HC-01 still applies) for cases needing actual reasoning — e.g., resolving ambiguous seniority ("Senior" vs "Sr." vs "III") — but it's not the default extraction path anymore.

### 2.3 Runtime — Lambda, and How the Two Fargate Justifications Get Neutralized

Rev 2 justified Fargate on two claims: (1) JVM cold start is fatal on Lambda, and (2) Celery needs a persistent process to hold batching-window state. Both are true *as stated* — but both premises are fixable without abandoning Lambda, and V1 is already running on Lambda via Mangum, so staying on Lambda is the lower-disruption path if the fixes hold up. They do:

**Fix for (2) — Celery batching state:** this was never a reason to need a persistent process, it was a reason to have chosen the wrong batching mechanism. SQS has **native batch triggering** built into the Lambda event-source mapping: set `BatchSize` and `MaximumBatchingWindowInSeconds` on the queue subscription, and Lambda invokes your function with up to N messages once the count *or* the time window is hit — whichever comes first. That is exactly the "5–10 chunks or 5 minutes" rule from the spec, implemented by AWS infrastructure config, not application code. No Redis buffer, no custom flush-trigger logic, no persistent process required to hold state between invocations.

**Fix for (1) — JVM cold start:** package the worker as a **Lambda container image** (supports up to 10GB, so bundling a JRE + `opendataloader-pdf` + Python runtime is fine) and set **provisioned concurrency** on that function. Provisioned concurrency pre-initializes N execution environments — including the JVM — so invocations against those environments never cold-start. This is not free (provisioned concurrency bills for idle capacity, same as Fargate does), but it is *schedulable*: `Application Auto Scaling` scheduled actions can drop provisioned concurrency to zero outside business hours (nights/weekends, when recruiters aren't uploading batches) and scale it back up before the workday starts. Fargate's always-on task cost has no equivalent lever — this is a genuine cost advantage for Lambda in a B2B-hours-only usage pattern, not just parity.

**Honest residual risk:** if provisioned concurrency is scaled to zero and a burst of uploads arrives outside the scheduled warm window, those specific invocations eat the JVM cold start (1–3s) on top of container init. Given the NFR-04 target (20 resumes in < 5 minutes) and that this only matters for off-hours bursts, that's an acceptable trade — not a free lunch, a deliberately chosen one.

| Component | Choice | Justification |
|---|---|---|
| Runtime | Python 3.12 + FastAPI + Mangum | Unchanged from V1. Async, OpenAPI, Pydantic v2, already deployed this way. |
| Compute — API | Lambda (API Gateway REST + WebSocket integration) | Stateless request handling, matches V1's existing deployment model. |
| Compute — Worker | Lambda, container image, provisioned concurrency (scheduled scaling) | Bundles JVM for `opendataloader-pdf`; provisioned concurrency neutralizes cold start on a business-hours schedule. |
| Task queue | Amazon SQS (two queues: `DocumentProcessingQueue`, `UnresolvedChunkQueue`) | Native batch-window trigger replaces Celery + Redis entirely — no custom buffering code. |
| WebSocket connection state | DynamoDB (`websocket_connections` table) | API Gateway WebSocket Lambda integrations are stateless per-invocation; connection IDs must be tracked externally to push messages via the Management API. |

### 2.4 Database

| Component | Choice | Justification |
|---|---|---|
| Primary DB | PostgreSQL (RDS) | Unchanged rationale from Rev 1 — DynamoDB's query model can't cleanly support score-range/skill-presence filtering or CSV export JOINs. |
| Vector extension | pgvector — **now optional, not core-path** | Rev 1 made semantic embedding similarity a *required* 4th scoring component for every resume. Rev 2 demotes it: JD scoring is primarily BM25 + skill-graph traversal (deterministic, matches the AWS-blueprint's stated approach). Embeddings are computed and stored **only if** the skill-graph match is ambiguous (score sits in a gray band), as a tiebreaker — not a mandatory pipeline stage. This cuts embedding compute for the ~95% of resumes with a clear-cut skill match. |
| Task queue | Amazon SQS | **Replaces Celery + Redis-as-broker (Rev 3).** Native batch-window trigger, no application code needed for the accumulate-then-flush logic. |
| Cache | Redis (ElastiCache) — **narrowed scope in Rev 3** | Now used ONLY for skill-graph read cache and IP-based rate-limit token buckets on `/ats-check`. No longer a queue broker — SQS owns that role. |
| WebSocket state | DynamoDB | Connection ID → job_id mapping for API Gateway WebSocket push (see §2.3). |
| File storage | S3, SSE-S3 encrypted | Unchanged. |

### 2.5 Semantic Similarity — Demoted, Not Deleted

Rev 1 treated embedding cosine-similarity as a mandatory 4th score component running on every document. That's an unjustified always-on cost for marginal signal when BM25 + skill-graph already resolves most matches unambiguously. Rev 2: `sentence-transformers` (`all-MiniLM-L6-v2`) stays in the stack, self-hosted, but is invoked **conditionally** — only when `skill_score` falls in an ambiguous band (configurable, default 0.4–0.6) where a semantic tiebreak actually changes the ranking outcome.

### 2.6 Matching & Scoring (Reverts Toward V1, Corrected)

Rev 1 tried to replace V1's BM25/TF-IDF scorer with Reciprocal Rank Fusion and calibration regression — solving a problem V1's benchmark didn't actually show (`skill.f1 = 100%` in the last benchmark run). Rev 2: **keep BM25 + skill-graph as primary**, matching the AWS blueprint's stated JD Scoring Engine. Fix the two things that were *actually* broken in V1:
- **Dynamic per-pool IDF** (non-deterministic — a candidate's score changes depending on who else is in the batch) → replace with a **fixed reference-corpus IDF table**, recomputed offline on a schedule, not per-request.
- **God-class `scorer.py`** (864 lines, one file, six responsibilities) → split into single-responsibility scorer modules per §design.md, same math, different file boundaries.

RRF is **not** used. It solves a rank-fusion problem V2 doesn't have once IDF is fixed and deterministic.

---

## 3. Data Flow

### 3.1 Full Pipeline (Batch Upload)

```
1. UPLOAD
   Client → presigned S3 URL → direct upload
   → SHA-256 hash check → duplicate? return cached result, skip pipeline
   → Celery task enqueued → HTTP 202 + task_id

2. STRUCTURAL EXTRACTION (opendataloader-pdf, per-document, deterministic)
   PDF bytes → convert() → { kids[]: [{type, text, bounding_box, hidden_text}], markdown }
   → Persist raw ODL JSON to S3 (cache — never re-run ODL on the same content_hash)

3. DETERMINISTIC FIELD EXTRACTION (V1 engine, ported onto ODL markdown/JSON)
   → SectionRouter maps heading elements → canonical sections (skills/experience/education/...)
   → contact_parser / experience_parser / education_parser / skills_parser run per section
   → Each field gets extracted OR flagged unparseable with the raw text chunk retained
   → If ALL required fields resolved with confidence ≥ threshold → SKIP Nova, go to step 5

4. LLM FALLBACK (Amazon Nova, batched — only for docs with unparsed chunks)
   → Failed chunks accumulate in Redis buffer, keyed by (document_id, field_name, raw_text)
   → Flush trigger: buffer reaches 5–10 chunks OR 5 minutes elapsed (whichever first)
   → Single Bedrock Converse call, tool-use schema, temp=0, batched array in/array out
   → Response merged into the document's extraction result (Nova fields never overwrite
     a field the deterministic engine already resolved with confidence ≥ threshold)

5. JD SCORING (deterministic, parallel branch A)
   → Knockout evaluation (hard filters — pass/fail, logged with reason)
   → BM25 skill match against fixed-IDF reference table
   → Skill-graph traversal for synonym/related skill credit
   → IF skill_score in ambiguous band → semantic embedding tiebreak (conditional, §2.5)
   → Composite score = weighted sum (weights are per-job config, recomputed client-side)

6. ATS SCORING (deterministic, parallel branch B — never blocks branch A)
   → Runs directly on ODL bbox output, no dependency on step 3/4 completing
   → Two-column detection, hidden-text detection, table-as-layout, parseability,
     contact-presence (see design.md §ATS Engine for full signal table)
   → Produces ats_score (0-100) + flags[] + fix_suggestions[]

7. PERSIST + PUSH
   → Postgres: extraction, scoring, ats_result rows
   → WebSocket: push { candidate_ready, jd_score, ats_score } to subscribed clients
   → Dashboard shows BOTH scores side by side — never one gates the other's visibility
```

### 3.2 Standalone ATS Checker Flow (No Job Session)

```
POST /api/v2/ats-check
  Body: multipart PDF (+ optional pasted JD text)
  → Direct synchronous processing (no Celery, no DB persistence of the document)
  → opendataloader-pdf → ATS deterministic engine → ats_score + flags + fixes
  → IF jd_text provided: lightweight BM25 match against pasted text (no job record created)
  → Returns result directly in the HTTP response, nothing written to jobs/documents tables
  → Rationale: a job-seeker checking their own resume must not create workspace/job
    clutter, and must not be billed against job-session usage metering.
```

### 3.3 Weight Recompute (Unchanged From Rev 1 — This Part Was Correct)

Component scores (`skill_score`, `experience_score`, `education_score`, `semantic_score` if computed) are immutable once persisted. Composite score is computed at read time from job weights — client-side in a Zustand derived selector for instant re-sort, server-side identically for API consumers. No re-extraction, no re-scoring, ever, on a weight change.

---

## 4. Deployment Architecture

```
AWS Region: ap-south-1

├── VPC
│   ├── Public Subnets: ALB, NAT Gateway
│   └── Private Subnets
│       ├── ECS Fargate — API service (FastAPI, stateless, autoscale on CPU)
│       ├── ECS Fargate — Worker service (Celery, JVM-warm, autoscale on queue depth)
│       ├── RDS PostgreSQL (Multi-AZ) + pgvector extension
│       └── ElastiCache Redis (Celery broker + Nova batch buffer + skill-graph cache)
│
├── S3 — PDF storage + cached ODL JSON output (SSE-S3)
├── Amazon Bedrock — Nova Micro / Nova Lite (on-demand, no provisioned throughput needed at V2 volume)
├── CloudFront — frontend static assets
├── API Gateway (WebSocket) → ALB → FastAPI WS handler
├── ECR — worker image (bundles JRE + opendataloader-pdf + Python)
├── Secrets Manager — DB creds, Bedrock IAM role config
└── CloudWatch — logs, metrics, alarms on: Nova fallback rate (%), ATS-only pipeline latency,
                  batching buffer flush frequency
```

**New operational metric that matters here and didn't exist in Rev 1:** the **Nova fallback rate** — the % of documents that require LLM assistance. If this creeps up over time (e.g., >20%), it's a signal the deterministic engine's dictionaries/regex need updating — same feedback loop V1's `ROOT_CAUSE_REPORT.md` process already established, now cheaper to run because it's isolated to the fallback path instead of contaminating every extraction.

---

## 5. What This Architecture Does NOT Include (And Why)

| Excluded | Reason |
|---|---|
| LLM extraction as the primary/default path | Rev 1's core mistake. Costly, slow, non-deterministic, and the evidence (V1 benchmark) didn't support it. |
| RRF (Reciprocal Rank Fusion) | Solves a rank-fusion problem that doesn't exist once IDF is fixed. Added complexity for zero measured benefit. |
| Mandatory embedding similarity on every resume | Marginal signal over BM25+skill-graph for the ~95% of unambiguous matches. Demoted to conditional tiebreaker. |
| LLM-based ATS scoring | An LLM is a worse instrument than arithmetic for "are these bounding boxes in two columns." Bbox clustering is deterministic, free, and auditable. |
| Kubernetes | Still over-engineered for V2 scale. ECS remains sufficient. |
| Separate vector DB service | pgvector covers V2 volume; now even less load-bearing than Rev 1 assumed since embeddings are conditional, not universal. |