# Frozen Phase 2 Frontend API Contract

**Status:** FROZEN  
**Target API Version:** v2 (`/api/v2/jobs`)  
**Backend Branch:** `v2.1`  
**Governing Architecture:** Phase 1.6 Concurrency, Durability, and Direct Presigned S3 POST  

---

## 1. Core Architecture Principles for Frontend

1. **Direct-to-S3 Uploads (Zero Backend File Ingestion):**
   - The frontend never posts multipart file payloads through FastAPI or API Gateway.
   - Files are uploaded directly from the browser to Amazon S3 via presigned `POST` conditions.
2. **Immediate Fast-Path Stage 1:**
   - S3 PUT triggers PyMuPDF layout analysis in the background immediately per file.
   - The frontend does not wait for all files to upload before extraction begins.
3. **Analyze Barrier:**
   - Recruiter clicks **Analyze** to submit requirements and explicit `file_ids`.
   - Unselected files are transitioned to terminal `REMOVED`.
   - S1-ready files advance into bounded Stage 2 ODL microbatches and Bedrock infill.
4. **Short Polling with 304 Not Modified:**
   - Frontend polls `GET /api/v2/jobs/{job_id}/status` every `1.0s - 1.5s` while in active progress.
   - Backend calculates an aggregate `ETag` covering aggregate counters and per-file state. Polling returns HTTP 304 when no progress has occurred, minimizing bandwidth and CPU.
5. **No WebSockets, No SSE.**

---

## 2. API Endpoints Specification

### 2.1 Job Creation & Upload Initialization
`POST /api/v2/jobs` (or legacy alias `/jobs`)

Initializes the job record, registers planned files, and returns S3 presigned POST parameters.

#### Request Headers
```http
Content-Type: application/json
Authorization: Bearer <jwt_session_token> (Optional in dev/test)
```

#### Request Payload
```json
{
  "title": "Staff Backend Engineer",
  "department": "Engineering",
  "description": "Distributed systems, Python, cloud architectures",
  "must_have_skills": ["Python", "FastAPI", "Distributed Systems"],
  "nice_to_have_skills": ["Docker", "Kubernetes", "AWS"],
  "min_years": 4,
  "max_years": 12,
  "education_level": "Bachelors",
  "education_field": "Computer Science",
  "keywords": ["concurrency", "resilience", "microservices"],
  "weights": {
    "skills": 40.0,
    "experience": 25.0,
    "keywords": 20.0,
    "education": 15.0
  },
  "files": [
    {"filename": "alex_morgan.pdf", "file_size": 245012},
    {"filename": "marcus_vance.pdf", "file_size": 312040}
  ]
}
```

#### Constraints
- `files`: Maximum 100 files per job. If `files > 50`, the response includes pagination with `next_page_token`.
- Rate limit: 20 job creations per session per 24 hours.

#### Response: `201 Created`
```json
{
  "job_id": "4a71e8bf-4a92-482a-bc91-ec129e928a01",
  "status": "UPLOADING",
  "total_files": 2,
  "remaining": 2,
  "usable_files": 0,
  "files": [
    {
      "file_id": "f101-uuid4",
      "filename": "alex_morgan.pdf",
      "status": "PENDING_UPLOAD",
      "presigned_post": {
        "url": "https://resume-ranker-dev-isolated-445567096027.s3.ap-south-1.amazonaws.com/",
        "fields": {
          "key": "jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f101-uuid4.pdf",
          "bucket": "resume-ranker-dev-isolated-445567096027",
          "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
          "X-Amz-Credential": "ASIA...",
          "X-Amz-Date": "20260926T000000Z",
          "X-Amz-Security-Token": "IQoJ...",
          "Policy": "ey...",
          "X-Amz-Signature": "3a9f..."
        }
      }
    },
    {
      "file_id": "f102-uuid4",
      "filename": "marcus_vance.pdf",
      "status": "PENDING_UPLOAD",
      "presigned_post": {
        "url": "https://resume-ranker-dev-isolated-445567096027.s3.ap-south-1.amazonaws.com/",
        "fields": {
          "key": "jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f102-uuid4.pdf",
          "bucket": "resume-ranker-dev-isolated-445567096027",
          "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
          "X-Amz-Credential": "ASIA...",
          "X-Amz-Date": "20260926T000000Z",
          "X-Amz-Security-Token": "IQoJ...",
          "Policy": "ey...",
          "X-Amz-Signature": "7b2c..."
        }
      }
    }
  ],
  "next_page_token": null
}
```

---

### 2.2 Direct S3 Browser Upload Protocol
For each file in `files`:
- Construct a standard `FormData` object.
- Append all key-value pairs from `presigned_post.fields` in exact order.
- Append the `file` field with the local `File` or `Blob` object:
  ```typescript
  const formData = new FormData();
  Object.entries(fileInfo.presigned_post.fields).forEach(([k, v]) => {
    formData.append(k, v);
  });
  formData.append('file', fileObject);
  
  await fetch(fileInfo.presigned_post.url, {
    method: 'POST',
    body: formData,
  });
  ```
- S3 responds with `HTTP 204 No Content`.
- The frontend updates the local upload progress to 100% for that file.

---

### 2.3 Job Status & File Progress
`GET /api/v2/jobs/{job_id}/status`

#### Request Headers
```http
If-None-Match: "<previous_etag>"
```

