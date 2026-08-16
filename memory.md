# memory.md — Resume Ranker V2
> Context window and state tracking for future sessions.
> Last updated: 2026-08-17

---

## 1. Project State

- **Architecture Version:** V2 — Fully migrated from V1 (PDFPipelineV3) to the new ExtractionPipeline.
- **Active Branch:** `new-changes`
- **Active Phase:** Phase 5 complete (frontend polish). Phase 6 (Concurrent Extraction / latency budget) is next but NOT started.
- **Phases 1–5 Status:** ✅ All gates passed. E2E Playwright tests pass end-to-end.
- **Deployment:** LocalStack (DynamoDB + S3) + real AWS (Bedrock Nova Micro + ODL Lambda).

---

## 2. What "V2 Migration" Actually Means (Critical for New Sessions)

### Naming Confusion — Read This First

There are **two pipeline version numbers** that are intentionally decoupled:

| Label | What it is | Used where |
|-------|-----------|-----------|
| **API v2** | Public API prefix `/api/v2/jobs` | `jobs_v2.py`, frontend `api.ts` |
| **ExtractionPipeline** | The NEW extraction class (`src/extraction/extraction_pipeline.py`) | Used exclusively by all `/api/v2/jobs` traffic |
| **PDFPipelineV3** | The OLD third-iteration internal pipeline (`src/core/pipeline.py`) | Still exists but only used by `ExtractionService` (legacy path, not on hot path) |

**Do NOT confuse `PDFPipelineV3` (internal V3 iteration) with a `v3` API.** The public API has only v2. The `V3` in `PDFPipelineV3` is the third internal rewrite of V1 parsing logic, unrelated to public API versioning.

### V1 vs V2 Field Format — Root Cause of All "Unknown Name" Bugs

| Pipeline | Output format |
|----------|--------------|
| `PDFPipelineV3` (old) | Nested: `{ "personal_info": { "name": ..., "email": ... }, "skills": [...] }` |
| `ExtractionPipeline` (new) | **Flat**: `{ "name": ..., "email": ..., "phone": ..., "skills": [...] }` |

`CandidateScorer._score_candidate()` was updated to read **both formats** (flat first, nested fallback):
```python
pi = candidate.get('personal_info', {}) or {}
name = candidate.get('name') or pi.get('name') or 'Unknown'
email = candidate.get('email') or pi.get('email') or ''
```

---

## 3. Key Architectural Truths (DO NOT VIOLATE)

1. **No WebSockets.** SSE (`EventSource`) is the only real-time mechanism.
2. **Tiered Extraction.** PyMuPDF quality gate → if score < 0.90, invoke ODL Lambda. ODL is batched per job (one JVM boot amortised, not per document).
3. **Database.** DynamoDB (single-table + GSIs). No Postgres. No `scan()` with FilterExpression.
4. **No Auth.** All endpoints are open.
5. **LLM.** Amazon Nova Micro via Bedrock. `temperature=0`. Used ONLY for extraction field infill (unresolved chunks). Never for scoring or ATS.
6. **Frontend State.** Zustand is source of truth for candidate lists. Weight changes compute **locally via `useMemo`** — zero network requests on slider change.
7. **ODL.** Standalone cloud Lambda (`odl-parser-lambda`). Called via `boto3.invoke`. In local dev, S3/DynamoDB → LocalStack; Bedrock/Lambda → real AWS.
8. **Scorer reads flat fields.** `candidate['name']`, `candidate['email']` — NOT `candidate['personal_info']['name']`. Canonical format post-V2 migration.

---

## 4. Bugs Fixed This Session

### Backend

