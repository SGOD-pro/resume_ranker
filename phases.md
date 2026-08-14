# phases.md — Resume Ranker V2
> Strict implementation milestones. No phase begins until the prior is verified. Rev 6.
> Rev 6 changelog: added Phase 6 (Concurrent Extraction), Phase 7 (ATS Scoring), Phase 8 (SSE Streaming Extraction), Phase 9 (Ground-Truth Extraction Audit) after Phase 4/5 close-out. See `benchmark_methodology.md` for how "done" is measured — a single 200-PDF run is NOT sufficient evidence for any gate below. **Phase 9 is a hard prerequisite before trusting any extraction-accuracy number cited elsewhere in this doc or in `tests/benchmark_v4/report.md` — run it before or in parallel with Phase 6, it does not depend on Phase 6/7/8 code.**

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

---

## Phase 6: Concurrent Extraction (ThreadPoolExecutor + Latency Budget)
**Goal:** Cut wall-clock extraction time for multi-resume uploads without changing per-PDF extraction correctness. This phase touches concurrency and instrumentation ONLY — no changes to `PDFPipelineV3`, `CandidateScorer`, or any parser logic. If a fix requires touching parser logic, stop and open a separate scoped fix, don't fold it in here.

**Why this phase exists, stated honestly:** the current `_extraction_event_stream` in `jobs.py` already launches `asyncio.to_thread` per document and awaits a queue — so naive concurrency already exists. What's missing is (a) a bounded worker pool so 500-resume uploads don't spawn 500 threads and OOM the Lambda, (b) per-stage timing instrumentation so "faster" is a measured claim not a vibe, and (c) a documented latency budget tied to the Lambda timeout (120s per `template.yaml` Globals). Don't let an agent claim a speedup without a before/after number from the SAME machine, SAME PDF set, SAME cold/warm state.

