# design.md — Resume Ranker V2
> Low-level design, design patterns, and API contracts. Rev 4.

## 1. DynamoDB Access Patterns & Schema (No Table Scans)

To support V2 filtering requirements (score range, skill presence, status) without expensive `scan()` operations, DynamoDB uses specific Global Secondary Indexes (GSIs). 

**Architectural Rule:** Multi-attribute filtering MUST use GSIs. `scan()` with `FilterExpression` on the base table is strictly prohibited for candidate queries.

### Table: `Candidates`
*   **Base Table PK:** `JOB#{job_id}`
*   **Base Table SK:** `CANDIDATE#{candidate_id}`
*   **Attributes:** `name`, `email`, `status`, `composite_score`, `skill_list`, `created_at`

### GSI 1: Score-Range Queries (FR-29/30)
DynamoDB GSIs are equality-then-range. To query a score range (e.g., 70-80), we bucket the score.
*   **GSI1 PK:** `JOB#{job_id}#SCORE_BUCKET#{floor(composite_score / 10)}`
*   **GSI1 SK:** `composite_score`
*   *Query Pattern:* DynamoDB cannot query across multiple partition keys in a single request. To get scores 70-80, you MUST execute 2 separate queries: one on PK `JOB#123#SCORE_BUCKET#7` (SK BETWEEN 70 and 79.99) and one on PK `JOB#123#SCORE_BUCKET#8` (SK BETWEEN 80 and 80). The application layer MUST merge these results client-side.

### GSI 2: Skill-Presence Filter (FR-29)
Sparse index: one item per (candidate, skill). Only populated for candidates that possess the skill.
*   **GSI2 PK:** `JOB#{job_id}#SKILL#{skill_id}`
*   **GSI2 SK:** `composite_score`
*   *Query Pattern:* To get top candidates with Python, query PK `JOB#123#SKILL#python` and limit to 50.

### GSI 3: Status Filter (Shortlist/Reject)
*   **GSI3 PK:** `JOB#{job_id}#STATUS#{status}`
*   **GSI3 SK:** `created_at`
*   *Query Pattern:* To get all shortlisted candidates, query PK `JOB#123#STATUS#shortlisted`.

---

## 2. Pre-Extraction Structural Quality Gate

V1's PyMuPDF extraction failed on multi-column layouts because it scrambled reading order. We cannot use the post-extraction composite presence score to route fallbacks, because a garbled layout might still produce a non-empty (but wrong) `experience` field.

The routing decision MUST be a pre-extraction structural heuristic, computed from raw layout geometry *before* field parsing happens.

```python
def pymupdf_layout_quality(page) -> float:
    """
    Computed BEFORE field parsing. Answers: 'is this text extractable
    in reading order at all', not 'did we successfully parse a name'.
    """
    signals = {}

    # 1. Column consistency — PyMuPDF's actual failure mode.
    x_clusters = cluster_word_x_positions(page)
    signals["single_column"] = 1.0 if len(x_clusters) <= 1 else 0.0

    # 2. Reading-order sanity — do consecutive words/lines have
    #    monotonically non-decreasing y-position within a column?
    signals["reading_order_score"] = reading_order_monotonicity(page)  # 0.0-1.0

    # 3. Char density vs page area — catches scanned/image PDFs
    signals["char_density"] = min(1.0, len(page.get_text()) / EXPECTED_CHARS_PER_PAGE)

    # 4. Table detection — if the page looks tabular, PyMuPDF will misread it.
    signals["not_table_heavy"] = 1.0 if not looks_tabular(page) else 0.0

    return (
        signals["single_column"] * 0.35 +
        signals["reading_order_score"] * 0.30 +
        signals["char_density"] * 0.20 +
        signals["not_table_heavy"] * 0.15
    )
```

**Routing Logic (Lambda A / BackgroundTask):**
1. Run PyMuPDF. Calculate `pymupdf_layout_quality` per page.
2. If average page quality `< 0.90` → Run `opendataloader-pdf` (JVM). Overwrite PyMuPDF output.
3. Proceed to Evaluation.

---

## 3. Instrumentation & Telemetry (StageTiming)

To validate the PyMuPDF→ODL→Nova routing decision empirically, every extraction stage MUST emit a `StageTiming` record. This prevents silent mis-tuning of the quality gate.

```python
@dataclass
class StageTiming:
    document_id: str
    stage: str              # "pymupdf_parse" | "quality_check" | "odl_parse" |
                            # "deterministic_extract" | "nova_fallback" | "scoring" | "ats"
    method_used: str        # "pymupdf" | "opendataloader" | "nova-micro" | "nova-lite"
    duration_ms: float
    triggered_fallback: bool # did THIS stage's output cause the next stage to fire?
    quality_score: float | None # only populated for "quality_check" stage
```
This list of records is persisted alongside the `ExtractionResult` in S3 and aggregated in the benchmark report to track ODL fallback rates and p50/p95 latencies per stage.

---

## 4. LLM Fallback Pipeline (Lambda B)

If the deterministic regex engine yields `UnresolvedChunk`s (e.g., weird date format), the LLM fallback is invoked:
1. Batch up to 10 unresolved chunks.
2. Call Amazon Bedrock (`amazon.nova-micro-v1:0`) via `boto3`.
3. Use `toolConfig` to enforce strict JSON schema (no free-text JSON parsing).
4. `temperature: 0.0`.
5. Merge response into `ExtractionResult` (tag provenance as `nova_fallback`). LLM NEVER overwrites a deterministic-resolved field.

---

## 5. API & Network Contract (Strict)

The frontend and backend MUST adhere to this exact contract. Note: There is no authentication layer; endpoints are open.

| Endpoint | Method | Request | Response | Notes |
|---|---|---|---|---|
| `/api/v2/jobs` | POST | `{title, description}` | `201 {job_id}` | Open |
| `/api/v2/jobs/{id}/resumes` | POST | `multipart/form-data` | `202 {queued: [doc_ids]}` | Open |
| `/api/v2/jobs/{id}/extract` | GET | `-` | `text/event-stream` (SSE) | Open |
| `/api/v2/jobs/{id}/score` | POST | `-` (uses cached weights) | `200 {candidates[]}` | Open |
| `/api/v2/jobs/{id}/weights` | PATCH | `{weights}` | `200 {status: "updated"}` | Open |
| `/api/v2/ats-check` | POST | `multipart/form-data` | `200 {ats_score, bounding_boxes[]}` | Open (IP-rate-limited) |

---

## 6. SSE Event Contract

The SSE stream (`GET /extract`) emits the following events. The frontend `app-store` transitions its `appPhase` based on these events.

- `event: status\ndata: {"stage": "parsing", "doc_id": "123"}`
- `event: status\ndata: {"stage": "scoring", "doc_id": "123"}`
- `event: complete\ndata: {"total": 10, "success": 9, "failed": 1}`

**Frontend Transition:** Upon receiving `complete`, the frontend closes the `EventSource`, calls `POST /score`, and transitions `appPhase` to `scored`.