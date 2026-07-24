# Resume Ranker V2 — Architecture Decision Records (ADRs)

> **Documented Technical Decisions, Rationales, Tradeoffs, and Rejected Alternatives.** *Rev 2 — Hybrid Architecture.*

---

## ADR-01: Hybrid Extraction (Deterministic + LLM Fallback)

* **Status:** `Accepted`

### Context
V1's regex/dictionary engine benchmarked at 100% F1 on skill matching and 85%+ on field extraction when fed clean text. The 72/100 extraction ceiling was caused by PyMuPDF feeding garbled column-scrambled text to otherwise correct parsers. Two options existed:
1. Replace all parsers with a full LLM pipeline.
2. Fix document input parsing and retain existing regex engines.

### Decision
Adopt a **Hybrid Extraction Pipeline**.
* Use `opendataloader-pdf` to fix structural layout parsing deterministically.
* Port V1 regex/dictionary engines to consume ODL's clean Markdown output.
* Invoke Amazon Nova (Micro/Lite) only for fields marked `unresolved` by the deterministic engine (~10% of cases).
* Batch LLM calls (5–10 documents per Bedrock invocation).

### Consequences
* LLM API cost reduced by `~98%` vs a pure-LLM pipeline.
* Latency for 90% of resumes drops from 5–8s (LLM) to `< 2s` (deterministic).
* Extraction accuracy improves from 72/100 to target `> 92%`.
* Codebase retains V1's proven, deterministic matching logic.
* *New Dependency:* JVM runtime requirement for ODL (dictates ECS Fargate over AWS Lambda).

### Alternatives Considered
* **Pure LLM Extraction (Claude Sonnet):** Rejected due to cost ($5/100 resumes), latency (8s/resume), non-determinism, and evidence showing regex matching was not the root cause.
* **Pure Deterministic Extraction (ODL + Regex Only):** Rejected. Leaves ~10% of complex resumes with unresolved fields and no fallback path.
* **ODL + SpaCy NER:** Rejected. SpaCy NER trained on news/Wikipedia data misses modern tech skills and startup names; V1's hand-curated dictionaries perform significantly better.

---

## ADR-02: Amazon Nova for LLM Fallback (Not Claude)

* **Status:** `Accepted`

### Context
The LLM fallback path extracts structured fields (dates, company names, skill lists) from localized text chunks. This is bulk structured infill, not complex reasoning. Claude Sonnet is excessive; Claude Haiku is faster but still cost-prohibitive at scale.

### Decision
Use **Amazon Nova Micro** as the primary fallback model, with **Nova Lite** for escalation when confidence is `< 0.5`. Use Bedrock's tool-use constrained decoding (temperature = `0.0`).

### Consequences
* **Cost:** Fractions of a cent per 1,000 resumes (vs dollars for Claude).
* **Speed:** 1–2s per batched call (vs 5–8s for Claude).
* **Reliability:** Tool-use schema enforces `> 95%` valid JSON structures.
* Vendor lock-in is isolated behind the `NovaFallbackService` Anti-Corruption Layer.

### Alternatives Considered
* **Claude Haiku:** Rejected. 5–10x higher cost than Nova Micro for identical structured extraction tasks.
* **OpenRouter Free Tier (Llama 3 8B):** Rejected. Rate limits break batch processing; lacks tool-use constrained decoding.
* **Self-Hosted Llama 3 8B:** Rejected. High GPU infrastructure cost and complexity for a path running ~10% of the time.

---

## ADR-03: ATS Scoring is 100% Deterministic (No LLM)

* **Status:** `Accepted`

### Context
ATS format failures are structural (two-column layouts, hidden text, table-as-layout, missing contact info). Detecting these requires spatial reasoning over bounding box ($x, y$) coordinates, which LLMs cannot reliably perform from raw text. `opendataloader-pdf` provides exact element bounding boxes.

### Decision
Implement ATS scoring as pure Python bounding-box clustering and regex evaluation over 5 key signals:
1. Two-Column Layout (Bbox clustering)
2. Hidden Text (`ODL` flag)
3. Table-as-Layout (Element type + section context)
4. Parseability (Character ratio)
5. Contact Presence (Regex)

Calculates a weighted average 0–100 score with zero LLM invocations.

### Consequences
* ATS score is 100% deterministic (same input $\rightarrow$ same output, always).
* Execution is instant (`< 100ms` per document) and zero cost.
* ATS engine is completely decoupled from Job and Extraction contexts, enabling standalone `/api/v2/ats-check`.

### Alternatives Considered
* **LLM-Based ATS Scoring:** Rejected. LLMs cannot reliably evaluate spatial coordinate layouts from text.
* **Third-Party ATS API (e.g. Resumego):** Rejected. Creates external service dependency and cost per check.

---

