/**
 * api.ts — Centralized API service layer
 * =========================================
 * EVERY backend call goes through this module.
 * No raw fetch() calls in components — ever.
 */

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

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

/** Upload resumes one file at a time so progress can be tracked per-file.
 *
 * onFileComplete(uploadedCount, totalCount, filename) is called after each
 * individual file is accepted or rejected by the server — this drives the
 * "X of Y" progress bar correctly instead of tracking raw bytes.
 */
export interface UploadResult {
  job_id: string;
  session_id?: string;
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  total_accepted: number;
}

export interface UploadSessionFileSpec {
  filename: string;
  file_size: number;
  content_type?: string;
}

export interface DocumentPresignedUrlInfo {
  document_id: string;
  filename: string;
  s3_key: string;
  presigned_url: string;
}

export interface CreateUploadSessionResponse {
  session_id: string;
  job_id: string;
  job_version: number;
  expected_document_count: number;
  documents: DocumentPresignedUrlInfo[];
}

export interface CompleteDocumentUploadResponse {
  document_id: string;
  session_id: string;
  job_id: string;
  status: string;
}

export interface FinalizeUploadSessionResponse {
  session_id: string;
  job_id: string;
  status: string;
  message: string;
}

export interface UploadSessionProgressResponse {
  session_id: string;
  job_id: string;
  job_version: number;
  status: string;
  expected_document_count: number;
  uploaded_document_count: number;
  fast_parsed_count: number;
  terminal_count: number;
  documents: Array<{
    document_id: string;
    filename: string;
    status: string;
    candidate_name?: string;
    identity_status?: string;
    extraction_quality?: string;
    fallback_reason?: string;
    error_reason?: string;
  }>;
}

/** Create a durable upload session with presigned S3 PUT URLs */
export async function createUploadSession(
  jobId: string,
  files: UploadSessionFileSpec[],
): Promise<CreateUploadSessionResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/upload-sessions`, {
    method: 'POST',
    body: JSON.stringify({
      document_count: files.length,
      files,
    }),
  });
}

/** Notify backend that an individual document finished uploading to S3 */
export async function completeDocumentUpload(
  jobId: string,
  sessionId: string,
  documentId: string,
): Promise<CompleteDocumentUploadResponse> {
  return apiFetch(
    `/api/v2/jobs/${jobId}/upload-sessions/${sessionId}/documents/${documentId}/complete`,
    {
      method: 'POST',
    },
  );
}

/** Finalize the upload session barrier */
export async function finalizeUploadSession(
  jobId: string,
  sessionId: string,
): Promise<FinalizeUploadSessionResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/upload-sessions/${sessionId}/finalize`, {
    method: 'POST',
  });
}

/** Poll upload session progress */
export async function getUploadSession(
  jobId: string,
  sessionId: string,
): Promise<UploadSessionProgressResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/upload-sessions/${sessionId}`);
}

/**
 * Direct browser-to-S3 upload with bounded client concurrency of 4.
 * Uses presigned PUT URLs, notifies backend upon each document completion,
 * and sets the finalization barrier.
 */
export async function uploadFilesDirectToS3(
  jobId: string,
  files: File[],
  onProgress?: (uploaded: number, total: number, filename: string) => void,
): Promise<UploadResult> {
  if (files.length === 0) {
    return { job_id: jobId, accepted: [], rejected: [], total_accepted: 0 };
  }

  // 1. Request presigned PUT URLs for the batch
  const fileSpecs: UploadSessionFileSpec[] = files.map((f) => ({
    filename: f.name,
    file_size: f.size,
    content_type: f.type || 'application/pdf',
  }));

  const sessionRes = await createUploadSession(jobId, fileSpecs);
  const { session_id, documents } = sessionRes;

  const docMap = new Map<string, DocumentPresignedUrlInfo>();
  documents.forEach((d) => docMap.set(d.filename, d));

  const accepted: string[] = [];
  const rejected: { filename: string; reason: string }[] = [];
  let completedCount = 0;

  // 2. Upload directly to S3 with bounded concurrency of 4
  const CONCURRENCY = 4;
  let nextIndex = 0;

  const uploadWorker = async () => {
    while (nextIndex < files.length) {
      const idx = nextIndex++;
      const file = files[idx];
      const docInfo = docMap.get(file.name);

      if (!docInfo) {
        rejected.push({ filename: file.name, reason: 'Session document info missing' });
        completedCount++;
        onProgress?.(completedCount, files.length, file.name);
        continue;
      }

      try {
        const putRes = await fetch(docInfo.presigned_url, {
          method: 'PUT',
          body: file,
          headers: {
            'Content-Type': 'application/pdf',
          },
        });

        if (!putRes.ok) {
          throw new Error(`S3 upload failed with HTTP ${putRes.status}`);
        }

        await completeDocumentUpload(jobId, session_id, docInfo.document_id);
        accepted.push(file.name);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Upload failed';
        rejected.push({ filename: file.name, reason: msg });
      } finally {
        completedCount++;
        onProgress?.(completedCount, files.length, file.name);
      }
    }
  };

  const workers = Array.from({ length: Math.min(CONCURRENCY, files.length) }, () =>
    uploadWorker(),
  );
  await Promise.all(workers);

  // 3. Finalize upload session barrier
  try {
    await finalizeUploadSession(jobId, session_id);
  } catch (err) {
    console.error('Failed to finalize upload session:', err);
  }

  return {
    job_id: jobId,
    session_id,
    accepted,
    rejected,
    total_accepted: accepted.length,
  };
}

/**
 * Upload resumes using direct S3 presigned URLs.
 * Maintains compatibility with existing callers.
 */
export async function uploadResumes(
  jobId: string,
  files: File[],
  onFileComplete?: (uploaded: number, total: number, filename: string) => void,
): Promise<UploadResult> {
  return uploadFilesDirectToS3(jobId, files, onFileComplete);
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
    `${API_BASE}/api/v2/jobs/${jobId}/extract`,
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
  return apiFetch(`/api/v2/jobs/${jobId}/score`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

import type { AtsCheckResponse } from '@/store/types';

/** Run B2B ATS Health Check on a resume PDF */
export async function checkAts(file: File): Promise<AtsCheckResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/api/v2/jobs/ats-check`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    let errorMsg = 'Failed to run ATS check';
    try {
      const err = await res.json();
      errorMsg = err.detail || errorMsg;
    } catch {
      // ignore json parse error
    }
    throw new ApiError(errorMsg, res.status);
  }
  return res.json();
}

/** Update human decision for candidate (P1 workflow) */
export async function updateCandidateDecision(
  jobId: string,
  documentId: string,
  payload: { decision: string; reason?: string; note?: string; tags?: string[] },
): Promise<Record<string, unknown>> {
  return apiFetch(`/api/v2/jobs/${jobId}/candidates/${documentId}/decision`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/** Export candidate rankings as CSV */
export async function exportCandidatesCsv(jobId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v2/jobs/${jobId}/export/csv`, {
    method: 'GET',
    headers: {
      Accept: 'text/csv',
    },
  });
  if (!res.ok) {
    throw new ApiError(`CSV Export failed: ${res.statusText}`, res.status);
  }
  return res.text();
}
