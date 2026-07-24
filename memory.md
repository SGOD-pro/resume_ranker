# memory.md — Resume Ranker V2

> Context window and state tracking for future sessions.

## 1. Project State

### Completed Phases
* Phase 0: Infrastructure Skeleton — Complete. (Postgres + Redis + pgvector up, DynamoDB dead, V2 FastAPI app wired, Alembic migrations initialized).
* Phase 1: Structural Parsing Layer — **Complete**. `StructuralParsingService` (ACL), `OdlElement`/`StructuralParse` dataclasses, S3+InMemory cache, golden fixtures (single_column, two_column, hidden_text), 41/41 tests passing.
* Phase 2: Deterministic Extraction Engine — **Complete**. `DeterministicExtractionService`, V2 Parser Adapters. F1 evaluation script scores 100% deterministic extraction. 83/83 unit tests passing. `ruff` and `mypy` strict type checking verified with zero errors.

### Current Focus
* **Active Phase:** Phase 3: Extraction Fallback (Amazon Nova)
* **Status:**
    * Phase 0 (Infrastructure Skeleton): COMPLETE
    * Phase 1 (Structural Parsing Layer): COMPLETE
    * Phase 2 (Deterministic Extraction Engine): COMPLETE
    * Phase 3 (Extraction Fallback): PENDING
    * Phase 4 (Scoring Engine): PENDING

- **Architecture Version:** Rev 3 (Lambda + SQS)
- **Last Updated:** 2026-07-24

## 2. Key Decisions Made

| Decision | Date | Rationale | ADR |
| :--- | :--- | :--- | :--- |
| **Hybrid extraction (deterministic + Nova fallback)** | 2025-01 | V1 regex wasn't broken; ODL input was | ADR-01 |
| **Amazon Nova Micro/Lite for fallback** | 2025-01 | Cheapest structured extraction; tool-use constrained decoding | ADR-02 |
| **ATS is 100% deterministic (no LLM)** | 2025-01 | LLMs can't reason about bbox coordinates | ADR-03 |
| **Fixed reference-corpus BM25 IDF** | 2025-01 | Dynamic per-pool IDF is non-deterministic | ADR-04 |
| **AWS Lambda with SQS** | 2026-07 | SQS batch windows solve state; Provisioned Concurrency solves JVM cold starts | ADR-05 |
| **Conditional semantic embeddings** | 2025-01 | 95% of resumes don't need it | ADR-06 |
| **Composite score computed at read time** | 2025-01 | Weight changes must be instant | ADR-07 |

## 3. Hard Constraints (Must Hold in Every Session)

> [!WARNING]
>
> 1. **No LLM in ATS scoring. Ever.** It's bbox math only.
> 2. **No single-document LLM calls in batch mode.** Batching is enforced in code.
> 3. **No vendor SDK imports outside ACL classes.** CI enforces this.
> 4. **No dynamic per-pool BM25 IDF.** Fixed reference corpus only.
> 5. **No stored composite scores.** Computed at read time.
> 6. **No weight-change-triggered re-extraction.** Extraction is immutable.
> 7. **No PyMuPDF (`fitz`).** Completely banned in V2.

## 4. Known Pitfalls (From V1)

| Pitfall | How V2 Avoids It |
| :--- | :--- |
| PyMuPDF scrambles multi-column text | ODL handles layout natively |
| Regex fails on scrambled text | Regex runs on clean ODL markdown |
| Dynamic IDF makes scores batch-dependent | Fixed reference-corpus IDF table |
| 864-line `scorer.py` God-class | Split into 6 single-responsibility modules |
| Dual-path arbitration ("run both, pick best") | Deleted. Single path. Root cause fixed. |
| Lambda cold start with ML models | Lambda container image with Provisioned Concurrency |
| Black-box composite scores | Component scores persisted with provenance |

## 5. Metrics to Watch

