# Resume Ranker V2 — Project Overview

> **High-level project overview and business value.** *Rev 2 — Hybrid Architecture.*

---

## 1. What This Is

**Resume Ranker V2** is a candidate screening platform that ranks PDF resumes against a job description. A recruiter uploads a batch and gets a ranked list with explainable scores in minutes. A job-seeker can upload a single resume to the standalone ATS checker and see exactly what will break in an automated system.

V2 is a structural rethink of V1's extraction layer. V1's regex/dictionary engine was never the problem — feeding it column-scrambled text from PyMuPDF was. V2 fixes the input, keeps the engine, and adds an LLM only for the ~10% of resumes the deterministic engine cannot parse.

---

## 2. Why V2 Exists

V1 benchmarked at **72/100 extraction quality**. 
* **Root Cause:** `PyMuPDF` pixel-clustering broke on two-column and table-based layouts, feeding garbled text to otherwise-correct regex parsers.
* **Core Insight:** The skill-matching engine itself hit **100% F1** on the benchmark — the matching logic was never broken.

### What V2 Changes vs. V1

| Problem | V1 Root Cause | V2 Fix |
| :--- | :--- | :--- |
| **72/100 extraction ceiling** | `PyMuPDF` pixel-clustering breaks on multi-column layouts | `opendataloader-pdf` structural parsing with bounding boxes (`bbox`) |
| **Regex parsers miss fields on scrambled text** | Input text was garbled, not the regex engine | Feed clean ODL markdown to V1 regex — same code, clean input |
| **Non-deterministic BM25 scores** | Dynamic per-pool IDF calculation | Fixed reference-corpus IDF table |
| **No ATS detection** | Feature not built | Deterministic `bbox`-based ATS engine (no LLM required) |
| **Lambda cold starts** | ML model loading on AWS Lambda | ECS Fargate (JVM-warm requirement for ODL) |
| **Black-box scoring** | Weighted sum in 864-line God-class | Component scores persisted, composite computed at read time |

### What V2 Keeps from V1

- **V1 Regex & Dictionary Parsers**: Ported to consume clean `opendataloader-pdf` markdown.
- **`skill_graph.json` Concept**: Preserved and now backed by PostgreSQL / DynamoDB registries.
- **BM25 + TF-IDF Primaries**: Primary scoring algorithms (now using fixed corpus IDF).
- **Recruiter Interface & Logic**: Three-panel UI, knockout logic, and customizable weight system.

---

## 3. Target Users

- **Primary**: Technical recruiters and hiring managers receiving **50–500 resumes per role**.
- **Secondary**: Engineering leads pre-screening candidates before technical calls.
- **Tertiary**: Job-seekers using the standalone ATS checker to optimize resume formatting.

---

## 4. Core Value Proposition

* **⚡ Speed**: `< 15 seconds` per resume end-to-end. The deterministic path processes `~90%` of resumes in `< 2 seconds`. LLM fallback adds latency only for the `~10%` that require complex layout resolution.
* **🔍 Explainability**: Every score decomposes into individual components with full provenance tracking — `deterministic` vs. `nova_fallback` vs. `unresolved`. No opaque black boxes.
* **🎯 ATS Transparency**: Job-seekers see exactly which formatting choices will break an ATS, with actionable fix recommendations. Recruiters see the same data inline.
* **💰 Cost Discipline**: LLM calls are batched and conditional — `~98%` fewer invocations compared to a pure-LLM pipeline. Embedding compute is conditional, not universal.

---

## 5. Business Model

### B2B SaaS Tiers

* **Free Tier**: 1 active job, 10 resumes, standalone ATS checker (unauthenticated, IP-rate-limited).
* **Pro Tier**: 10 active jobs, 100 resumes per job, CSV export, API access.
* **Team Tier**: Unlimited jobs, recruiter collaboration features, priority processing queue.

---

## 6. Success Metrics

| Metric | Target | Measurement Strategy |
| :--- | :--- | :--- |
| **Extraction Accuracy (field-level)** | `> 92%` | Benchmark suite of 500+ real-world resumes |
| **Nova Fallback Rate** | `< 15%` | `nova_fields_used / total_fields` aggregated across batches |
| **P95 End-to-End Processing** | `< 15s` per resume | Distributed tracing on pipeline |
| **Weight Recompute Latency** | `< 200ms` | Frontend performance monitoring |
| **ATS Score Stability** | `100%` deterministic | Same input $\rightarrow$ same output, always |
| **Knockout False-Positive Rate** | `< 5%` | Manual audit of disqualified candidate sample |
| **System Uptime** | `> 99.5%` | CloudWatch synthetic health checks |