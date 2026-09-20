# SWYRA Sortlist v2 — Pre-Release Factual Audit

> **Date:** 2026-09-20
> **Branch:** `v2.1`
> **Auditor:** Principal Engineer (automated)
> **Status:** BLOCKING — must be resolved before public release

---

## 1. Implemented Behavior vs Planned-Only Behavior

### ✅ Actually Implemented & Working

| Feature | Location | Status |
|---------|----------|--------|
| FastAPI backend with 7 API routes | `src/api/routes/jobs_v2.py`, `health.py` | Working |
| PDF upload with 10MB limit, SHA-256 dedup | `jobs_v2.py` POST `/resumes` | Working |
| SSE extraction progress streaming | `jobs_v2.py` GET `/extract` | Working |
| V2 Extraction Pipeline (PyMuPDF → ODL → Regex → Nova) | `src/extraction/extraction_pipeline.py` | Working |
| Structural quality gate (x-clustering, reading order) | `src/extraction/structural_parsing_service.py` | Working |
| ODL Lambda fallback for multi-column PDFs | `src/extraction/odl_client.py` | Working (requires AWS) |
| Nova LLM fallback for missing critical fields | `src/extraction/fallback/nova_service.py` | Working (requires AWS Bedrock) |
| 3-phase candidate scoring (knockout, scoring, ranking) | `src/ranking/scorer.py` | Working |
| BM25 skill scoring with inference weights | `src/ranking/bm25_scorer.py` | Working |
| Graph-based skill inference (200+ nodes) | `src/ranking/skill_inference.py` | Working |
| Domain classification (13 domains, 10 subdomains) | `src/ranking/domain_classifier.py` | Working |
| Domain proximity penalty matrix | `src/registries/domain_proximity.json` | Working |
| ATS scoring (bounding box overlap analysis) | `src/ats/ats_scoring_service.py` | Working |
| B2B ATS checker endpoint | `src/ats/b2b_ats_scorer.py` | Working (has production `assert` bug) |
| DynamoDB single-table design (Jobs, Documents, Scoring) | `src/infrastructure/models/` | Working |
| S3 storage for PDFs, extracted JSON, scoring JSON | `src/infrastructure/storage/` | Working |
| React 3-panel recruiter UI | `frontend/src/` | Working |
| Client-side weight recalculation | `CandidateListPanel.tsx`, `CandidateDetailPanel.tsx` | Working |
| ATS Checker page with PDF viewer + bounding boxes | `frontend/src/pages/AtsCheckerPage.tsx` | Working |
| Zustand state management (3 stores) | `frontend/src/store/` | Working |
| Backend health gate with cold-start detection | `BackendHealthGate.tsx` | Working |
| Resume drag-and-drop upload with progress tracking | `ResumeUploadZone.tsx` | Working |

### ❌ Claimed in Documentation But NOT Implemented

| Claimed Feature | Where Claimed | Reality |
|----------------|---------------|---------|
| Authentication / Authorization | `projectrequirement.md` HC-01 says "No auth" (accepted) | **No auth exists. Every endpoint is public. PII is exposed.** |
| Fixed reference-corpus BM25 IDF (`registries/idf.pkl`) | `projectrequirement.md` HC-07, `rules.md` R-10, `decision.md` ADR-06 | **File does not exist.** Dynamic pool IDF is still used in `bm25_scorer.py` |
| DynamoDB GSIs (GSI1 score buckets, GSI2 skills, GSI3 status) | `design.md` §1, `projectrequirement.md` FR-14 | **Not implemented.** Single table with PK/SK queries only |
| SQS-based async extraction (DocumentQueue, OdlBatchQueue) | `architecture.md`, `projectrequirement.md` FR-02 | **Not implemented.** Uses FastAPI `BackgroundTasks` only |
| Lambda A / Lambda B split deployment | `architecture.md`, `phases.md` Phase 4 | **Not implemented.** Single FastAPI process |
| SSE reconnect-and-resume from DynamoDB state | `architecture.md` §6b, `phases.md` Phase 8 | **Not implemented** |
| Phase 6: Concurrent extraction with ThreadPoolExecutor | `phases.md` | **Not started** |
| Phase 9: Ground-truth extraction audit (N≥50) | `phases.md`, `benchmark_methodology.md` | **Not started** |
| Client-side weight PATCH without re-scoring | `rules.md` R-17, `boundaries.md` | **Not implemented.** Frontend re-scores via POST |
| CSV export | `CandidateListFooter.tsx` | **Button exists, no handler** |
| Upload JD PDF | `JobDescriptionSection.tsx` | **Button exists, no handler** |
| Candidate actions persistence (Shortlist/Reject/Notes) | `CandidateActions.tsx` | **Local Zustand only, lost on refresh, no API** |
| Settings / Help dialogs | `AppHeader.tsx` | **Buttons exist, no handlers** |
| TanStack Query for GET requests | `boundaries.md`, `AGENT.md` | **Not integrated.** All fetches via custom `apiFetch` |
| Playwright E2E tests passing | `memory.md` | **Not verified in current branch — no Playwright config found** |

