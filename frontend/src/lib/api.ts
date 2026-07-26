/**
 * api.ts — Centralized API service layer
 * =========================================
 * Single source of truth for all backend calls.
 * All routes use /api/v2. No raw fetch() in components.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// ── Error class ─────────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  body?: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

// ── Internal fetch wrapper ──────────────────────────────────────────────────

interface ApiFetchOptions extends RequestInit {
  /** Timeout in milliseconds. Defaults to 30s. */
  timeoutMs?: number;
}

async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { timeoutMs = 30_000, ...fetchOpts } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchOpts,
      signal: controller.signal,
      headers: {
        // Don't set Content-Type for FormData — browser sets it with boundary
        ...(fetchOpts.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...fetchOpts.headers,
      },
    });

    if (!res.ok) {
      let body: unknown;
      try {
        body = await res.json();
      } catch {
        body = await res.text();
      }
      throw new ApiError(`API ${res.status}: ${path}`, res.status, body);
    }

    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface CreateJobPayload {
  title: string;
  department?: string;
  description?: string;
  must_have_skills?: string[];
  nice_to_have_skills?: string[];
  min_years?: number;
  max_years?: number;
  education_level?: string;
  education_field?: string;
  keywords?: string[];
}

export interface CreateJobResponse {
  id: string;
  title: string;
  status: string;
}

export interface UploadResult {
  job_id: string;
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  total_accepted: number;
}

export interface ExtractionEvent {
  type: string;
  current?: number;
  total?: number;
  filename?: string;
  status?: string;
  error?: string;
}

export interface ScorePayload {
  weights: Record<string, number>;
}

export interface ScoreResponse {
  job_id: string;
  status: string;
  total_candidates: number;
  weights_applied: Record<string, number>;
  candidates: Record<string, unknown>[];
}

export interface AtsIssue {
  severity: 'moderate' | 'severe';
  message: string;
  fix_suggestion?: string;
  issue: string;
}

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page: number;
  issue: string;
}

export interface AtsResult {
  ats_score: number;
  signals: Record<string, string>;
  flags: AtsIssue[];
  bounding_boxes: BoundingBox[];
}

export interface CandidateListResponse {
  job_id: string;
  total_candidates: number;
  limit: number;
  cursor: number | null;
  candidates: Record<string, unknown>[];
}

export interface CandidateDetailResponse {
  id: string;
  job_id: string;
  status: string;
  s3_pdf_key: string;
  url: string;
  ats_result: AtsResult;
  extraction?: {
    explicit_skills?: { name: string; provenance: string; confidence: number }[];
  };
  score: number;
  skill_score: number;
  experience_score: number;
  education_score: number;
  semantic_score: number;
  [key: string]: unknown;
}

// ── Endpoints ───────────────────────────────────────────────────────────────

/** Health check */
export async function checkHealth(): Promise<{ status: string }> {
  return apiFetch('/api/v2/health', { timeoutMs: 5_000 });
}

/** Create a new screening job */
export async function createJob(payload: CreateJobPayload): Promise<CreateJobResponse> {
  return apiFetch('/api/v2/jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Update JD config for an existing job (PATCH merge) */
export async function updateJob(
  jobId: string,
  payload: Partial<CreateJobPayload>,
): Promise<{ id: string; config: CreateJobPayload; status: string }> {
  return apiFetch(`/api/v2/jobs/${jobId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/** Upload resume PDFs (multipart/form-data) */
export async function uploadResumes(
  jobId: string,
  files: File[],
  onProgress?: (loaded: number, total: number) => void,
): Promise<UploadResult> {
  const total = files.length;
  if (onProgress) onProgress(0, total);

  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file, file.name);
  }

  const result = await apiFetch<UploadResult>(`/api/v2/jobs/${jobId}/resumes`, {
    method: 'POST',
    body: formData,
    timeoutMs: 120_000, // 2 min for large batches
  });

  if (onProgress) onProgress(total, total);
  return result;
}

/** Start SSE extraction stream — returns a cleanup/close function */
export function startExtraction(
  jobId: string,
  onEvent: (event: ExtractionEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
): () => void {
  const eventSource = new EventSource(`${API_BASE}/api/v2/jobs/${jobId}/extract`);

  eventSource.addEventListener('progress', (e) => {
    try {
      onEvent(JSON.parse(e.data) as ExtractionEvent);
    } catch {
      onError(new Error('Failed to parse SSE event'));
    }
  });

  eventSource.addEventListener('complete', (e) => {
    try {
      onEvent(JSON.parse(e.data) as ExtractionEvent);
    } catch {
      // ignore parse error on complete
    }
    eventSource.close();
    onComplete();
  });

  eventSource.addEventListener('error', (e) => {
    try {
      const data = JSON.parse((e as MessageEvent).data) as ExtractionEvent;
      onError(new Error(data.error || 'SSE error'));
    } catch {
      onError(new Error('SSE connection lost'));
    }
    eventSource.close();
  });

  eventSource.onerror = () => {
    onError(new Error('SSE connection lost'));
    eventSource.close();
  };

  return () => eventSource.close();
}

/** Score and rank candidates */
export async function scoreJob(jobId: string, payload: ScorePayload): Promise<ScoreResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/score`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** List candidates for a job */
export async function getCandidates(
  jobId: string,
  limit = 20,
  cursor = 0,
): Promise<CandidateListResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/candidates?limit=${limit}&cursor=${cursor}`);
}

/** Get full detail for a single candidate */
export async function getCandidateDetail(
  jobId: string,
  candidateId: string,
): Promise<CandidateDetailResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/candidates/${candidateId}`);
}

/** Run ATS check on a PDF file */
export async function runAtsCheck(file: File): Promise<AtsResult> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetch('/api/v2/ats-check', {
    method: 'POST',
    body: formData,
  });
}
