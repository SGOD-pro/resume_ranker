# Resume Ranker V2 — System Requirements & Hard Constraints

> **Comprehensive Functional & Non-Functional Requirements, Architectural Constraints, and Scope Boundaries.** *Rev 2 — Hybrid Architecture.*

---

## 1. Functional Requirements

### 1.1 Resume Ingestion

- **`FR-01`**: System **MUST** accept PDF resumes (single and batch uploads, up to 50 files per job).
- **`FR-02`**: System **MUST** process each resume end-to-end in under 15 seconds P95 under normal load.
- **`FR-03`**: System **MUST** support drag-and-drop file upload as well as programmatic submission via API.
- **`FR-04`**: System **MUST** reject non-PDF files at the API boundary with `HTTP 415` and a descriptive error message.
- **`FR-05`**: System **MUST** deduplicate resumes within a job by content hash (`SHA-256` of file bytes). Duplicate submission returns the existing result within `< 200ms`.

### 1.2 Extraction

- **`FR-06`**: Extraction **MUST** produce structured outputs including contact info, work experience (role, company, dates, description), education (degree, institution, dates), skills (explicit + inferred), certifications, and projects.
- **`FR-07`**: Each extraction field **MUST** carry a confidence score (`0.0–1.0`) and provenance tag (`deterministic` | `nova_fallback` | `unresolved`).
- **`FR-08`**: Extraction **MUST** handle multi-column layouts, embedded tables, and non-standard section headers — resolved at the structural parsing layer (`opendataloader-pdf`), not the field extraction layer.
- **`FR-09`**: Total years of experience **MUST** be computed strictly from parsed date ranges, not estimated from keywords.
- **`FR-10`**: Skill extraction **MUST** distinguish between explicitly listed skills and skills inferred from work experience descriptions.
- **`FR-11`**: Extraction failures **MUST** be surfaced per-field with the raw text chunk that failed — never swallowed into a generic error.
- **`FR-12`**: The deterministic extraction engine **MUST** be the primary path. The LLM fallback (Amazon Nova) **MUST** only be invoked for fields marked `unresolved` by the deterministic engine.
- **`FR-13`**: LLM fallback calls **MUST** be batched (5–10 documents or 5 minutes, whichever comes first). Single-document LLM calls are prohibited in batch processing mode.

### 1.3 Job Configuration

- **`FR-14`**: A job **MUST** define: title, description, required skills, nice-to-have skills, minimum years of experience, education requirements, knockout criteria, and scoring weights.
- **`FR-15`**: Recruiters **MUST** be able to adjust scoring weights and view updated composite scores in real-time without backend re-processing.
- **`FR-16`**: Knockout criteria **MUST** act as hard filters. Disqualified candidates appear in a separate list with explicit disqualification reasons.
- **`FR-17`**: System **MUST** support a minimum of 10 concurrent active jobs per workspace.

### 1.4 Scoring

- **`FR-18`**: Final score **MUST** be a weighted composite of: skill match, experience, education, and (conditionally) semantic similarity.
- **`FR-19`**: Skill matching **MUST** account for semantic equivalence via skill-graph traversal (`synonym`, `implies`, `related` edges).
- **`FR-20`**: Complete score breakdown **MUST** be visible at candidate detail level — component scores, provenance, and matched/missing skills.
- **`FR-21`**: Weight recomputation **MUST** happen client-side in `< 200ms` for 100 candidates with zero backend API calls.
- **`FR-22`**: System **MUST** flag: employment gaps `> 6 months`, short tenures `< 3 months`, and skills listed without supporting work experience.
- **`FR-23`**: BM25 IDF **MUST** be computed from a fixed reference corpus, not the active candidate pool. A candidate's score **MUST NOT** fluctuate when pool size changes.

### 1.5 ATS Scoring

- **`FR-24`**: System **MUST** provide a standalone ATS checker endpoint (`POST /api/v2/ats-check`) that accepts a PDF and returns an ATS score without creating a job or persisting the document.
- **`FR-25`**: ATS scoring **MUST** be 100% deterministic with zero LLM calls.
- **`FR-26`**: ATS scoring **MUST** detect: two-column layouts, hidden text, table-as-layout structures, parseability issues, and missing contact info.
- **`FR-27`**: ATS output **MUST** include actionable fix suggestions per failed signal.
- **`FR-28`**: ATS score **MUST NOT** gate candidate visibility in the recruiter dashboard — it serves as a warning layer, not a filter.

### 1.6 Candidate Management

- **`FR-29`**: Candidates **MUST** be filterable by score range, status, present skills, and ATS score range.
- **`FR-30`**: Candidates **MUST** be sortable by composite score, experience years, most recent role date, and ATS score.
- **`FR-31`**: Recruiters **MUST** be able to shortlist, reject, or mark candidates for review with persistent status tracking.
- **`FR-32`**: System **MUST** support CSV export of ranked candidates along with full score breakdowns and flags.

### 1.7 Real-Time Feedback