| Metric | Healthy Range | Alarm Threshold | Action |
| :--- | :--- | :--- | :--- |
| **Nova fallback rate** | 5–15% | \> 20% | Update deterministic dictionaries/regex |
| **ODL extraction time** | 1–3s | \> 5s | Check JVM health, ODL version |
| **ATS scoring time** | \< 100ms | \> 500ms | Check bbox clustering logic |
| **BM25 skill score distribution**| 0.2–0.8 | Bimodal at 0/1 | Check IDF table staleness |
| **Embedding tiebreaker fire rate** | \< 10% | \> 25% | Check skill-graph coverage |
| **WebSocket message latency** | \< 1s | \> 3s | Check Redis pub/sub health |

## 6. File Structure (Target - V1 to V2 Hybrid Integration)

> [!NOTE]
> This structure merges the current V1 repository layout with the V2 architecture target, reusing existing V1 modules (like `contact_parser.py`, `bm25_scorer.py`, `models/`, `repositories/`) under the target V2 domains to avoid repeating code.

```text
resume_ranker/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── websocket.py                     # [V2] WebSocket support
│   │   ├── config/                              # [Current] AWS & Settings
│   │   ├── core/                                # [Current] Pipeline & Output cleaning
│   │   ├── extraction/                          # [V2 Target - renamed from extractors]
│   │   │   ├── structural_parsing_service.py    # [V2] ACL: opendataloader-pdf
│   │   │   ├── deterministic_extraction_service.py # [V2]
│   │   │   ├── nova_fallback_service.py         # [V2] ACL: boto3/Bedrock
│   │   │   ├── section_router.py                # [V2]
│   │   │   └── parsers/                         # [Merged] V1 extractors moved here
│   │   │       ├── contact_parser.py            # [Current] from extractors/contact/
│   │   │       ├── experience_parser.py         # [Current] from extractors/experience/
│   │   │       ├── education_parser.py          # [Current] from extractors/education/
│   │   │       ├── skills_parser.py             # [Current] from extractors/skills/
│   │   │       └── layout_extractor.py          # [Current] from extractors/layout/
│   │   ├── ranking/
│   │   │   ├── bm25_scorer.py                   # [Current] (V2: fixed IDF adaptation)
│   │   │   ├── tfidf_scorer.py                  # [Current]
│   │   │   ├── scorer.py                        # [Current] (V2: split orchestrator)
│   │   │   ├── experience_scorer.py             # [V2] Split from scorer.py
│   │   │   ├── education_scorer.py              # [V2] Split from scorer.py
│   │   │   ├── embedding_tiebreaker.py          # [V2] Conditional embeddings
│   │   │   ├── knockout_evaluator.py            # [V2]
│   │   │   └── flag_detector.py                 # [V2]
│   │   ├── ats/                                 # [V2 New] Standalone ATS logic
│   │   │   ├── ats_scoring_service.py           # [V2] No LLM
│   │   │   └── evaluators/
│   │   │       ├── two_column_layout.py
│   │   │       ├── hidden_text.py
│   │   │       ├── table_as_layout.py
│   │   │       ├── parseability.py
│   │   │       └── contact_presence.py
│   │   ├── infrastructure/                      # [Current] (Keeping current name over infra/)
│   │   │   ├── models/                          # [Current] DB models
│   │   │   ├── repositories/                    # [Current] Data access
│   │   │   ├── storage/                         # [Current]
│   │   │   ├── redis_client.py                  # [V2]
│   │   │   └── health.py                        # [Current]
│   │   ├── schemas/
│   │   │   ├── extraction.py                    # [Current]
│   │   │   ├── scoring.py                       # [Current]
│   │   │   ├── job.py                           # [V2]
│   │   │   ├── document.py                      # [V2]
│   │   │   └── ats.py                           # [V2]
│   │   ├── registries/
│   │   │   ├── skill_registry.py                # [Current]
│   │   │   ├── section_registry.py              # [Current]
│   │   │   ├── skill_graph.json                 # [Current]
│   │   │   └── idf.pkl                          # [V2 Target] Fixed reference-corpus BM25 IDF
│   │   ├── services/                            # [Current]
│   │   │   └── extraction_service.py            # [Current]
│   │   └── lambda_handler.py                    # [Current] (V2 uses ECS, but keeping for reference)
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── regression/                          # [V2] 3,856-resume benchmark
│   │   └── golden/                              # [V2] ODL snapshot tests
│   ├── Dockerfile                               # bundles JRE + Python
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── RecruiterDashboard.tsx
│   │   │   ├── CandidateDetail.tsx
│   │   │   └── AtsChecker.tsx                   # [V2] standalone, unauthenticated
│   │   ├── store/
│   │   │   └── weightsStore.ts                  # [V2] Zustand, instant recompute
│   │   └── api/
│   └── package.json
├── .github/workflows/
│   ├── ci.yml
│   └── deploy.yml
└── docker-compose.yml
```

