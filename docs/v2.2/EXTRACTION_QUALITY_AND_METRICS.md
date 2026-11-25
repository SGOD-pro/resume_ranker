# SWYRA Sortlist v2.2 — Extraction Quality, Instrumentation & Metrics

**Document Status:** RELEASE SPECIFICATION  
**Release:** `v2.2 — Evidence Integrity, Strict Relevance Scoring, and ATS Diagnostics`  
**Modules:** `backend/src/extraction/extraction_pipeline.py` & `backend/src/api/routes/jobs_v2.py`  
**Date:** 2026-09-20  

---

## 1. Multi-Stage Extraction Pipeline Architecture

The Sortlist extraction pipeline operates as an evidence-first, progressive-degradation engine designed to balance throughput, deterministic reproducibility, and parsing fidelity.

```
                    ┌──────────────────────────────────────────────┐
                    │               Resume PDF Input               │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │   Tier 1: Fast PyMuPDF Structural Analysis   │
                    │   - Reading order reconstruction             │
                    │   - Layout block classification              │
                    │   - Exact geometry & bounding boxes          │
                    └──────────────────────┬───────────────────────┘
                                           │
                   Passes Quality Gate? ───┴─── Fails Quality Gate?
                   │ (Clean single-column)      │ (Multi-column / complex)
                   ▼                            ▼
        ┌──────────────────────┐    ┌───────────────────────────────────┐
        │ Skip JVM Subprocess  │    │ Tier 2: OpenDocument Layout (ODL) │
        │                      │    │ JVM Structural Tree Parser        │
        └──────────┬───────────┘    └─────────────────┬─────────────────┘
                   │                                  │
                   └──────────────────┬───────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────────────────┐
                    │ Tier 3: Deterministic Rule-Based Parsers     │
                    │ - ContactParser (CandidateIdentityResolver)  │
                    │ - SkillExtractor (Alias, graph, fuzzy)       │
                    │ - ExperienceParser (Roles, dates, titles)    │
                    │ - EducationParser (Degrees, institutions)    │
                    │ - ProjectExtractor (Tech stacks, summaries)  │
                    └──────────────────────┬───────────────────────┘
                                           │
             All Critical Fields Present? ─┴─ Missing Critical Fields?
             │ (Name, skills, experience)     │ (Sparse / non-standard)
             ▼                                ▼
┌──────────────────────────────┐    ┌───────────────────────────────────┐
│ Finalize Extraction Result   │    │ Tier 4: Bedrock Nova LLM Fallback │
│ (100% Deterministic)         │    │ Infill missing fields ONLY;       │
│                              │    │ deterministic data protected      │
└──────────────┬───────────────┘    └─────────────────┬─────────────────┘
               │                                      │
               └──────────────────┬───────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────────────────────┐
                    │ Attach Performance Instrumentation (_timings)│
                    │ Persist Structured Extracted JSON            │
                    └──────────────────────────────────────────────┘
```

---

## 2. Bounded Concurrency (`MAX_CONCURRENT_EXTRACTIONS`)

To prevent process thread starvation, excessive memory consumption, and API rate-limiting under bulk uploads, batch extraction is guarded by an asynchronous semaphore:

- **Concurrency Limit:** `MAX_CONCURRENT_EXTRACTIONS = 5`
- **Mechanism:** `asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)` wraps document processing in `run_pipeline_batch()`.
- **Failure Isolation:** Each extraction task is wrapped in an individual `try/except` boundary. A malformed or corrupted document logs an error and records a failed document result without terminating or delaying the remaining batch.

---

## 3. High-Precision Timing Instrumentation

Every extracted document attaches a structured `_timings` dictionary recording wall-clock milliseconds across pipeline phases:

| Timing Metric | Description | Typical Range |
| :--- | :--- | :---: |
| `structure_ms` | Time spent in layout classification, line grouping, and structural bounding box mapping. | $25\text{ms} - 90\text{ms}$ |
| `deterministic_ms` | Time consumed by deterministic extractors (contact, identity arbitration, skills, experience, education). | $40\text{ms} - 120\text{ms}$ |
| `nova_ms` | Latency incurred by Bedrock Nova LLM fallback. Recorded as `0.0` when deterministic extraction suffices. | $0\text{ms}$ (clean) / $800\text{ms} - 2200\text{ms}$ (fallback) |
| `download_ms` | S3 retrieval time before pipeline execution begins. | $15\text{ms} - 60\text{ms}$ |
| `total_ms` | Total end-to-end processing latency for the document. | $80\text{ms} - 2500\text{ms}$ |

---

## 4. Extraction Metrics API (`GET /api/v2/jobs/{job_id}/extraction-metrics`)

Recruiters and systems administrators can monitor pipeline performance and identity resolution health through a dedicated metrics endpoint.

### Request
```http
GET /api/v2/jobs/job_94a2b1c8/extraction-metrics HTTP/1.1
Host: api.sortlist.ai
Accept: application/json
```

### Response Schema (`200 OK`)
```json
{
  "job_id": "job_94a2b1c8",
  "total_documents": 25,
  "successful_extractions": 24,
  "failed_extractions": 1,
  "timing_summary": {
    "mean_total_ms": 164.2,
    "p95_total_ms": 312.8,
    "mean_structure_ms": 48.5,
    "mean_deterministic_ms": 115.7,
    "mean_nova_ms": 0.0,
    "mean_download_ms": 28.3
  },
  "identity_resolution": {
    "confirmed_count": 22,
    "provisional_count": 2,
    "unresolved_count": 0,
    "unresolved_rate": 0.0
  },
  "fallback_rates": {
    "nova_fallback_invocations": 0,
    "nova_fallback_rate": 0.0
  },
  "documents": [
    {
      "document_id": "doc_101",
      "candidate_name": "Sarah Jenkins",
      "identity_status": "CONFIRMED",
      "identity_confidence": 0.90,
      "timings": {
        "download_ms": 24.1,
        "structure_ms": 42.0,
        "deterministic_ms": 98.4,
        "nova_ms": 0.0,
        "total_ms": 140.4
      }
    }
  ]
}
```

---

## 5. Performance SLAs & Monitoring Gates

Sortlist enforces quality and latency thresholds across automated test suites:
- **P95 Latency SLA:** Deterministic pipeline processing must complete within $\le 2500\text{ms}$ per document.
- **Identity Resolution Quality:** Clean benchmark corpora must maintain an unresolved rate $\le 5.0\%$.
- **Zero Identity False Positives:** Descriptive text, skill phrases, job titles, and phrases with trailing punctuation must maintain an extraction rate of **0.0%**.