## ADR-04: Fixed Reference-Corpus BM25 IDF (Not Dynamic Per-Pool)

* **Status:** `Accepted`

### Context
V1 computed BM25 Inverse Document Frequency (IDF) dynamically across the active candidate pool. As a result, a candidate's skill score changed based on co-uploaded resumes in the batch (e.g. candidate ranked #1 in a pool of 10 dropped to #3 when 50 resumes were added). This broke streaming UX and single-resume preview features.

### Decision
Pre-compute a global IDF lookup table from a 10,000+ resume reference corpus (`registries/idf.pkl`). Dynamic per-pool IDF remains available via an opt-in `--dynamic-idf` flag.

### Consequences
* Single-resume scoring is completely deterministic and stable over time.
* Scores are directly comparable across different job postings.
* Reference corpus IDF table requires quarterly recomputation.

### Alternatives Considered
* **Keep Dynamic Per-Pool IDF:** Rejected due to non-determinism and broken streaming UX.
* **Use Plain TF-IDF Only:** Rejected. BM25 term frequency saturation and length normalization provide superior candidate ranking.

---

## ADR-05: AWS Lambda Deployment with SQS (Replacing ECS Fargate)

* **Status:** `Accepted` (Supersedes previous ECS Fargate decision)

### Context
Rev 2 initially proposed ECS Fargate due to two concerns:
1. JVM cold starts for `opendataloader-pdf` (1–3s) plus Lambda cold starts (1–5s) violating P95 latency goals.
2. Celery requiring a persistent worker process to maintain its batching-window state for Nova fallback accumulation.
However, Rev 3 addresses these efficiently without leaving the Lambda ecosystem: SQS provides a native event-source mapping with `BatchSize` and `MaximumBatchingWindowInSeconds`, removing the need for a Celery-based Redis buffer entirely. Provisioned Concurrency for the Lambda container image keeps the JVM warm on a scheduled basis, matching business hours.

### Decision
Deploy the API and Worker as **AWS Lambda** functions using a container image. 
* Use **Amazon SQS** with native batch windows to trigger the Worker Lambda.
* Use **Provisioned Concurrency** (managed by Application Auto Scaling schedules) to neutralize JVM cold starts.
* API runs via API Gateway HTTP API v2 (using Mangum), with WebSockets managed via a separate integration maintaining state in DynamoDB.

### Consequences
* Batching is handled entirely by AWS infrastructure (SQS event mapping) rather than application code (Celery/Redis).
* Provisioned concurrency incurs idle costs but is schedulable, offering significant savings during off-hours compared to always-on Fargate tasks.
* Residual risk: Unscheduled off-hours bursts will experience the JVM cold start penalty.

### Alternatives Considered
* **ECS Fargate:** Rejected in Rev 3. Unnecessary overhead and always-on cost when SQS + Lambda Provisioned Concurrency handles the requirements natively and matches the existing V1 infrastructure model.

---

## ADR-06: Conditional Semantic Embeddings (Not Universal)

* **Status:** `Accepted`

### Context
Running sentence-transformer embeddings (`all-MiniLM-L6-v2`) across 100% of resumes creates unnecessary compute overhead. BM25 and skill-graph traversal already resolve `~95%` of candidate matches unambiguously.

### Decision
Compute and store embeddings **only if** the candidate's skill score falls within an ambiguous band (`0.4–0.6`). Outside this band, `semantic_score = null` and the composite formula renormalizes remaining component weights.

### Consequences
* `~95%` of processed resumes skip embedding compute entirely.
* `all-MiniLM-L6-v2` model is loaded lazily on demand.
* Composite scoring formula dynamically handles `null` semantic scores.

### Alternatives Considered
* **Universal Embeddings:** Rejected. Always-on compute cost for marginal signal gains on non-ambiguous resumes.
* **No Embeddings At All:** Rejected. Embeddings provide crucial tiebreaker value in the ambiguous 0.4–0.6 score band.

---

## ADR-07: Composite Score Computed at Read Time (Never Stored)

* **Status:** `Accepted`

### Context
Storing composite scores in the database requires re-scoring every candidate in a job whenever a recruiter adjusts scoring weights. For 500 candidates, this triggers 500 database write operations and breaks the `< 200ms` weight adjustment requirement.

### Decision
Persist **only immutable component scores** (`skill_score`, `experience_score`, `education_score`, `semantic_score`). The composite score is calculated strictly at read time (client-side via Zustand derived selectors, backend via repository read methods).

### Consequences
* Weight adjustments are instant (`< 200ms`) with zero database writes.
* Component scores are immutable once stored.
* Composite scores are guaranteed to reflect current job weight settings.

### Alternatives Considered
* **Store Composite Score & Recompute on Weight Change:** Rejected due to $O(N)$ DB write overhead per weight adjustment.
