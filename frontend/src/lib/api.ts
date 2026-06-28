/**
 * api.ts — Centralized API service layer
 * =========================================
 * EVERY backend call goes through this module.
 * No raw fetch() calls in components — ever.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// ── Internal fetch wrapper ──────────────────────────────────────────────────

interface ApiFetchOptions extends RequestInit {
  /** Timeout in milliseconds. Defaults to 30s. */
  timeoutMs?: number;
}

export class ApiError extends Error {
  status: number;
  body?: unknown;

  constructor(
    message: string,
    status: number,
    body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { timeoutMs = 30_000, ...fetchOpts } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchOpts,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
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
      throw new ApiError(
        `API ${res.status}: ${path}`,
        res.status,
        body,
      );
    }

    return (await res.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Public API functions ────────────────────────────────────────────────────

/** Health check — 3s timeout, used by BackendHealthGate */
export async function checkHealth(): Promise<{ status: string }> {
  return apiFetch('/health', { timeoutMs: 3_000 });
}

/** Create a new screening job */
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

export async function createJob(
  payload: CreateJobPayload,
): Promise<CreateJobResponse> {
  return apiFetch('/jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Update JD config for an existing job (PATCH merge) */
export async function updateJob(
  jobId: string,
  payload: Partial<CreateJobPayload>,
): Promise<{ id: string; config: CreateJobPayload; status: string }> {
  return apiFetch(`/jobs/${jobId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/** Upload resumes via XMLHttpRequest (supports upload progress) */
export interface UploadResult {
  job_id: string;
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  total_accepted: number;
}

export function uploadResumes(
  jobId: string,
  files: File[],
  onProgress?: (loaded: number, total: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();

    files.forEach((file) => formData.append('files', file));

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } catch {
          reject(new ApiError('Failed to parse upload response', xhr.status));
        }
      } else {
        let body: unknown;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          body = xhr.responseText;
        }
        reject(new ApiError(`Upload failed: ${xhr.status}`, xhr.status, body));
      }
    });

    xhr.addEventListener('error', () => {
      reject(new ApiError('Upload network error', 0));
    });

    xhr.addEventListener('abort', () => {
      reject(new ApiError('Upload aborted', 0));
    });

    xhr.open('POST', `${API_BASE}/jobs/${jobId}/resumes`);
    xhr.send(formData);
  });
}

/** Start SSE extraction stream */
export interface ExtractionEvent {
  type: string;
  current?: number;
  total?: number;
  filename?: string;
  status?: string;
  error?: string;
}

export function startExtraction(
  jobId: string,
  onEvent: (event: ExtractionEvent) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
): () => void {
  const eventSource = new EventSource(
    `${API_BASE}/jobs/${jobId}/extract`,
  );

  eventSource.addEventListener('progress', (e) => {
    try {
      const data = JSON.parse(e.data) as ExtractionEvent;
      onEvent(data);
    } catch {
      onError(new Error('Failed to parse SSE event'));
    }
  });

  eventSource.addEventListener('complete', (e) => {
    try {
      const data = JSON.parse(e.data) as ExtractionEvent;
      onEvent(data);
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

  // Return cleanup function
  return () => eventSource.close();
}

/** Score candidates */
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

export async function scoreJob(
  jobId: string,
  payload: ScorePayload,
): Promise<ScoreResponse> {
  return apiFetch(`/jobs/${jobId}/score`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
