# SWYRA Sortlist v2.2 — ATS Diagnostics & Geometry Architecture

**Document Status:** RELEASE SPECIFICATION  
**Release:** `v2.2 — Evidence Integrity, Strict Relevance Scoring, and ATS Diagnostics`  
**Modules:** `backend/src/ranking/ats_scorer.py`, `backend/src/extractors/layout/layout_extractor.py`, `frontend/src/components/detail/AtsHealthSection.tsx`  
**Date:** 2026-09-20  

---

## 1. Structural Parseability vs. Extractor Confidence

A foundational principle of **v2.2** is the strict technical decoupling of **ATS Structural Parseability** from **Extractor Confidence**. In legacy systems, these signals were conflated into a single ambiguous number, misinforming recruiters and candidates alike.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Resume Diagnostics Split                                │
└───────────────────────────┬────────────────────────────────┬───────────────────────────┘
                            │                                │
                            ▼                                ▼
         ┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐
         │       ATS Structural Score          │  │       Extractor Confidence          │
         │             (0 - 100)               │  │             (0 - 100)               │
         ├─────────────────────────────────────┤  ├─────────────────────────────────────┤
         │ Evaluates how standard enterprise   │  │ Evaluates the raw optical and       │
         │ ATS parsers ingest the document.    │  │ character quality of the PDF.       │
         │                                     │  │                                     │
         │ • Multi-column interleaving         │  │ • OCR text extractability           │
         │ • Table & cell nesting              │  │ • Character encoding validity       │
         │ • Header hierarchy & section labels │  │ • Embedded font integrity           │
         │ • Contact block detectability       │  │ • Symbol corruption & garbled text  │
         │ • Font variance & formatting sprawl │  │                                     │
         └─────────────────────────────────────┘  └─────────────────────────────────────┘
```

### Why Decoupling is Essential
A modern two-column graphical resume can yield **99% Extractor Confidence** because every character is crisp digital vector text. However, when processed through an enterprise ATS (e.g., Taleo, Workday), text lines across columns can be read left-to-right horizontally, interleaving role titles with unrelated sidebar skills. 

In Sortlist v2.2:
- **`structural_score`** measures standard ATS ingestibility (e.g., multi-column penalty, table penalty, section detection).
- **`extractor_confidence`** measures text extraction reliability.
- The two metrics are computed independently, reported separately in the API, and rendered as distinct diagnostic gauges in the UI.

---

## 2. Exact Bounding Box Geometry

Previous versions contained synthetic fallback approximations (e.g., estimating line widths as `len(line.text) * 5` and hardcoding `page = 1`). This resulted in visual bounding boxes in the PDF viewer that misaligned with actual document elements.

In **v2.2**, all diagnostic bounding boxes require verified geometry:
1. **Source Geometry:** In `backend/src/extractors/layout/layout_extractor.py`, `ClassifiedLine` records exact coordinates `(x0, top, x1, bottom)` and 1-based `page` indices derived directly from PyMuPDF word-level quad geometries.
2. **Deterministic Aggregation:** When formatting risks (e.g., complex tables, multi-column blocks, icon-based contact rows) are detected, bounding boxes are constructed strictly from verified coordinate spans.
3. **No Fake Overlays:** If structural analysis flags an issue on a document whose coordinate stream is missing or corrupted, the system emits an **informational flag only** without rendering phantom bounding boxes.

### Bounding Box Data Contract
```typescript
export interface BoundingBox {
  page: number;              // 1-based page index
  x0: number;                // Left boundary (PDF points)
  y0: number;                // Top boundary (PDF points)
  x1: number;                // Right boundary (PDF points)
  y1: number;                // Bottom boundary (PDF points)
  severity: 'warning' | 'severe';
  reason: string;            // Plain-English diagnostic explanation
}
```

---

## 3. Dedicated ATS Diagnostics Panel (`AtsHealthSection`)

In the recruiter workspace (`CandidateDetailPanel.tsx`), ATS health has been elevated to a dedicated analysis section alongside Match Score and Skills Breakdown.

### Key Capabilities
- **Parseability Meter:** Visual gauge displaying structural ATS compatibility ($0 - 100$).
- **Checklist Summary:** Real-time validation of essential sections (Contact Information, Work Experience, Education, Technical Skills).
- **Actionable Risk Warnings:** Categorized alerts for formatting hazards (e.g., "Multi-column layout detected: text may interleave during legacy ATS ingestion").
- **Limitations Notice:** Built-in disclaimer stating that no diagnostic can guarantee hiring outcomes across proprietary third-party ATS platforms.

---

## 4. Privacy & Ephemeral Data Retention

The standalone ATS Checker (`/api/v2/jobs/ats-check` and `AtsCheckerPage.tsx`) implements strict ephemeral privacy protections:
1. **Zero Persistent Storage:** Files uploaded to the standalone ATS checker are processed in-memory or transient storage and purged immediately upon response completion.
2. **No Database Write:** Standalone ATS checks do not write candidate records, contact information, or documents to DynamoDB or S3.
3. **No Model Training:** Uploaded resumes are never logged, cached, or used for model fine-tuning or evaluation without explicit user authorization.

---

## 5. Explicit Limitations Disclaimer

Sortlist publishes the following transparent limitations notice across all ATS diagnostic interfaces:

> **ATS Diagnostic Limitations:**  
> The SWYRA Sortlist ATS Health Check assesses general structural parseability based on industry-standard formatting guidelines (single-column reading order, standard section headings, and clean text layers). Because commercial ATS platforms (e.g., Workday, Greenhouse, Taleo, iCIMS) utilize proprietary, non-public parsing algorithms, a high parseability score does not guarantee parsing success or advancement in any third-party applicant tracking system.
