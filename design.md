# design.md — Resume Ranker V2
> Low-level design, design patterns, and API contracts.

## 1. Extraction Quality Routing (Lambda A)
To balance speed and accuracy, Lambda A implements a tiered extraction strategy:
1. **Fast-Path (PyMuPDF):** Extract text using `fitz`. 
2. **Quality Check:** Calculate a heuristic quality score (0-100). Score is based on:
   - Character count ratio (text length / page count).
   - Presence of standard resume headers (e.g., "Experience", "Education", "Skills").
   - Valid date regex hits.
3. **Slow-Path (ODL):** If PyMuPDF quality score < 90, run `opendataloader-pdf`. This resolves multi-column layouts and provides bounding boxes (`bbox`) required for the ATS engine.
4. **Output:** Save the resulting JSON (Markdown + Elements) to S3. Push message to `ExtractQueue`.

## 2. API & Network Contract (Strict)
| Endpoint | Method | Auth | Request | Response |
|---|---|---|---|---|
| `/api/v2/jobs` | POST | JWT | `{title, description}` | `201 {job_id}` |
| `/api/v2/jobs/{id}/resumes` | POST | JWT | `multipart/form-data` | `202 {queued: [doc_ids]}` |
| `/api/v2/jobs/{id}/extract` | GET | JWT | `-` | `text/event-stream` (SSE) |
| `/api/v2/jobs/{id}/score` | POST | JWT | `{weights}` | `200 {candidates[]}` |
| `/api/v2/ats-check` | POST | None | `multipart/form-data` | `200 {ats_score, bounding_boxes[]}` |

## 3. SSE Event Contract
- `event: status\ndata: {"stage": "parsing", "doc_id": "123"}`
- `event: status\ndata: {"stage": "scoring", "doc_id": "123"}`
- `event: complete\ndata: {"total": 10, "success": 9, "failed": 1}`