# 05 — API Layer

## Overview

The API is a FastAPI application serving HTTP/JSON endpoints and one SSE endpoint. All routes are defined in `src/api/routes/`. The application factory is in `src/api/app.py`.

**Base URL:** `http://localhost:8000`
**CORS:** Allows `http://localhost:5173` and `http://127.0.0.1:5173` (Vite dev server)

---

## Application Setup

```python
# src/api/app.py
app = FastAPI(
    title="Resume Intelligence Platform",
    version="0.1.0",
)
app.add_middleware(CORSMiddleware, ...)
app.include_router(health_router)                    # /health
app.include_router(jobs_router, prefix="/jobs")       # /jobs/*
```

**Server launch:** `uvicorn src.api.app:app --host 0.0.0.0 --port 8000`

---

## Endpoints

### `GET /health`

**Purpose:** Backend reachability check. Used by the frontend `BackendHealthGate` on app load.

**Response:** `{"status": "ok"}`

**Timeout:** Frontend uses 3s timeout for cold-start detection.

---

### `POST /jobs`

**Purpose:** Create a new screening job with JD configuration.

**Request Body:**
```json
{
  "title": "Backend Engineer",
  "department": "Engineering",
  "description": "We are looking for...",
  "must_have_skills": ["Python", "SQL"],
  "nice_to_have_skills": ["Docker", "AWS"],
  "min_years": 2,
  "max_years": 8,
  "education_level": "bachelor",
  "education_field": "Computer Science",
  "keywords": ["microservices", "API", "agile"]
}
```

**Response:**
```json
{
  "id": "uuid-string",
  "title": "Backend Engineer",
  "status": "created"
}
```

**Behavior:** Creates an in-memory job record in `_jobs` dict. No persistence.

---

### `PATCH /jobs/{job_id}`

**Purpose:** Update JD config for an existing job. Merges only supplied (non-None) fields.

**Request Body:** Same as POST but all fields optional.

**Response:**
```json
{
  "id": "uuid-string",
  "config": { ... },
  "status": "updated"
}
```

**Use case:** Frontend calls this right before analysis to sync the latest JD form state.

---

### `POST /jobs/{job_id}/resumes`

**Purpose:** Upload resume PDFs for a job.

**Request:** `multipart/form-data` with `files` field (multiple).

**Validation:**
| Check | Rule | Rejection Reason |
|-------|------|-----------------|
| Extension | Must be `.pdf` | "Not a PDF file" |
| Content type | Must be `application/pdf` | "Invalid content type" |
| Size | ≤ 10 MB | "File too large: XMB (max 10MB)" |
| Duplicate | SHA256 hash check | "Duplicate of 'filename' (SHA256 match)" |

**Response:**
```json
{
  "job_id": "uuid",
  "accepted": ["resume1.pdf", "resume2.pdf"],
  "rejected": [{"filename": "photo.jpg", "reason": "Not a PDF file"}],
  "total_accepted": 5
}
```

**File storage:** Files saved to `backend/uploads/{job_id}/{uuid8}_{filename}`.

---

### `GET /jobs/{job_id}/extract`

**Purpose:** Start extraction via Server-Sent Events stream.

**Response type:** `text/event-stream`

**Event types:**

#### `progress` event
```json
{
  "type": "extraction_progress",
  "current": 3,
  "total": 10,
  "filename": "resume_3.pdf",
  "status": "extracted"    // or "failed"
}
```

#### `complete` event
```json
{
  "type": "extraction_complete",
  "total": 10,
  "succeeded": 9,
  "failed": 1
}
```

#### `error` event
```json
{
  "error": "Job not found"
}
```

**Concurrency:** All PDFs are extracted concurrently via `asyncio.create_task()` + `asyncio.to_thread()`. Results stream to the client via an `asyncio.Queue`.

**Side effect:** Stores extracted candidate fields in `_jobs[id]["extracted_candidates"]`.

---

### `POST /jobs/{job_id}/score`

**Purpose:** Score and rank all extracted candidates against the JD.

**Request Body:**
```json
{
  "weights": {
    "skills": 40,
    "experience": 25,
    "keywords": 20,
    "education": 15
  }
}
```

**Validation:** Weights must sum to exactly 100.

**Weight conversion:** Frontend sends 0-100 integers; backend divides by 100 to get 0.0-1.0 fractions.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "scored",
  "total_candidates": 25,
  "weights_applied": {"skills": 40, "experience": 25, ...},
  "candidates": [ /* ScoredCandidate[] as dicts */ ],
  "debug_jd": { /* JobDescription as dict */ }
}
```

---

### `GET /jobs/{job_id}/results`

**Purpose:** Retrieve previously stored scoring results without re-running analysis.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "scored",
  "total_candidates": 25,
  "candidates": [ /* ScoredCandidate[] */ ]
}
```

---

## State Management

All state is **in-memory**. There is no database, no file-based persistence, no cache layer.

```python
_jobs: dict = {}  # job_id → { config, resumes, extracted_candidates, scored_results, ... }
```

**Implications:**
- Jobs are lost on server restart
- No multi-process scaling (state is per-process)
- No authentication or authorization

---

## Error Handling

| HTTP Status | When |
|-------------|------|
| 404 | Job ID not found in `_jobs` |
| 400 | No candidates extracted yet (scoring before extraction) |
| 400 | No scoring results available (results before scoring) |
| 422 | Validation error (weights don't sum to 100, missing required fields) |
| 500 | Extraction or scoring engine exception |
