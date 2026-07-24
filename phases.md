# Resume Ranker V2 — Implementation Phases & Milestones

> **Strict Implementation Milestones. No phase begins until the prior phase is fully verified.** *Rev 2 — Hybrid Architecture.*

---

## Phase 0: Infrastructure Skeleton (Days 1–3)

### Deliverables
- AWS Lambda functions (API + Worker, container image via ECR)
- Amazon SQS queues (`DocumentProcessingQueue`, `UnresolvedChunkQueue`)
- RDS PostgreSQL database instance with `pgvector` extension enabled
- ElastiCache Redis cluster (for skill-graph cache and rate limiting)
- DynamoDB table (`websocket_connections`) for API Gateway WebSocket state
- S3 storage buckets (PDF uploads, ODL parse cache)
- ECR container image repository
- GitHub Actions CI pipeline (`lint`, `type-check`, `test`, `build`, `push`)

### Verification Gate
- `docker-compose up` runs API + Postgres + Redis + LocalStack (SQS/DynamoDB) locally with zero errors.
- `curl localhost:8000/health` returns `200 OK` with all components healthy.
- CI build pipeline completes successfully on a test PR.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 1 until infrastructure is live and CI is green.

---

## Phase 1: Structural Parsing Layer (Days 4–7)

### Deliverables
- `StructuralParsingService` (wraps `opendataloader-pdf`)
- `OdlElement` and `StructuralParse` dataclasses
- S3 caching mechanism for ODL parse output by PDF content hash (`SHA-256`)
- Golden-file snapshot test suite on 20 sample resumes (1-column, 2-column, table-based, Canva-style)
- ODL JVM warm-up logic during worker container startup

### Verification Gate
- All 20 golden-file snapshot tests pass cleanly.
- ODL output is cached in S3 (second run of the same PDF skips ODL parsing).
- JVM remains warm between requests without cold-start spikes.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 2 until ODL integration is stable and cached.

---

## Phase 2: Deterministic Extraction Engine (Days 8–14)

### Deliverables
- `SectionRouter` (maps ODL headers to canonical resume sections)
- Ported V1 parsers: `contact_parser`, `experience_parser`, `education_parser`, `skills_parser`
- `ExtractedField` model with confidence scores (`0.0–1.0`) and provenance tags
- `DeterministicExtractionService` (returns `ExtractionResult` + list of `UnresolvedChunk`)
- Field-extraction F1 evaluation script on a 100-resume benchmark sample

### Verification Gate
- Field-extraction $F_1 \ge \text{V1 benchmark}$ on 100-resume sample.
- Provenance tag is `deterministic` for $\ge 85\%$ of extracted fields across the sample.
- `UnresolvedChunk` list is correctly populated for the remaining `~15%`.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 3 until deterministic engine matches or beats V1 on clean input.

---

## Phase 3: LLM Fallback (Days 15–18)

### Deliverables
- `NovaFallbackService` (Bedrock Converse API, tool-use constrained decoding)
- `RedisBatchBuffer` (accumulates `UnresolvedChunk` items by count/time threshold)
- `FallbackRecord` database persistence
- Field merge logic: Nova values **NEVER** overwrite deterministic-resolved fields
- Escalation path: Nova Micro $\rightarrow$ Nova Lite when confidence `< 0.5`

### Verification Gate
- Batched call processes 10 unresolved chunks in a single Bedrock invocation.
- Nova populates $\ge 60\%$ of unresolved fields with confidence $\ge 0.7$.
- `nova_fields_used` metric count is accurate in persisted `ExtractionResult`.
- Zero fields resolved by the deterministic engine are overwritten by Nova.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 4 until fallback closes the gap on unresolved fields.

---

## Phase 4: JD Scoring Engine (Days 19–24)

### Deliverables
- `BM25SkillScorer` with fixed reference-corpus IDF table (`registries/idf.pkl`)
- Database-backed `SkillGraph` (ported from V1 `skill_graph.json`)
- `ExperienceScorer`, `EducationScorer`, `KnockoutEvaluator`
- `EmbeddingTiebreaker` (conditional, ambiguous score band only)
- `ScoringService` orchestrator
- Regression test suite on V1 benchmark corpus (3,856 resumes)