- **`FR-33`**: File upload progress **MUST** be visible per file in real-time.
- **`FR-34`**: Candidate list **MUST** update via WebSockets as individual resumes complete processing.
- **`FR-35`**: WebSocket **MUST** support `candidate_partial` messages (JD score ready while ATS score is still computing) so the frontend renders immediately available data.

---

## 2. Non-Functional Requirements

### 2.1 Performance

- **`NFR-01`**: API P95 for scoring endpoint: `< 10 seconds` (including LLM fallback when triggered).
- **`NFR-02`**: Deterministic-only extraction path: `< 3 seconds` P95.
- **`NFR-03`**: Frontend weight recomputation: `< 200ms` for 100 candidates.
- **`NFR-04`**: Batch processing of 20 resumes **MUST** complete the full pipeline in `< 5 minutes`.
- **`NFR-05`**: Standalone ATS check **MUST** return in `< 1 second` (no LLM, no DB write, down from previous 5s target).
- **`NFR-05b`**: Evaluation hot path (JD Scoring + ATS) **MUST** execute in `< 50ms` p95 and **MUST NOT** instantiate any JVM or parse raw PDFs.

### 2.2 Reliability

- **`NFR-06`**: LLM fallback failures **MUST** retry at most once with exponential backoff before marking fields as `unresolved`.
- **`NFR-07`**: Partial extraction results **MUST** be persisted — a single field failure does not discard the document.
- **`NFR-08`**: Target system uptime: `99.5%`.

### 2.3 Security

- **`NFR-09`**: Resume PDFs **MUST** be encrypted at rest (`S3 SSE-S3`, `AES-256`).
- **`NFR-10`**: All `/api/v2/` endpoints **MUST** require JWT authentication (except `/api/v2/ats-check` which is IP-rate-limited).
- **`NFR-11`**: Personally Identifiable Information (PII like email and phone) **MUST NOT** appear in structured logs (use `REDACTED`).
- **`NFR-12`**: File uploads **MUST** be validated by magic bytes, not file extensions alone.

### 2.4 Observability

- **`NFR-13`**: Every pipeline run **MUST** emit structured logs containing: `job_id`, `document_id`, `stage`, `duration_ms`, `success`, and `nova_invoked`.
- **`NFR-14`**: Nova fallback rate **MUST** be tracked as a CloudWatch metric with an alarm at `> 20%`.
- **`NFR-15`**: ATS scoring latency **MUST** be logged separately from JD scoring latency.
- **`NFR-16`**: `/health` endpoint **MUST** monitor DB, Redis, S3, and Bedrock connectivity.

### 2.5 Data Governance

- **`NFR-17`**: Extracted candidate data retained for a minimum of 90 days.
- **`NFR-18`**: System **MUST** support full job data deletion for GDPR compliance, cascading to documents, scores, ATS results, and fallback records.
- **`NFR-19`**: Cached `opendataloader-pdf` structural parse outputs **MUST** be retained in S3 for 30 days for deduplication and reprocessing.

---

## 3. Hard Constraints (Non-Negotiable)

| ID | Constraint Specification |
| :--- | :--- |
| **`HC-01`** | LLM provider **MUST** be swappable via config. No direct `anthropic` or `boto3` calls outside `NovaFallbackService`. |
| **`HC-02`** | No score is presented without a visible breakdown. Composite scores without component provenance are prohibited. |
| **`HC-03`** | Weight adjustments **MUST NOT** trigger backend re-extraction or re-scoring. Composite is computed at read time. |
| **`HC-04`** | Knockout disqualifications **MUST** be logged with an explicit reason string. |
| **`HC-05`** | Skill graph **MUST** be data-driven (DB-backed) and updatable without a code deploy. |
| **`HC-06`** | All API contracts **MUST** be versioned (`/api/v2/`). V1 endpoints remain active during migration. |
| **`HC-07`** | The deterministic extraction engine **MUST** be the default path. LLM fallback is opt-in per-field, never per-document. |
| **`HC-08`** | ATS scoring **MUST NOT** call any LLM. It operates on bounding boxes (`bbox`) only. |
| **`HC-09`** | LLM fallback **MUST** use tool-use constrained decoding, not prompt-based JSON instructions. |
| **`HC-10`** | LLM fallback calls **MUST** be batched. Single-document LLM calls in batch processing mode are prohibited. |
| **`HC-11`** | BM25 IDF **MUST** come from a fixed reference corpus, not the candidate pool. |
| **`HC-12`** | Semantic embedding similarity **MUST** be conditional (ambiguous score band only), not universal. |

---

## 4. Out of Scope for V2

- ❌ **Interview Scheduling**: Automated candidate calendar scheduling.
- ❌ **ATS Sync**: Direct integration/sync with external ATS tools (Greenhouse, Lever).
- ❌ **Candidate Portal**: Resume builder or self-service candidate portal.
- ❌ **Multi-Language Support**: Support for non-English resumes (English only for V2).
- ❌ **Mobile Native Apps**: Native iOS/Android applications.
- ❌ **Custom ML Training**: Custom model fine-tuning or training pipelines.
- ❌ **Reciprocal Rank Fusion (RRF)**: Solves a problem V2 doesn't have once IDF is fixed.