#### Response: `200 OK` (or `304 Not Modified`)
```http
ETag: "w/9b72a6b24f"
Content-Type: application/json
```
```json
{
  "job_id": "4a71e8bf-4a92-482a-bc91-ec129e928a01",
  "status": "PROCESSING",
  "total_files": 2,
  "remaining": 1,
  "usable_files": 1,
  "analyze_requested": true,
  "is_stalled": false,
  "created_at": "2026-09-26T00:00:10Z",
  "updated_at": "2026-09-26T00:00:35Z",
  "files": [
    {
      "file_id": "f101-uuid4",
      "filename": "alex_morgan.pdf",
      "status": "S2_DONE",
      "candidate_name": "Alex Morgan",
      "low_confidence_extraction": false,
      "fallback_reason": null,
      "updated_at": "2026-09-26T00:00:25Z",
      "error_message": null
    },
    {
      "file_id": "f102-uuid4",
      "filename": "marcus_vance.pdf",
      "status": "S2_PROCESSING",
      "candidate_name": "Candidate",
      "low_confidence_extraction": false,
      "fallback_reason": null,
      "updated_at": "2026-09-26T00:00:30Z",
      "error_message": null
    }
  ]
}
```

#### Job States
| Job Status | Meaning | Frontend Action |
|---|---|---|
| `UPLOADING` | Files being uploaded by client. | Show file upload progress bars. |
| `READY_TO_ANALYZE` | Fast-path preprocessing complete; waiting for user to click Analyze. | Enable "Analyze" button. |
| `PROCESSING` | Analyze clicked; Stage 2 microbatching / scoring active. | Show analysis spinner & per-file progress. |
| `SCORING` | All files completed; final scoring barrier calculating rankings. | Show scoring badge. |
| `DONE` | Pipeline complete with usable ranked candidates. | Transition to Results view. |
| `DONE_WITH_ERRORS` | Pipeline complete, but 0 usable candidates reached scoring. | Show error state banner without crash. |
| `FAILED` | Catastrophic job-level failure. | Show failure alert with retry option. |

#### File States
| File Status | Terminal? | Meaning |
|---|---|---|
| `PENDING_UPLOAD` | No | Presigned URL generated; waiting for browser S3 PUT. |
| `S1_PROCESSING` | No | S3 notification triggered; Stage 1 fast-parse active. |
| `S1_DONE` | No | Fast-parse complete; layout signals evaluated. |
| `S2_PROCESSING` | No | Leased by Stage 2 worker; microbatching / LLM infill active. |
| `S2_DONE` | **Yes** | Extraction complete; candidate structured data ready. |
| `S1_FAILED` | **Yes** | Corrupt PDF or PyMuPDF crash. |
| `S2_FAILED` | **Yes** | Unrecoverable fallback error. |
| `REMOVED` | **Yes** | Excluded from analysis by recruiter. |

---

### 2.4 Trigger Analysis
`POST /api/v2/jobs/{job_id}/analyze`

#### Request Payload
```json
{
  "title": "Staff Backend Engineer",
  "must_have_skills": ["Python", "FastAPI"],
  "nice_to_have_skills": ["Docker"],
  "min_years": 4,
  "max_years": 12,
  "weights": {
    "skills": 40.0,
    "experience": 25.0,
    "keywords": 20.0,
    "education": 15.0
  },
  "file_ids": ["f101-uuid4", "f102-uuid4"]
}
```

#### Response: `202 Accepted`
```json
{
  "job_id": "4a71e8bf-4a92-482a-bc91-ec129e928a01",
  "status": "PROCESSING",
  "analyze_requested": true,
  "remaining": 2,
  "usable_files": 0
}
```

---

### 2.5 Candidate Results
`GET /api/v2/jobs/{job_id}/results`

#### Response: `200 OK`
```json
{
  "job_id": "4a71e8bf-4a92-482a-bc91-ec129e928a01",
  "status": "DONE",
  "total_candidates": 2,
  "weights": {
    "skills": 40.0,
    "experience": 25.0,
    "keywords": 20.0,
    "education": 15.0
  },
  "candidates": [
    {
      "rank": 1,
      "document_id": "f101-uuid4",
      "name": "Alex Morgan",
      "email": "alex.morgan@example.com",
      "phone": "+1-555-0144",
      "final_score": 91.2,
      "signal": "Strong",
      "skill_score": 95.0,
      "experience_score": 88.0,
      "keyword_score": 90.0,
      "education_score": 85.0,
      "knocked_out": false,
      "knockout_reasons": [],
      "skills": ["Python", "FastAPI", "Distributed Systems", "AWS"],
      "low_confidence_extraction": false,
      "pdf_url": "https://resume-ranker-dev-isolated-445567096027.s3.ap-south-1.amazonaws.com/jobs/.../raw/f101-uuid4.pdf?AWSAccessKeyId=..."
    }
  ]
}
```

---

## 3. Guarantees and Invariants

1. **Terminal Decrement Invariant:**
   - Every file in terminal state (`S1_FAILED`, `S2_DONE`, `S2_FAILED`, `REMOVED`) decrements `job.remaining` by exactly 1.
   - When `remaining == 0` and `analyze_requested == true`, scoring triggers automatically.
2. **Low-Confidence Graceful Degradation:**
   - When global daily LLM cap or per-job cap is hit, files are tagged `low_confidence_extraction=true`.
   - Files are **never failed** simply because an LLM slot was unavailable.
   - UI should display a subtle badge: `"Heuristic extraction (LLM cap reached)"`.
3. **Stall Detection (`is_stalled`):**
   - If no update occurs for >600 seconds while in progress, `is_stalled` is set to `true`.
   - UI must display a non-blocking diagnostic message with a retry action.