### ⚠️ Partially Implemented / Degraded

| Feature | Issue |
|---------|-------|
| Quality threshold | Code uses `0.90` (`structural_parsing_service.py`), docs conflict between `0.90` and `0.70` |
| B2B ATS bounding boxes | `B2BAtsScorer` declares `BoundingBox` class but always returns `[]` |
| Nova model ID mismatch | Docstring says "Nova Micro", code invokes `apac.amazon.nova-lite-v1:0` (Nova Lite) |
| `ExtractionService` | Instantiated as `LazyProxy` in routes but never called; dead code |
| `PDFPipelineV3` (2,538 lines) | Legacy V1 pipeline still in codebase, not used by V2 API routes |
| SSE extraction event UI | `AnalyzeButton.tsx` onEvent callback is a no-op |

---

## 2. Documentation Contradictions

### CRITICAL — Directly Conflicting Specifications

| # | Subject | Source A | Source B | Conflict |
|---|---------|----------|----------|----------|
| 1 | **Quality gate threshold** | `projectrequirement.md` FR-06, `project.md`, `architecture.md`, `phases.md`, `memory.md`: **< 0.90** | `design.md` §2, `decision.md` ADR-03: **< 0.70** | Code uses `0.90`. Five docs say 0.90, two say 0.70. |
| 2 | **BM25 IDF source** | `README.md`, `mamori.md`: Dynamic pool IDF | `projectrequirement.md` HC-07, `rules.md` R-10, `decision.md` ADR-06: Fixed corpus `idf.pkl` | **Code uses dynamic pool IDF.** `idf.pkl` does not exist. |
| 3 | **Backend persistence** | `docs/02_ARCHITECTURE_DEEP_DIVE.md`, `docs/05_API_LAYER.md`: In-memory `_jobs` dict, local filesystem | `project_report.md`, `mamori.md`, current code: AWS DynamoDB + S3 | **Code uses DynamoDB + S3** (V2 migrated). Old docs not updated. |
| 4 | **Lambda packaging** | `projectrequirement.md` HC-04: Lambda A = Docker container | `architecture.md` §2: Lambda A = Python ZIP, ODL = separate ECR container | Not implemented — single FastAPI process |
| 5 | **ODL local execution** | `architecture.md`, `rules.md` R-01: Local Bypass imports `odl/main.py` | `projectrequirement.md` NFR-01, `memory.md`: Hits real AWS Lambda | **Code hits real AWS Lambda** via `boto3.invoke` |
| 6 | **Local storage** | `projectrequirement.md`: "floci-backed" | `rules.md` R-01, `memory.md`: "LocalStack" | Different names for same concept |
| 7 | **Pipeline architecture** | `README.md`: `PDFPipelineV3`, dual-path, no LLM | Current code: `ExtractionPipeline`, tiered, with Nova LLM | README is stale V1 documentation |
| 8 | **Candidate data schema** | `mamori.md`, `PDFPipelineV3`: Nested `personal_info.name` | `ExtractionPipeline`, `memory.md`: Flat `name`, `email` | Scorer has compatibility fallback |
| 9 | **Nova trigger scope** | `projectrequirement.md` FR-09: Any unresolved chunk | `decision.md` ADR-11: Critical fields only | Code follows ADR-11 |
| 10 | **Deleted files still documented** | `docs/02`, `docs/13`: Reference `ranking_service.py`, `document_service.py`, `section_assembly.py`, `benchmark_v3/` | `docs/00_CLEANUP_RECOMMENDATIONS.md`: Confirms deletion | Files deleted but docs not updated |

### MODERATE — Stale Numbers

| Subject | Old Value | Current Value |
|---------|-----------|---------------|
| Skill aliases | 70+ (`IMPLEMENTATION.md`) → 90+ (`SCORING_ARCHITECTURE.md`) | 118 (`skill_registry.py`) |
| Section aliases | 140+ (`IMPLEMENTATION.md`) | 200+ (`section_registry.py`) |
| Benchmark corpus | 20 resumes / 4 JDs (`IMPLEMENTATION.md`) | 3,856 resumes / 20 JDs (V4 benchmark) |
| File paths | `/home/swyra/Desktop/resume-ranking/...` | `/home/swyra/projects/resume_ranker/` |

