# SWYRA Sortlist v2.2 Release Notes

**Release Name:** `v2.2 — Evidence Integrity, Strict Relevance Scoring, and ATS Diagnostics`  
**Working Branch:** `v2.1`  
**Release Date:** 2026-09-20  

---

## 1. Release Overview

Sortlist v2.2 is a comprehensive quality, fairness, and product-hardening release focused on **evidence integrity**, **deterministic relevance scoring**, and **transparent ATS diagnostics**.

This release directly addresses real-world extraction failures, eliminates bias-inducing heuristics, preserves full auditable evidence for all candidates (including those who fail knockout criteria), and introduces rigorous extraction metrics.

---

## 2. Key Defect Fixes & Enhancements

### 2.1 Candidate Identity Resolution (`CandidateIdentityResolver`)
* **Elimination of Non-Name Extractions:** Resolved the critical defect where descriptive phrases, summaries, and skill phrases (e.g., `"Insights possible sub-space."`) were extracted as candidate names.
* **Multi-Signal Arbitration:** Replaced greedy first-match parsing with multi-source candidate generation (ODL AST, Layout tags, header lines, contact neighbors, ALL-CAPS hero lines) scored against 6 deterministic positive signals.
* **Uncompromising Negative Disqualification:** Discards phrases with terminal punctuation (`.`, `!`, `?`), invalid token counts, blacklisted job titles (`engineer`, `developer`, `manager`), action verbs, technical skills, and corporate entities.
* **Fail-Safe Fallback:** If identity confidence falls below `0.45`, the system abstains and assigns `"Name needs review"` with an unresolved warning badge.
* **Identity Provenance Inspection:** Added a "Why this name?" drawer in the recruiter workspace displaying extraction source, bounding box coordinates, supporting text, and rejected false candidates.

### 2.2 Strict Relevance Scoring Policy (`scorer.py`)
* **Non-Zero Knockout Scoring:** Candidates who do not meet mandatory criteria (e.g., minimum years or required degrees) no longer have their relevance scores zeroed out. Full component scores are preserved for auditable evidence alongside an explicit `DOES_NOT_MEET_CRITERIA` status.
* **Phase 3 Sorting:** Candidate rankings group eligible candidates first sorted by relevance score descending, placing non-meeting candidates at the bottom while retaining their score visibility.
* **Prohibited Factor Elimination:**
  - Company prestige bonus (`_prestige_bonus()`) completely removed / zeroed out.
  - Certification prestige and hackathon bonuses removed. Certifications evaluated strictly for domain relevance.
  - Career gap penalties disabled.
* **Bounded Marginal Bonuses:** Replaced unbounded nice-to-have skill bonuses (+10.0 per match) with a bounded marginal bonus capped at `+5.0` (`min(5.0, matched * 1.0)`).
* **Audit Lineage & Factor Ledger:** Every scoring result includes `score_version ("2.2.0")`, `policy_version ("2026.1")`, `job_version`, and a typed `factor_ledger` recording contribution, source, confidence, and rule id for every point awarded.

### 2.3 ATS Diagnostics & Geometry (`ats_scorer.py`)
* **Decoupling of Metrics:** Cleanly separated `structural_score` (column interleaving, table nesting, font sprawl, header standards) from `extractor_confidence` (raw OCR clarity and character integrity).
* **Exact Geometry:** Removed synthetic approximations (`len(text) * 5`). Line bounding boxes and page indices are derived directly from PyMuPDF word quads.
* **Visual Integrity:** Suppressed synthetic bounding box overlays when verified coordinates are absent, emitting clear informational flags instead.
* **Dedicated Workspace Panel:** Integrated a dedicated ATS Health section in the candidate detail view with checklist validation, formatting risks, and a transparent limitations notice.

### 2.4 Extraction Instrumentation & Observability
* **High-Resolution Latency Tracking:** Every extraction attaches microsecond-precise timings for `structure_ms`, `deterministic_ms`, `nova_ms`, `download_ms`, and `total_ms`.
* **Bounded Concurrency:** Capped batch extraction at `MAX_CONCURRENT_EXTRACTIONS = 5` via `asyncio.Semaphore` to protect system memory and API limits.
* **New Extraction Metrics Endpoint:** Added `GET /api/v2/jobs/{job_id}/extraction-metrics` providing mean/P95 latencies, unresolved identity rates, fallback activation percentages, and per-document diagnostics.

---

## 3. Automated Test Suite & Validation Summary

| Test Suite | Total Tests | Passed | Failed | Execution Time |
| :--- | :---: | :---: | :---: | :---: |
| **Backend Integration & Acceptance** | 22 | 22 | 0 | 45.2s |
| **Domain Guardrails & Merge Rules** | 15 | 15 | 0 | 0.8s |
| **Candidate Identity Resolver (Unit + Gold-Set)** | 16 | 16 | 0 | 0.4s |
| **Scoring Policy v2.2 (Unit)** | 7 | 7 | 0 | 0.1s |
| **ATS Diagnostics (Unit)** | 4 | 4 | 0 | 0.2s |
| **Extraction Metrics Endpoint (Unit)** | 1 | 1 | 0 | 0.3s |
| **Frontend TypeScript & Build (`tsc -b && vite build`)** | Clean | Clean | 0 | 0.7s |
| **Frontend ESLint (`eslint .`)** | Clean | Clean | 0 | 3.5s |
| **TOTAL** | **65+** | **65+** | **0** | **100% PASS** |

---

## 4. Migration & Compatibility Guide

1. **Identity Resolution Schema:**
   - Client applications consuming candidate objects should inspect `identity_status` (`CONFIRMED`, `PROVISIONAL`, `UNRESOLVED`). When `identity_status === 'UNRESOLVED'`, display `"Name needs review"`.
2. **Knockout Score Handling:**
   - Downstream integrations should not assume knocked-out candidates have `final_score == 0.0`. Check `eligibility_status === 'DOES_NOT_MEET_CRITERIA'` to identify knockout conditions.
3. **Score Version Tracking:**
   - Persisted score snapshots generated by v2.2 are tagged with `score_version: "2.2.0"` and `policy_version: "2026.1"`.
