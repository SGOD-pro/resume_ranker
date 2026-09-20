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

### Documents
- `POST /api/v2/jobs/{job_id}/resumes` — Upload PDFs
  - Content-Type: multipart/form-data
  - Validation: PDF only, 10MB max, SHA-256 dedup
  - Response: `{ job_id, accepted[], rejected[], total_accepted }`

- `GET /api/v2/jobs/{job_id}/extract` — SSE extraction progress
  - Content-Type: text/event-stream
  - Events: `progress { document_id, status, candidate_name }`, `complete { total, succeeded, failed }`, `error { message }`

- `GET /api/v2/jobs/{job_id}/resumes/{document_id}/download` — Download resume PDF
  - Response: `application/pdf` stream

- `DELETE /api/v2/jobs/{job_id}/resumes/{document_id}` — Delete specific resume

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
