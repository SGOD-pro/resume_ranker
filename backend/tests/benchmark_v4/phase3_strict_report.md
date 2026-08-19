# Phase 3 Extraction Pipeline Benchmark — Strict Mode
Generated: 2026-07-31T20:50:57.762083
PDFs sampled: 50

## Verification Gate

| Check | Status |
|-------|--------|
| Step 3.4 Merge Rule (LLM never overwrites deterministic field) | ✅ PASSED |
| ODL Routing (quality<0.90 → ODL triggered) | ✅ PASSED |
| ODL Markdown Overwrite (ODL text fed to regex, not stale PyMuPDF) | ✅ PASSED |
| **Overall Gate** | 🟢 **PASS — Ready for Phase 4** |

## Section 1 — Step 3.4 Merge Rule Test
**Verdict: PASSED** (5/5 checks)

| # | Test | Result |
|---|------|--------|
| 1 | Step 3.4 Canonical: email=real, phone=null → LLM fills phone only | ✅ |
| 2 | All deterministic fields present — LLM must be fully rejected | ✅ |
| 3 | All fields null — LLM fills everything | ✅ |
| 4 | LLM returns null (garbage input) — deterministic fields untouched | ✅ |
| 5 | Deterministic non-empty skills → LLM skills MUST NOT overwrite | ✅ |

## Section 2 — ODL Routing Verification
Routing: **PASSED**  |  Markdown Overwrite: **PASSED**

| File | Quality | ODL Called? | Expected? | Correct | Markdown Source |
|------|---------|-------------|-----------|---------|-----------------|
| 1 | 0.402 | Yes | Yes | ✅ | ODL ✅ |
| 10 | 0.640 | Yes | Yes | ✅ | ODL ✅ |
| 12 | 0.456 | Yes | Yes | ✅ | ODL ✅ |

## Section 3 — Pathing Breakdown (50 Resumes)

| Path | Count | % |
|------|-------|---|
| PyMuPDF-only (quality ≥ 0.90) | 8 | 16.0% |
| ODL triggered (quality < 0.90) | 42 | 84.0% |
| Nova triggered (gaps after regex) | 50 | 100.0% |
| Errors | 0 | 0.0% |

**Average quality score:** 0.619  (p50=0.500, p95=1.000)
**Resumes below 0.90 threshold:** 42 / 50

> ✅ **Consistent:** Low quality correctly triggered ODL.

## Section 4 — Real Extraction Success

| Field | By Regex (Deterministic) | By Nova (LLM gap-fill) | Missing | Total Found % |
|-------|--------------------------|------------------------|---------|---------------|
| email | 30 (60.0%) | 0 (0.0%) | 20 | 60.0% |
| phone | 44 (88.0%) | 0 (0.0%) | 6 | 88.0% |
| name | 47 (94.0%) | 0 (0%) | 3 | 94.0% |

> **Deterministic** = field already in raw text; regex would have found it.
> **Nova (LLM)** = field was null after regex; Nova filled it.
> Nova mock does NOT inflate counts — it only returns data it can see in text.

## Section 5 — Latency p50/p95 by Stage

| Stage | n | p50 (ms) | p95 (ms) | avg (ms) |
|-------|---|----------|----------|----------|
| pymupdf | 50 | 89.9 | 172.9 | 101.4 |
| odl | 42 | 0.1 | 0.1 | 0.1 |
| regex_parse | 50 | 56.8 | 139.9 | 65.2 |
| nova | 50 | 0.7 | 1.2 | 0.7 |
| total | 50 | 235.8 | 446.5 | 274.9 |

> ODL/Nova latencies are mock timings — near-zero in test env.

## Section 6 — Per-Resume Spot Check (first 15)

| # | File | Quality | ODL | Nova | Email | Phone |
|---|------|---------|-----|------|-------|-------|
| 1 | 1 | 0.402 | ✓ | ✓ | `email@email.com` | `3868683442` |
| 2 | 10 | 0.640 | ✓ | ✓ | `email@email.com` | `890-555-0401` |
| 3 | 12 | 0.456 | ✓ | ✓ | `email@email.com` | `3868683442` |
| 4 | 13 | 0.483 | ✓ | ✓ | `email@email.com` | `3868683442` |
| 5 | 14 | 0.550 | ✓ | ✓ | `email@email.com` | `890-555-0401` |
| 6 | 15 | 0.494 | ✓ | ✓ | `email@email.com` | `(541) 754-3010` |
| 7 | 16 | 0.618 | ✓ | ✓ | `—` | `—` |
| 8 | 17 | 0.425 | ✓ | ✓ | `sophia.bennett@email.com` | `(555) 123-7890` |
| 9 | 18 | 0.492 | ✓ | ✓ | `—` | `—` |
| 10 | 2 | 0.457 | ✓ | ✓ | `resume@example.com` | `890-555-0401` |
| 11 | 3 | 0.785 | ✓ | ✓ | `email@email.com` | `—` |
| 12 | 5 | 0.469 | ✓ | ✓ | `email@email.com` | `3868683442` |
| 13 | 6 | 0.595 | ✓ | ✓ | `email@email.com` | `3868683442` |
| 14 | 7 | 0.477 | ✓ | ✓ | `email@email.com` | `3056478349` |
| 15 | 8 | 0.479 | ✓ | ✓ | `email@email.com` | `(541) 754-3010` |

## Phase 4 Gate Decision
🟢 **ALL CHECKS PASSED** — Pipeline is internally consistent:
- Quality gate routes correctly to ODL when quality < 0.90.
- ODL markdown overwrites PyMuPDF text before regex runs.
- Nova fills gaps without overwriting deterministic fields (R-08/R-09).
- **Cleared to proceed to Phase 4.**