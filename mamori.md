# Mamori: Memory Bridge from V1 to V2

## 1. V1 API Endpoints

All backend calls in V1 go through the central `frontend/src/lib/api.ts` which connects to the FastAPI backend defined primarily in `backend/src/api/routes/jobs.py`.

- **`POST /jobs`**
  - **Request:** `CreateJobRequest` (title, department, description, skills, etc.)
  - **Response:** `CreateJobResponse` (id, title, status: "created")
  - **Description:** Creates a new screening job and stores metadata in DynamoDB.

- **`PATCH /jobs/{id}`**
  - **Request:** `UpdateJobRequest` (Partial JD fields)
  - **Response:** `{ id, config, status: "updated" }`
  - **Description:** Partial update for a job's JD config. Merges non-None fields into the stored config.

- **`POST /jobs/{id}/resumes`**
  - **Request:** `multipart/form-data` with `files` (PDFs)
  - **Response:** `UploadResponse` (job_id, accepted list, rejected list, total_accepted)
  - **Description:** Server-side validation for PDFs, 10MB limit, deduplication via SHA256. Uploads to S3 and DynamoDB.

- **`GET /jobs/{id}/extract`**
  - **Response:** Server-Sent Events (SSE) stream (`text/event-stream`)
  - **Description:** Real-time extraction progress stream. Yields `progress` and `complete` events containing extraction status per file and overall totals.

- **`POST /jobs/{id}/score`**
  - **Request:** `ScoreRequest` (weights dict: skills, experience, keywords, education summing to 100)
  - **Response:** `{ job_id, status, total_candidates, weights_applied, candidates }`
  - **Description:** Loads extracted JSON from S3, runs `CandidateScorer.rank()`, uploads results to S3, and returns the full ranked list.

- **`GET /jobs/{id}/results`**
  - **Response:** `{ job_id, status, total_candidates, candidates }`
  - **Description:** Retrieves the latest scoring results from S3 for a given job.

- **`GET /jobs/{id}/resumes/{document_id}/download`**
  - **Response:** `application/pdf` stream
  - **Description:** Downloads a resume PDF from S3.

## 2. V1 Frontend Data Flow

The frontend relies heavily on **Zustand** stores for state management, specifically separating global app UI state from candidate domain state.

- **`app-store.ts`:** Manages the overall application UI state, including `appPhase` (idle, uploading, extracting, scoring, complete), `backendStatus`, global `uploadProgress` tracking, and blocking errors.
- **`candidate-store.ts`:** Manages the domain data. It stores the `candidates` array, `selectedId`, and filtering/sorting configurations (`filterSignal`, `sortField`, `searchQuery`, `showKnockouts`).
- **Data Flow:** The application triggers API calls via `api.ts`. During scoring, a `POST /jobs/{id}/score` is dispatched. The JSON response containing the array of candidates is received, and the frontend updates the `candidate-store.ts` via `setCandidates()`. 
- **View Layer:** `CandidateListPanel.tsx` uses a memoized selector to pull `candidates` from the `useCandidateStore`. It filters (by signal/knockout status/search query) and sorts (by score or name) the candidates on the client side, then renders a virtualized list of `CandidateRow` components.

## 3. V1 Extraction Flow

The extraction is performed synchronously on the backend, triggered via the SSE endpoint `GET /jobs/{id}/extract`.

- **Trigger:** Frontend opens an `EventSource` connection to the extract endpoint.
- **Processing:** The backend loads all document metadata from DynamoDB, downloads the PDFs from S3 to temporary local files, and processes them concurrently using `asyncio.to_thread()`.
- **Extraction:** Each thread calls `_extract_single_sync()`, which delegates to the `ExtractionService` singleton, invoking `PDFPipelineV3.extract()` to parse the PDF (likely using PyMuPDF and regexes under the hood).
- **Persistence:** Extracted structured data is uploaded back to S3 as JSON, and document metadata is updated in DynamoDB.
- **Streaming:** The router yields `progress` SSE events as individual files succeed or fail, and a final `complete` event when all threads finish.

## 4. V1 Scoring Logic

The scoring engine lives in a monolithic God-class `CandidateScorer` inside `backend/src/ranking/scorer.py`. It executes a 3-Phase ranking pipeline on the extracted data:

- **Phase 1: Hard Knockout:** Filters candidates based on hard constraints (e.g., must-have skills, minimum years of experience, required degree level). Inference matching is run *before* this so inferred skills can satisfy must-haves. Candidates failing this phase are marked with `knocked_out = True` and pushed to the bottom of the rankings.
- **Phase 2: Multi-Signal Scoring:** Computes individual sub-scores that are later weighted and summed:
  - **Skill Scoring:** Uses BM25 with Inference weighting. Includes domain classification penalties (e.g., penalizing healthcare candidates for engineering roles).
  - **Experience Scoring:** Base years matched against JD criteria.
  - **Keyword Scoring:** Simple presence/absence.
  - **Education Scoring:** Degree level mapping (e.g., Masters > Bachelors).
  - **Bonus Points:** Project-skill match (up to 5.0), prestigious companies (up to 4.0), and certifications/hackathons (up to 5.0).
- **Phase 3: Rank & Explain:** Sorts all candidates by `final_score` descending (with knockouts placed last), assigns integer ranks, and computes relative percentiles. The final weighted score is capped at 100.