### Verification Gate
- MRR and NDCG metrics on the 3,856-resume benchmark $\ge \text{V1}$.
- Domain classification accuracy $\ge 97\%$.
- Single-resume candidate scoring is 100% deterministic regardless of pool size.
- Semantic tiebreaker fires on $< 10\%$ of candidates.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 5 until candidate scoring does not regress vs V1.

---

## Phase 5: ATS Engine (Days 25–28)

### Deliverables
- `AtsScoringService` (standalone, zero Job/Scoring context dependencies)
- 5 Signal Evaluators: `TwoColumnLayoutEvaluator`, `HiddenTextEvaluator`, `TableAsLayoutEvaluator`, `ParseabilityEvaluator`, `ContactPresenceEvaluator`
- `AtsResult` model with detailed warning flags and actionable fix suggestions
- Standalone `/api/v2/ats-check` endpoint (unauthenticated, IP-rate-limited, zero DB persistence)
- 50 hand-labeled resumes with human ATS baseline scores

### Verification Gate
- ATS scores within $\pm 10$ points of human labels on 50-resume sample.
- Identical input yields identical output across 100 iterations (100% determinism).
- `/api/v2/ats-check` endpoint returns in $< 5\text{ seconds}$.
- ATS score is visible in recruiter workspace alongside JD score.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 6 until ATS engine is deterministic and accurate.

---

## Phase 6: API & WebSocket Layer (Days 29–33)

### Deliverables
- `/api/v2/jobs` CRUD REST endpoints
- `/api/v2/jobs/{id}/resumes` upload endpoint (presigned S3 URLs)
- `/api/v2/jobs/{id}/candidates` list endpoint with filtering and cursor pagination
- `/api/v2/jobs/{id}/candidates/{id}` candidate detail endpoint
- `/api/v2/jobs/{id}/candidates/export` CSV export endpoint
- WebSocket endpoint `/ws/jobs/{job_id}` supporting `candidate_ready`, `candidate_partial`, `candidate_failed`, and `processing_complete`
- JWT authentication middleware

### Verification Gate
- All error responses adhere strictly to RFC 7807 problem details format.
- WebSocket pushes `candidate_partial` message when JD score finishes before ATS computation.
- CSV export generates complete score breakdowns and candidate flags.
- 3 concurrent recruiter users upload batches simultaneously without service degradation.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 7 until API is complete and load-tested.

---

## Phase 7: Frontend (Days 34–40)

### Deliverables
- Three-panel recruiter dashboard (Job Setup | Candidate List | Candidate Detail)
- Scoring weight sliders with Zustand derived selector for instant client-side recomputation
- Inline ATS score display alongside composite JD score
- Standalone ATS checker view (`/ats-checker`)
- Real-time candidate list updates via WebSocket integration
- TanStack Query for frontend API caching and state management

### Verification Gate
- Weight recomputation executes in $< 200\text{ms}$ for 100 candidates.
- Real-time candidate list updates stream seamlessly via WebSockets.
- ATS checker page works unauthenticated for public users.
- All API error states are handled gracefully in UI notifications.

> [!CAUTION]
> **Prerequisite:** Cannot proceed to Phase 8 until frontend is functional and responsive.

---

## Phase 8: Production Hardening (Days 41–45)

### Deliverables
- CloudWatch metric alarms: Nova fallback rate `> 20%`, ATS latency P95 `> 5s`, queue depth `> 50`
- PII redaction verification across all structured application logs
- Upload file validation using magic-byte headers
- Redis token-bucket rate limiting on `/api/v2/ats-check`
- GDPR data deletion endpoint (`DELETE /api/v2/jobs/{id}`)
- Full pipeline load test: 20-resume batch in $< 5\text{ minutes}$

### Verification Gate
- All NFRs met (see [projectrequirement.md](file:///d:/resume_ranker/projectrequirement.md#2-non-functional-requirements)).
- Zero PII found in CloudWatch logs.
- Load test completes under target thresholds.
- Nova fallback rate remains $< 15\%$ on production benchmark sample.

> [!IMPORTANT]
> **Final Sign-off:** Cannot proceed to production launch until all NFRs are verified and load testing passes cleanly.