## 7. Context for Future Sessions

- **If resuming work on extraction:** Start with `structural_parsing_service.py`. The ODL JVM must be warm. Check `tests/golden/` for snapshot stability. If ODL version changed, regenerate golden files intentionally, not accidentally. Ensure you reuse existing parsers (`contact_parser.py`, `skills_parser.py`) migrated to the new `extraction/parsers` folder.
- **If resuming work on extraction (Phase 2):** Start with `src/extraction/`. Phase 1 is done: `StructuralParsingService`, `OdlElement`, `StructuralParse`, `S3DocumentCache`, `InMemoryDocumentCache` all live in `src/extraction/`. ODL JSON field names use spaces — the mapping lives ONLY in `domain.py::_element_from_odl_dict`. Next task: build `SectionRouter` + port V1 parsers (`contact_parser`, `experience_parser`, `education_parser`, `skills_parser`) from `src/extractors/` to `src/extraction/parsers/` to consume `StructuralParse.markdown` instead of raw PyMuPDF output.
- **If resuming work on scoring:** The IDF table is in `registries/idf.pkl`. It is NOT computed from the candidate pool. If you see idf being computed dynamically, that's a bug — revert to the fixed table. Semantic embeddings are conditional — check `AMBIGUOUS_BAND` in config. Refactor `scorer.py` incrementally.
- **If resuming work on ATS:** ATS has zero dependencies on Job or Scoring contexts. If you find an import from `src.ranking` or `src.api.routes` in `src.ats/`, that's a boundary violation — fix it. ATS never calls an LLM.
- **If resuming work on Nova fallback:** Batching is non-negotiable. If you see a single-document Bedrock call in batch processing mode, that's HC-10 violation. Check `RedisBatchBuffer` flush threshold. Nova never overwrites a deterministic-resolved field.
- **If resuming work on frontend:** Weight recompute is frontend-only. If you see a backend call on weight change, that's HC-03 violation. The Zustand store holds raw component scores; the derived selector computes composite.

## 8. Phase 1 Session Log (2026-07-24)

### What Was Done
- Created `src/extraction/` package (new directory, per memory.md §6 target).
- `domain.py`: `OdlElement`, `StructuralParse`, `StructuralParseError`, `OdlParseCache` dataclasses + `structural_parse_from_odl_json()` factory. ODL JSON space-key mapping lives here and ONLY here.
- `structural_parsing_service.py`: `StructuralParsingService` ACL. Only file that imports `opendataloader_pdf`. Handles cache hit/miss, temp file lifecycle, error translation to `StructuralParseError`.
- `odl_cache.py`: `S3DocumentCache` (production) + `InMemoryDocumentCache` (tests). Both implement `DocumentCache` protocol.
- `tests/golden/fixtures/`: 3 fixture JSON files (single_column, two_column, hidden_text) — real ODL schema, no JVM required.
- `tests/golden/test_structural_parse_snapshots.py`: 21 golden snapshot tests.
- `tests/unit/test_structural_parsing_service.py`: 20 unit tests, all mocking `_run_odl`.

### Verification Gate Result
41/41 tests passed. Ruff: 0 errors. Phase 1 gate: **GREEN**.

### Java Constraint Note
Java is not installed on the dev machine. ODL requires JVM. The `StructuralParsingService` is designed to work in Docker (container bundles JRE per ADR-05). Local dev uses `InMemoryDocumentCache` + fixture JSON. This is the correct architecture — do NOT install Java locally or change this design.