---

## 3. Security & Privacy Risks

### P0 — CRITICAL

| Risk | Detail | Impact |
|------|--------|--------|
| **No authentication** | Zero auth on all endpoints. No JWT, no API keys, no sessions. | Anyone with network access can read all candidate PII, upload files, trigger compute |
| **No authorization / tenant isolation** | No user or organization model. Jobs accessible by anyone with UUID | Complete data exposure between users |
| **Tracked `.env` file** | `.env` is committed to git with database URLs and AWS credentials (even if test values) | Credential leak risk; `.gitignore` does not exclude `.env` |
| **IDOR vulnerability** | Job/document IDs are UUIDs but not scoped to any user/org | Enumeration or sharing of UUID exposes all data |
| **No rate limiting** | No throttling on upload, extraction, or ATS-check endpoints | Resource exhaustion, cost amplification |
| **CORS wildcard in non-prod** | `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True` | Overly permissive cross-origin access |
| **Untrusted PDF processing** | PyMuPDF processes untrusted PDFs in-process with no sandbox | Buffer overflow, memory safety exploits via malformed PDFs |
| **PII stored unencrypted** | Candidate names, emails, phones stored in plain text in S3 JSON and DynamoDB | Privacy violation, no encryption at application layer |

### P1 — HIGH

| Risk | Detail |
|------|--------|
| **No file size validation before memory read** | `jobs_v2.py` reads full file bytes before checking size |
| **Unbounded `_extraction_locks` dict** | Memory leak: `_extraction_locks = {}` grows indefinitely |
| **Production `assert` in B2B scorer** | `b2b_ats_scorer.py` line 123: `assert score == ...` can crash endpoint |
| **Direct S3 client access in routes** | `/ats-check` route accesses `_storage._bucket` and `_storage._client` private attrs |
| **Hardcoded `localhost:8000`** | `AtsCheckerPage.tsx` line 45 bypasses API layer with hardcoded URL |
| **External CDN for PDF worker** | `PdfViewer.tsx` loads JS from `unpkg.com` — supply chain risk |
| **Debug console.group in production** | `mapScoredCandidate.ts`, `AnalyzeButton.tsx` log full candidate data to browser console |
| **Lambda function name hardcoded** | `odl_client.py`: `"odl-parser-lambda-prod"` |
| **AWS profile names hardcoded** | `aws.py`: requires `"aws"` and `"local"` profile names |

---

## 4. Deprecated Code & Files

### Should Be Removed or Archived

| File/Directory | Reason |
|----------------|--------|
| `backend/deploy/` (entire directory, 274 Python files) | Full duplicate of `backend/src/` with stale code |
| `backend/src/core/pipeline.py` (2,538 lines) | Legacy `PDFPipelineV3` — not used by V2 API routes |
| `backend/src/services/extraction_service.py` | Dead code — V2 uses `ExtractionPipeline` directly |
| `backend/src/ranking/ats_scorer.py` | V1 ATS scorer tied to `DocumentStructure` — V2 uses `src/ats/` |
| `backend/src/core/lazy_proxy.py` + `backend/lazy_proxy_test.py` | `LazyProxy` instantiated but never called |
| `backend/scripts/` (6 files) | Benchmark/test scripts from V1 era |
| `backend/test_ats.py`, `backend/test_s3.py` | Root-level test stubs |
| `backend/deploy/.aws-sam/` | Build artifacts that should not be in source control |
| Root planning docs: `prmopt.md`, `one_shot_doc.md`, `resume.md`, `tests.md` | Agent prompt templates, not product documentation |
| `.env` | Should not be tracked; replace with `.env.example` |

### Files with Stale References to Deleted Code

| File | References |
|------|-----------|
| `docs/02_ARCHITECTURE_DEEP_DIVE.md` | `ranking_service.py`, `document_service.py`, `section_assembly.py` |
| `docs/13_FILE_MAP.md` | Same + `benchmark_v3/`, wrong file paths |
| `backend/docs/PROJECT_STRUCTURE.md` | Missing modern ranking modules |
| `backend/docs/SCORING_ARCHITECTURE.md` | Missing skill inference, domain classifier |
| `backend/docs/IMPLEMENTATION.md` | Pre-dates all V9 improvements |

---

## 5. Claims That Must Be Removed from Public Documentation

> These claims appear in `README.md` and/or `docs/project_report.md` and MUST NOT be published until independently validated.

### Unvalidated Metrics