- Add `MAX_CONCURRENT_EXTRACTIONS` env var (default 8, matches the benchmark's existing 8-thread pattern in `tests/benchmark_v4/main.py`). Bound `asyncio.to_thread` fan-out in `_extraction_event_stream` with an `asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)` — do not remove the existing per-document error isolation (one failing PDF must not cancel the batch).
- Add `StageTiming` capture per document: `download_s`, `pymupdf_s`, `odl_s` (if triggered), `nova_s` (if triggered), `scoring_s`, `total_s`. Store on the DynamoDB document item as a nested map, not a new table.
- Add a `/jobs/{id}/extraction-metrics` GET endpoint returning aggregate p50/p95/max per stage across the job's documents — this is what proves the speedup, not a changelog claim.
- Update `create_tables.py` / document model if new attributes require schema notes (DynamoDB is schemaless per-item, but document it in `document.py`'s docstring).
- **Gate:** Run the SAME 200-PDF corpus locally three times — once at `MAX_CONCURRENT_EXTRACTIONS=1` (baseline), once at `=8`, once at `=16`. Record wall-clock and peak RSS for all three. The PR is rejected if:
  - the p95 per-PDF latency in the metrics endpoint doesn't match the observed wall-clock math (concurrency_factor × wall_clock ≈ sum of per-PDF times, within 15%)
  - peak memory at `=16` exceeds the Lambda's configured `MemorySize` (1024MB in `template.yaml`) by more than 20% headroom
  - any single document's error causes the batch's other documents to silently disappear from results (regression test against the existing per-document try/except in `_extract_one`)
  - the claimed speedup number in the PR description isn't backed by the metrics endpoint output pasted into the PR, not just "it was faster"

## Phase 7: ATS Scoring — Logic + UI
**Goal:** Add an ATS-compatibility score (separate from the JD-match `final_score`) that tells a candidate/recruiter "would a real ATS parser choke on this PDF's layout." This is NOT the same signal as `extraction_quality` — extraction_quality measures whether OUR pipeline extracted well; ats_score measures whether the PDF's structure itself is ATS-hostile (multi-column with no reading-order metadata, text-in-images, tables-as-layout, missing standard section headers). Conflating these two in one number is the #1 way this phase goes wrong — keep them as two distinct fields.

**Backend:**
- New `AtsScoringService` in `backend/src/ranking/ats_scorer.py`. Deterministic, no LLM. Inputs: the `DocumentStructure` object already produced by `LayoutAwarePDFExtractor` (you already have `layout_type`, `classified_lines`, column detection — reuse it, don't re-derive).
- Score components (all bbox/structure-derived, each 0-100, weighted):
  - `column_penalty`: severe penalty if `layout_type == 'two_column'` or `'header_sidebar_main'` (most ATS parsers read left-to-right ignoring columns, scrambling content)
  - `table_penalty`: penalty if `_detect_table_layout()` (already exists on `DocumentStructure`) returns true
  - `section_header_coverage`: reward for canonical section headers detected via `section_registry.resolve()` — reuse the existing `sections_found`/`sections_missing` telemetry already computed in `pipeline.py`, don't recompute
  - `font_consistency`: penalty for excessive font-size variance in body text (signals graphics-heavy templates)
  - `text_extractability`: directly reuse `text_quality_score` and `semantic_quality_score` already computed in `pipeline.py` metadata — do not reimplement corruption detection, it already exists in `quality_scoring.py`
- Add `ats_score: float` and `ats_breakdown: Dict[str, float]` and `ats_flags: List[str]` (human-readable: "Two-column layout detected — most ATS systems read left-to-right and may scramble your content") to `ScoredCandidate` in `schemas/scoring.py`.
- Wire into `CandidateScorer._score_candidate` — compute once per candidate, it must NOT affect `final_score` or ranking order. This is informational only until a future phase decides otherwise (explicit non-goal, don't let an agent quietly fold it into the weighted formula).
- Standalone endpoint `POST /jobs/{id}/resumes/{doc_id}/ats-check` for on-demand re-check without a full rescore.

**Frontend:**
- New `ATSScoreSection.tsx` component, same visual pattern as `MatchScoreSection.tsx` (score bar + breakdown), placed in `CandidateDetailPanel.tsx` between `MatchScoreSection` and `SkillBreakdown`.
- Render `ats_flags` as a list, same visual treatment as `FlagsSection.tsx` (reuse the warning/info icon pattern, don't invent a new one).
- Add `ats_score` and `ats_flags` to the `Candidate` type in `store/types.ts`, and to `mapScoredCandidate.ts`.
- **Gate:** For a known ATS-hostile PDF (two-column, no section headers) `ats_score` must be materially lower (>25 points) than a known ATS-friendly PDF (single column, clear headers) from the same benchmark corpus — pick 3 of each from `backend/tests/benchmark_v4/resumes/`, name them explicitly in the PR, show before/after scores. `final_score` and `rank` for those 6 candidates must be byte-identical before and after this phase (regression proof that ATS scoring doesn't leak into ranking).

## Phase 8: SSE Streaming for Extraction — Hardening
**Goal:** The SSE extraction endpoint already exists (`GET /jobs/{job_id}/extract` in `jobs.py`, wired since Phase 2). This phase is NOT "add SSE" — it's closing the gaps in the existing implementation: no reconnect/resume support, no per-stage progress (only per-document), and no backpressure signal to the frontend when `MAX_CONCURRENT_EXTRACTIONS` throttling (Phase 6) causes documents to queue.

- Extend the `progress` SSE event payload with `stage: str` (`"downloading" | "parsing" | "scoring"`) sourced from the Phase 6 `StageTiming` capture — the frontend currently only shows "Extracting resume data…" as a static string in `CenterPanelLoader.tsx`; it should be able to show which stage is active for the in-flight document.
- Add a `queued` event type for documents waiting on the Phase 6 semaphore, distinct from `progress`, so the frontend can show "12 queued, 3 processing" instead of looking stalled.
- Reconnection: if the EventSource in `api.ts`'s `startExtraction` drops, the existing frontend retry logic in `AnalyzeButton.tsx` (`MAX_SSE_RETRIES = 3`) reconnects but currently has no way to resume mid-batch — it just gets whatever events fire after reconnect, potentially missing documents that completed while disconnected. Fix: on reconnect, the backend SSE endpoint checks DynamoDB document statuses first and emits synthetic `progress` events for any documents that completed while the client was disconnected, before resuming live streaming.
- **Gate:** Simulate a disconnect (kill the EventSource client-side mid-batch via devtools or a test harness) on a 20-document batch where 8 have completed. On reconnect, the frontend's progress counter must show 8/20 immediately (not 0/20), and the final completed count must equal 20 with no duplicate DynamoDB writes (verify via `version` field — no unexpected version-conflict retries in logs).

## Phase 9: Ground-Truth Extraction Audit (Independent PDF Verification)
**Goal:** Answer, with real evidence instead of a self-reported log, whether the name/email/phone/skills extraction rates in the existing V3/V7 benchmark reports are actually accurate — or whether the pipeline has been consistently and silently blind to content that's plainly visible in the PDFs. This phase produces NO code changes to extraction logic by itself. It produces an audit report. Any fixes it uncovers become separate, scoped follow-up phases — do not let this phase balloon into "also fix everything it finds," per the existing project rule that hypothesis-driven fixes require a document-level diff first, which is exactly what this phase generates.

**This phase exists because of four specific unresolved problems, stated plainly, not softened:**
1. Name extraction sits at 74.5% in the last full report. Nothing has ever confirmed whether that's because 25.5% of PDFs genuinely lack a parseable name, or because the extraction regex/heuristics are missing names that are sitting right there in the text.
2. Email (68%) and phone (70%) have the same problem — no one has verified these against the source PDFs, only against the pipeline's own claims about itself.
3. The Nova/Bedrock LLM fallback path has n=1 real-world validation (1 of 200 PDFs in the V3 corpus). That is not a sample size that supports any claim about whether the fallback works.
4. This project has a documented history (see `mamori.md` / prior V1 incident) of coding-agent-produced reports containing fabricated justifications and internally-consistent-but-wrong summary numbers. A benchmark number that was never checked against ground truth is exactly the kind of number that pattern produces, even without any bad intent — it's a structural blind spot, not a dishonesty problem.

- Follow `benchmark_methodology.md`'s "Ground-truth PDF audit" procedure exactly: draw a fresh N≥50 random sample (new seed, not the existing 200-PDF set), and for each PDF the agent must independently read the raw PDF (via rendered page image or independent text extraction, NOT via `PDFPipelineV3`'s own output) and record what a human would see for name/email/phone, before comparing against what the pipeline extracted.
- Classify every mismatch as `TRUE_MISS` / `TRUE_ABSENT` / `SCANNED_UNREADABLE` per the methodology doc — a flat "accuracy %" that doesn't distinguish these is not acceptable output for this phase.
- Separately audit the Nova fallback path against ≥15 adversarial/malformed PDFs specifically chosen to trigger it, per the methodology doc's stricter procedure for that path.
- Produce a single audit report (`backend/tests/benchmark_v4/GROUND_TRUTH_AUDIT.md`) listing every sampled PDF, the human-read ground truth, the pipeline's extraction, and the classification — this is the raw evidence artifact, not a summary.
- **Gate:** The audit report exists with all 50+15 PDFs individually listed (not aggregated-only). For name/email/phone, the TRUE_MISS rate (extractable-but-missed, excluding TRUE_ABSENT and SCANNED_UNREADABLE) is reported as its own explicit number, separate from the raw 74.5%/68%/70% figures. If TRUE_MISS rate for any field exceeds 10% of the extractable PDFs, that is flagged as requiring a follow-up scoped fix phase — this phase does not attempt the fix itself. If the Nova fallback's accuracy on the 15-PDF adversarial set is below 70%, that's flagged the same way, not silently accepted.

---

## Non-negotiable process notes for Phases 6–9 (carried over from prior incident)

- **No phase report is accepted without raw per-document evidence.** A summary table ("92% success rate") is not suflight itself — the agent must also produce the underlying per-document CSV/JSON and you (or I, on request) spot-check a sample against it before the gate is marked passed. This project has a documented history of agents fabricating summary numbers that don't match raw data — see `userMemories` "Never trust agent summary tables."
- **Regressions found in Phase 6/7/8 must be diffed at the document level before any regex/logic change is proposed.** Hypothesis-driven fixes ("I think it's the column detection") are rejected until backed by a diff of which specific PDFs regressed.
- **A single benchmark run is not evidence.** See `benchmark_methodology.md` — any claim of "X% success" or "Y speedup" must cite N runs, sample size, and corpus composition, or it doesn't count as a gate-passing result.