| Bug | File | Fix |
|-----|------|-----|
| `name = 'Unknown'` for all candidates | `scorer.py` L584 | Scorer read `personal_info.name` (V1 format). V2 pipeline stores flat. Fixed to read flat first, nested fallback. |
| `email`, `phone` always blank | `scorer.py` | Same V1/V2 format mismatch. Fixed. |
| ATS "Images instead of text" false positive | `b2b_ats_scorer.py` | Added pixel-area threshold — only flag images > meaningful area. Small icons/lines/decorators ignored. |
| Startup blocking (8s) on health checks | `app.py` | `check_all()` was synchronous before `yield`. Moved to `asyncio.create_task()` — server ready immediately, health results appear async. |
| LLM fallback not triggered when name missing | `markdown_extraction_service.py` | Added `if not fields["name"]: missing_critical = True` so Nova is invoked when regex name extraction fails. |
| ATS `AtsScoringService` false 0% score | `ats_scoring_service.py` | Fast-path (high quality) PDFs had no bounding box elements. Added `extraction_quality` param — returns 100% if quality >= 0.90. |

### Frontend

| Bug | File | Fix |
|-----|------|-----|
| Clicking candidate → infinite render loop | `candidate-store.ts`, `CandidateDetailPanel.tsx` | `getSelectedCandidate()` called as Zustand selector — returns new object on every render, breaking `getSnapshot` cache. Removed computed methods from store. Now uses stable primitive selectors + `useMemo`. |
| `scoreBreakdown` TypeError on knockout candidates | `candidate-store.ts`, `CandidateDetailPanel.tsx` | Null guard: `const sb = c.scoreBreakdown ?? { skills: 0, experience: 0, keywords: 0, education: 0 }` |
| Upload progress bar jumps 0→100% instantly | `api.ts`, `ResumeUploadZone.tsx` | Changed from single multipart batch to **per-file sequential XHR**. `onFileComplete` fires after server confirms each file — bar ticks accurately. |
| ATS "MISSED: None" shown in alarming red text | `AtsCheckerPage.tsx` | Hide MISSED block entirely when empty. Show muted `✓ No missed sections` instead. |

---

## 5. Current Architecture — Data Flow (V2)

```
User uploads PDFs
    → ResumeUploadZone (one file at a time via uploadSingleFile XHR)
    → POST /api/v2/jobs/{id}/resumes (jobs_v2.py)
    → PDF saved to S3, document record created in DynamoDB (PENDING)
    → BackgroundTask triggers ExtractionPipeline per doc

ExtractionPipeline (src/extraction/extraction_pipeline.py)
    → StructuralParsingService (PyMuPDF quality gate)
        → quality >= 0.90  → fast PyMuPDF text (no JVM)
        → quality <  0.90  → ODL Lambda (one JVM boot per batch window)
    → MarkdownExtractionService (regex parsers: name/email/skills/exp/edu)
    → NovaService (LLM fallback for unresolved chunks, including missing name)
    → Writes FLAT JSON to S3: { name, email, phone, skills, experience, ... }
    → Updates DynamoDB: PARSED

SSE stream (GET /api/v2/jobs/{id}/extract)
    → Polls DynamoDB every 2s
    → Emits progress events to EventSource in frontend

POST /api/v2/jobs/{id}/score
    → Loads flat JSON from S3 for each doc
    → CandidateScorer.rank(jd, candidates) — Phase 1 knockout, Phase 2 multi-signal
    → AtsScoringService.score(elements, extraction_quality) — layout ATS
    → Returns ScoredCandidate[] (flat fields)
    → mapScoredCandidate() maps to frontend Candidate type → Zustand store
```

---

## 6. Frontend Architecture (V2)

- **Framework:** React 18 + Vite + TypeScript
- **State:** Zustand (`candidate-store.ts`, `job-store.ts`, `app-store.ts`)
- **API:** All calls through `src/lib/api.ts` — no raw `fetch()` in components
- **Routing:** React Router — `/` (Dashboard), `/ats-checker` (standalone ATS checker)
- **Upload flow:** `ResumeUploadZone` → `api.uploadResumes()` (per-file sequential) → `onFileComplete` ticks progress bar

### ⚠️ Zustand Anti-Pattern — DO NOT REPEAT

