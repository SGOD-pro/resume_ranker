# 00 — Cleanup Recommendations

> Audit performed: 2026-06-24
> Scope: Full repository (`backend/`, `frontend/`, `tests/`)
> **Cleanup executed: 2026-06-24** ✅

---

## 1. Dead Imports (Unused Symbols) — ✅ DONE

| File | Symbol | Type | Status |
|------|--------|------|--------|
| `src/ranking/scorer.py:82` | `_tokenize` | Imported but never called | ✅ Removed |
| `src/ranking/scorer.py:83` | `_tf` | Imported but never called | ✅ Removed |
| `src/ranking/scorer.py:84` | `_cosine_sim` | Imported but never called | ✅ Removed |
| `src/ranking/scorer.py:85` | `_text_cosine_sim` | Imported but never called | ✅ Removed |
| `src/ranking/scorer.py:92` | `_most_recent_end_date` | Imported but never called | ✅ Removed |
| `src/ranking/scorer.py:69` | `_SINGLE_CHAR_SKILLS` | Imported but never referenced | ✅ Removed |

---

## 2. Duplicate Code

### 2a. `SectionContent` Dataclass — ✅ RESOLVED

| Location | Status |
|----------|--------|
| `src/schemas/extraction.py:26–36` | ✅ Canonical (kept) |
| `src/core/section_assembly.py:12–22` | ✅ **Deleted** — zero importers, pipeline already imports from `schemas/extraction.py` |

### 2b. `_parse_degree_level` — Duplicated in Two Modules — ⏭️ SKIPPED

| Location | Function Name |
|----------|---------------|
| `src/ranking/scorer.py:51–60` | `_parse_degree_level()` |
| `src/ranking/similarity.py:304–323` | `_parse_degree_level_local()` |

**Status:** Skipped — consolidation requires modifying production code in `similarity.py`. Both copies are functionally identical and work correctly.

---

## 3. Unused Files — ✅ DONE

### 3a. `src/services/ranking_service.py` — ✅ DELETED

Thin wrapper around `CandidateScorer`. Never imported by any API route. Never called by any test.

### 3b. `src/services/document_service.py` — ✅ DELETED

End-to-end wrapper. Only imported in `services/__init__.py` for re-export. Never called.

### 3c. `src/core/section_assembly.py` — ✅ DELETED

Duplicate `SectionContent` dataclass. Zero importers. Pipeline uses `schemas/extraction.py`.

---

## 4. Obsolete Benchmark Artifacts — ✅ DONE

### 4a. `tests/benchmark_v3/` — ✅ DELETED (entire directory)

5 files, ~107KB total. Fully superseded by v4 benchmark.

Deleted files:
- `benchmark_v3_runner.py` (56KB)
- `benchmark_v3_report.json` (35KB)
- `ground_truth_candidates.json` (11KB)
- `production_readiness.md` (4KB)
- `__init__.py`

### 4b. `tests/benchmark_v4/report_v6_backup.md` — ✅ DELETED

Stale backup of an older report version (42KB).

### 4c. `tests/benchmark_v4/dedup_resumes.py` — ✅ MOVED to `scripts/`

Relocated to `scripts/dedup_resumes.py` where other maintenance utilities live.

---

## 5. Experimental / Maintenance Scripts — No action needed

### 5a. `backend/scripts/benchmark.py` — Retained

Baseline capture script. Functional and potentially useful for CI.

---

## 6. Architectural Redundancies

### 6a. `src/services/__init__.py` Re-exports — ✅ CLEANED

Removed dead re-exports of `RankingService` and `DocumentService`. Now only exports `ExtractionService` (the only service used by API routes).

### 6b. `pipeline.py` CLI Section — ⏭️ SKIPPED

Low priority. `main.py` is the canonical CLI entry point. The `__main__` block in `pipeline.py` is cosmetic duplication.

---

## 7. Summary Table

| Category | Item | Action | Status |
|----------|------|--------|--------|
| Dead imports | `scorer.py` — 6 unused imports | Remove | ✅ Done |
| Duplicate code | `SectionContent` in 2 files | Delete orphan | ✅ Done |
| Duplicate code | `_parse_degree_level` in 2 files | Consolidate | ⏭️ Skipped |
| Dead file | `ranking_service.py` | Delete | ✅ Done |
| Dead file | `document_service.py` | Delete | ✅ Done |
| Dead file | `section_assembly.py` | Delete | ✅ Done |
| Obsolete benchmark | `benchmark_v3/` (entire dir) | Delete | ✅ Done |
| Stale backup | `report_v6_backup.md` | Delete | ✅ Done |
| One-time utility | `dedup_resumes.py` | Move to scripts/ | ✅ Done |
| Redundant CLI | `pipeline.py` `__main__` block | Remove | ⏭️ Skipped |
| Dead re-exports | `services/__init__.py` | Clean up | ✅ Done |

---

## Verification

All changes verified with 7 end-to-end tests:

```
✅ Test 1: Civil engineer → engineering.civil (NOT healthcare)
✅ Test 2: Nurse → healthcare (correct)
✅ Test 3: SW Engineer → engineering.software (correct)
✅ Test 4: Scorer → score=100.0, rank=1 (scoring works)
✅ Test 5: Knockout → knocked_out=True (3 reasons detected)
✅ Test 6: ExtractionService import: OK
✅ Test 7: FastAPI app: OK (6 routes)
```

> **No production behavior was affected by any of these changes.**