| Claim | Source | Why It Must Be Removed |
|-------|--------|----------------------|
| "97.8% domain classification accuracy" | `README.md`, `project_report.md` | Single-run self-report on 47.5% engineering-skewed corpus. No independent validation. |
| "86/100 Production Ready" | `README.md`, `project_report.md` | Self-assessed benchmark score. No external review. |
| "1.5% true false-positive rate (only 3 cases)" | `README.md`, `project_report.md` | Single run. Definition of "false positive" is self-defined. |
| "100% knockout reliability" | `README.md`, `project_report.md` | Not independently verified. |
| "72/100 extraction quality" | `README.md`, `project_report.md` | Self-reported. `benchmark_methodology.md` explicitly states extraction rates have never been human-verified. |
| "<200ms per candidate score" | `project_report.md` | No published benchmark artifact with timing data. |
| "3,856 resumes across 20 JDs" | `README.md`, `project_report.md` | Corpus exists but composition (47.5% engineering) makes cross-domain claims invalid. |
| "5,000+ resumes" | `one_shot_doc.md` | Inflated number — actual benchmark corpus is 3,856. |

### False Architectural Claims

| Claim | Source | Reality |
|-------|--------|---------|
| "Without requiring heavy machine learning models or GPU resources" | `README.md` | V2 uses Amazon Bedrock Nova LLM for fallback |
| "Avoids expensive GPU/LLM tokens" | `README.md` | Nova calls cost money and are active in production |
| "Production Frontend URL: resume-ranker-virid.vercel.app" | `project_report.md` | Deployed state not verified from this branch |
| "AWS Lambda, API Gateway, DynamoDB, S3 production deployment" | `project_report.md` | Lambda/API Gateway deployment not verified; SAM artifacts stale |
| "Fixed reference-corpus BM25 IDF" | V2 planning docs | `idf.pkl` does not exist; code uses dynamic pool IDF |
| "GSI1, GSI2, GSI3 for efficient filtering" | V2 planning docs | GSIs not implemented |

### Misleading Product Language

| Phrase | Issue | Replacement |
|--------|-------|-------------|
| "AI Resume Screener" | Implies autonomous AI decision-making | "Resume Review Assistant" or "Candidate Review Workspace" |
| "Production Ready" | System has no auth, no tenant isolation | Remove until security baseline met |
| "beat ATS systems" | Nowhere explicitly stated but implied by ATS checker positioning | Add explicit limitations disclaimer |

---

## 6. Fairness Policy Violations in Current Code

| Violation | Location | Detail |
|-----------|----------|--------|
| **Prestige company bonus** | `scorer.py` `_prestige_bonus()` | +2.0 per match from ~100 hardcoded elite companies (FAANG, Goldman Sachs, McKinsey, etc.), capped at +4.0 |
| **Prestigious cert issuer bonus** | `scorer.py` `_cert_bonus()` | +0.25 for certs from MIT, Stanford, Harvard, IIT, Google, AWS, Microsoft |
| **Career gap flagging** | `scorer.py` `_detect_anomalies()` | Flags `GAP` for >180 days between jobs (penalizes caregivers, medical leave, etc.) |
| **Overqualified flag** | `scorer.py` `_detect_anomalies()` | Flags `OVERQUALIFIED` for years > max_years × 1.5 (age proxy) |
| **Hardcoded "good/fair" thresholds** | `mapScoredCandidate.ts` | `≥75 = strong`, `≥50 = good`, `<50 = fair` — not grounded in documented policy |

---

## 7. Architecture Debt Summary

| Item | Severity | Notes |
|------|----------|-------|
| Dual extraction pipelines (V1 `PDFPipelineV3` + V2 `ExtractionPipeline`) | High | 2,538 lines of dead code |
| Dual ATS scorers (`ranking/ats_scorer.py` + `ats/ats_scoring_service.py`) | Medium | V1 scorer unused |
| Full deploy directory duplicate | High | 274 files duplicating src |
| No database migrations | Medium | DynamoDB schema changes are manual |
| No CI/CD pipeline visible | Medium | No GitHub Actions, no `check_imports.py` found |
| Frontend debug logging in production | Low | `console.group` calls throughout |
| Health endpoint typo | Low | "Resuem ranker Backend is healthy" |

---

## 8. Audit Conclusion

**This codebase cannot be published as a public v2 release in its current state.**

Critical blockers:
1. Zero authentication exposes candidate PII to any network user
2. Fairness violations (prestige bonuses, gap penalties) contradict the stated product positioning
3. Public documentation contains unvalidated metrics and false architectural claims
4. `.env` with credentials is tracked in git
5. 3,000+ lines of dead code and a full deploy directory duplicate create maintenance burden

The v2-release specification documents that follow define the path to resolving these issues.