```ts
// ❌ INFINITE LOOP — returns new object reference on every call
const candidate = useCandidateStore((s) => s.getSelectedCandidate());

// ✅ CORRECT — stable primitives + useMemo in the component
const selectedId = useCandidateStore((s) => s.selectedId);
const candidates = useCandidateStore((s) => s.candidates);
const jobWeights = useJobStore((s) => s.job.weights);
const candidate = useMemo(() => {
  const c = candidates.find(c => c.id === selectedId);
  // ... compute dynamicScore from c + jobWeights
  return c ? { ...c, overallScore: dynamicScore } : null;
}, [selectedId, candidates, jobWeights]);
```

Computed functions returning `{ ...spread }` objects must **NEVER** be used as Zustand selectors.
`candidate-store.ts` was cleaned — it now contains only primitive state mutations, no computed selectors.

---

## 7. Remaining Work (Pre-Deploy Checklist)

| Priority | Task | File | Notes |
|----------|------|------|-------|
| 🔴 Pre-deploy | **Remove default JD** | `job-store.ts` | Pre-filled "Senior Data Scientist" JD is for local testing only |
| 🟡 Phase 6 | Concurrent extraction with `asyncio.Semaphore` | `jobs_v2.py` | Not started. See `phases.md` Phase 6 for gate criteria (200-PDF benchmark required) |
| 🟡 Phase 6 | `/jobs/{id}/extraction-metrics` endpoint | `jobs_v2.py` | p50/p95 per stage — proves speedup |
| 🟡 Branding | SWYRA watermark in header | `AppHeader.tsx` | App name: Sortlist, brand: SWYRA |
| 🟡 Branding | "Home" + "ATS Checker" nav links | `AppHeader.tsx` | Not yet implemented |
| 🟡 UI | Themed scrollbars (brutalist) | `index.css` | Not yet implemented |

---

## 8. Key File Map (V2 Hot Path)

```
backend/src/
  api/
    app.py                          # FastAPI app factory — health checks are non-blocking
    routes/jobs_v2.py               # ALL /api/v2/jobs/* routes
  extraction/
    extraction_pipeline.py          # V2 orchestrator (≠ PDFPipelineV3)
    structural_parsing_service.py   # PyMuPDF quality gate + ODL batch
    markdown_extraction_service.py  # Regex parsers — output is FLAT dict
    fallback/nova_service.py        # LLM fallback for unresolved chunks
  ranking/
    scorer.py                       # CandidateScorer — reads FLAT fields
  ats/
    b2b_ats_scorer.py               # ATS checker page scorer
    ats_scoring_service.py          # Resume ranker ATS (layout bbox-based)
  infrastructure/health.py          # DynamoDB + S3 checks (parallel threads)

frontend/src/
  lib/
    api.ts                          # All backend calls — uploadResumes: per-file XHR
    mapScoredCandidate.ts           # Backend ScoredCandidate → frontend Candidate
  store/
    candidate-store.ts              # Zustand — primitive state only, NO computed selectors
    job-store.ts                    # JD config (⚠️ has default JD — REMOVE BEFORE DEPLOY)
    app-store.ts                    # Upload progress, app phase, backend status
  components/
    detail/CandidateDetailPanel.tsx # useMemo for candidate + score computation
    layout/UploadProgressBar.tsx    # Shows "X of Y files" — accurate per-file
    candidates/ResumeUploadZone.tsx # Per-file upload with onFileComplete callback
  pages/
    AtsCheckerPage.tsx              # Standalone ATS checker (/ats-checker)
```

---

## 9. V1 Pitfalls Fixed in V2 (Summary)

| V1 Problem | V2 Fix |
|-----------|--------|
| PyMuPDF scrambles 2-column layouts | Pre-extraction structural quality gate → ODL |
| Dynamic BM25 IDF (non-reproducible) | Fixed reference IDF table |
| Infinite spinner on local dev | FastAPI BackgroundTasks + DynamoDB state polling via SSE |
| All candidates named "Unknown" | Scorer reads flat `fields['name']`, not `personal_info.name` |
| Click crash on knockout candidates | `scoreBreakdown ?? {}` null guard in `useMemo` |
| Upload bar 0→100% instantly | Per-file XHR — progress ticks on server confirmation |
| `getSelectedCandidate()` infinite loop | Removed computed selectors from Zustand store entirely |
