# SWYRA Sortlist v2 — API Contracts

> Authoritative API reference. Supersedes `docs/05_API_LAYER.md`.

## Base URL
- Development: `http://localhost:8000`
- Production: Configured via environment variable

## Authentication (P0 — To Be Implemented)
All endpoints except `/health` and `/api/v2/ats-check` require authentication.
- Auth header: `Cookie: session=<token>` (httpOnly secure cookie)
- Unauthenticated requests return `401 Unauthorized`
- Requests to resources outside the user's organization return `403 Forbidden`

## Endpoints

### Health
- `GET /health` — Liveness probe, no auth required
  - Response: `{ status: "ok", version: string }`

### Authentication (P0)
- `POST /api/v2/auth/register` — Create org + admin user
- `POST /api/v2/auth/login` — Create session
- `POST /api/v2/auth/logout` — Destroy session
- `GET /api/v2/auth/me` — Get current user

### Jobs
- `POST /api/v2/jobs` — Create job
  - Body: `{ title, department?, description?, must_have_skills[]?, nice_to_have_skills[]?, min_years?, max_years?, education_level?, education_field?, keywords[]?, weights? }`
  - Response: `{ job_id, title, status: "created" }`

- `PATCH /api/v2/jobs/{job_id}` — Update job criteria
  - Body: Partial job fields
  - Response: `{ job_id, status }` with optimistic concurrency

- `GET /api/v2/jobs` — List jobs for current org
  - Response: `{ jobs: JobSummary[] }`

- `DELETE /api/v2/jobs/{job_id}` — Delete job and all associated data

### Documents & Upload Sessions

#### 1. Create Upload Session (Direct S3 Flow)
- `POST /api/v2/jobs/{job_id}/upload-sessions`
  - Body:
    ```json
    {
      "files": [
        {
          "filename": "candidate.pdf",
          "file_size": 1048576,
          "content_hash": "a1b2c3d4e5..."
        }
      ]
    }
    ```
  - Response:
    ```json
    {
      "session_id": "session-uuid",
      "job_id": "job-uuid",
      "job_version": 1,
      "status": "UPLOADING",
      "documents": [
        {
          "document_id": "doc-uuid",
          "filename": "candidate.pdf",
          "presigned_put_url": "https://s3.amazonaws.com/bucket/key?AWSAccessKeyId=...",
          "s3_pdf_key": "resumes/doc-uuid.pdf",
          "expires_in": 900
        }
      ]
    }
    ```

#### 2. Complete Document Upload
- `POST /api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{document_id}/complete`
  - Acknowledges that the browser successfully PUT the file to S3.
  - Response:
    ```json
    {
      "status": "success",
      "document_id": "doc-uuid",
      "document_status": "UPLOADED"
    }
    ```

#### 3. Finalize Upload Session
- `POST /api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize`
  - Closes the upload session and enqueues all confirmed documents into the SQS `fast-parse` work queue.
  - Response:
    ```json
    {
      "session_id": "session-uuid",
      "status": "FAST_PARSING",
      "total_queued": 40
    }
    ```

#### 4. Get Upload Session Status
- `GET /api/v2/jobs/{job_id}/upload-sessions/{session_id}`
  - Returns current session status, barrier progress, and document list.
  - Response:
    ```json
    {
      "session_id": "session-uuid",
      "job_id": "job-uuid",
      "status": "READY",
      "expected_count": 40,
      "uploaded_count": 40,
      "processed_count": 40,
      "failed_count": 0,
      "job_version": 1,
      "created_at": "2026-09-21T12:00:00Z",
      "updated_at": "2026-09-21T12:01:15Z"
    }
    ```

#### 5. Stream Session Progress (SSE)
- `GET /api/v2/jobs/{job_id}/upload-sessions/{session_id}/events`
  - Content-Type: `text/event-stream`
  - Streams durable DynamoDB lifecycle changes and document parsing progress.
  - Events:
    - `progress`: `{ document_id, status, candidate_name, processed, total }`
    - `complete`: `{ session_id, status: "READY" | "READY_WITH_WARNINGS" | "FAILED", total_succeeded, total_failed }`

#### 6. Upload Resumes (Legacy Multipart Compatibility Wrapper)
- `POST /api/v2/jobs/{job_id}/resumes` — Upload PDFs directly via multipart/form-data
  - Content-Type: `multipart/form-data`
  - Internal: Stores PDF directly to S3 and enqueues to SQS `fast-parse`.
  - Validation: PDF only, 10MB max, SHA-256 dedup
  - Response: `{ job_id, accepted[], rejected[], total_accepted }`

#### 7. Download Resume PDF
- `GET /api/v2/jobs/{job_id}/resumes/{document_id}/download`
  - Response: `application/pdf` stream

#### 8. Delete Resume
- `DELETE /api/v2/jobs/{job_id}/resumes/{document_id}`
  - Removes document from DynamoDB and S3.


### Scoring
- `POST /api/v2/jobs/{job_id}/score` — Score and rank candidates
  - Body: `{ weights: { skills, experience, keywords, education } }` (must sum to 100)
  - Response: `{ job_id, status, total_candidates, scoring_id, candidates: ScoredCandidate[] }`

- `GET /api/v2/jobs/{job_id}/results` — Get latest scoring results
  - Response: `{ job_id, status, total_candidates, candidates: ScoredCandidate[] }`

### Human Decisions (P1)
- `PATCH /api/v2/jobs/{job_id}/candidates/{document_id}/decision`
  - Body: `{ decision: HumanDecision, reason?: string, notes?: string, tags?: string[] }`
  - Reason is MANDATORY for REJECTED

- `GET /api/v2/jobs/{job_id}/candidates` — List candidates with filters
  - Query params: `signal`, `decision`, `search`, `sort`, `page`, `per_page`

### ATS Health Check
- `POST /api/v2/ats-check` — Standalone ATS check
  - Content-Type: multipart/form-data (single PDF)
  - Rate limited
  - Response includes parseability, sections, risks, fixes, extracted contacts
  - Uploaded file deleted after processing

### Export
- `GET /api/v2/jobs/{job_id}/export/csv` — Export candidates as CSV

### Audit Log (P0)
- `GET /api/v2/audit` — List audit events (admin only)
  - Query params: `resource_type`, `action`, `since`, `until`, `page`

## Error Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": {}
  }
}
```

## Rate Limits
- Upload: 10 requests/minute per org
- ATS Check: 5 requests/minute per IP
- Score: 5 requests/minute per org
- All others: 60 requests/minute per org
