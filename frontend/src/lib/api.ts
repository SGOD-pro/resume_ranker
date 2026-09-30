/**
 * api.ts — Centralized API service layer
 * =========================================
 * Implements Phase 2 Frontend API Contract:
 * - Direct-to-S3 presigned POST uploads (zero multipart backend file ingestion)
 * - Immediate fast-path Stage 1 extraction in the background
 * - Polling GET /api/v2/jobs/{job_id}/status with ETag and 304 Not Modified
 * - Barrier trigger: POST /api/v2/jobs/{job_id}/analyze with explicit file_ids
 * - Final candidate rankings: GET /api/v2/jobs/{job_id}/results
 * - Zero WebSockets, Zero SSE.
 */

import type {
  AtsCheckResponse,
  CreateJobFileSpec,
  CreateJobResponseV2,
  CreateJobFileResponse,
  PresignedPostInfo,
  JobStatusResponse,
  AnalyzeResponseV2,
  JobFileStatus,
} from '@/store/types';

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
  const { timeoutMs = 120_000, ...fetchOpts } = options;

  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new Error(`Request to ${path} timed out after ${timeoutMs}ms`)),
    timeoutMs,
  );

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

/** Create job payload */
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
  weights?: Record<string, number>;
  files?: CreateJobFileSpec[];
}

/** Create a new screening job */
export async function createJob(
  payload: CreateJobPayload,
): Promise<CreateJobResponseV2> {
  return apiFetch('/api/v2/jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Initialize a job with file specifications to receive direct S3 presigned POST parameters.
 */
export async function createJobWithUploads(
  payload: Omit<CreateJobPayload, 'files'>,
  files: File[],
): Promise<CreateJobResponseV2> {
  const fileSpecs: CreateJobFileSpec[] = files.map((f) => ({
    filename: f.name,
    file_size: f.size,
  }));
  return apiFetch('/api/v2/jobs', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      files: fileSpecs,
    }),
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

// ── Direct S3 Upload via Presigned POST ──────────────────────────────────────

/**
 * Direct upload of a single File object to S3 via presigned POST fields.
 * S3 responds with HTTP 204 No Content.
 */
export async function uploadFileViaPresignedPost(
  file: File,
  presignedPost: PresignedPostInfo,
): Promise<void> {
  const formData = new FormData();
  Object.entries(presignedPost.fields).forEach(([k, v]) => {
    formData.append(k, v);
  });
  formData.append('file', file);

  const res = await fetch(presignedPost.url, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok && res.status !== 204 && res.status !== 200) {
    throw new Error(`S3 direct upload failed with HTTP ${res.status}`);
  }
}

export interface UploadResult {
  job_id: string;
  accepted: string[];
  rejected: { filename: string; reason: string }[];
  total_accepted: number;
  fileIdMap: Record<string, string>;
}

/**
 * Direct browser-to-S3 upload with bounded client concurrency of 4.
 * Uses presigned POST parameters returned during job creation.
 */
export async function uploadFilesDirectToS3(
  jobId: string,
  files: File[],
  presignedFiles: CreateJobFileResponse[],
  onProgress?: (uploaded: number, total: number, filename: string) => void,
): Promise<UploadResult> {
  if (files.length === 0) {
    return { job_id: jobId, accepted: [], rejected: [], total_accepted: 0, fileIdMap: {} };
  }

  const fileMap = new Map<string, File>();
  files.forEach((f) => fileMap.set(f.name, f));

  const fileIdMap: Record<string, string> = {};
  presignedFiles.forEach((pf) => {
    fileIdMap[pf.filename] = pf.file_id;
  });

  const accepted: string[] = [];
  const rejected: { filename: string; reason: string }[] = [];
  let completedCount = 0;

  const CONCURRENCY = 4;
  let nextIndex = 0;

  const uploadWorker = async () => {
    while (nextIndex < presignedFiles.length) {
      const idx = nextIndex++;
      const fileInfo = presignedFiles[idx];
      const file = fileMap.get(fileInfo.filename);

      if (!file) {
        rejected.push({ filename: fileInfo.filename, reason: 'Local file handle not found' });
        completedCount++;
        onProgress?.(completedCount, presignedFiles.length, fileInfo.filename);
        continue;
      }

      try {
        await uploadFileViaPresignedPost(file, fileInfo.presigned_post);
        accepted.push(fileInfo.filename);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Upload failed';
        rejected.push({ filename: fileInfo.filename, reason: msg });
      } finally {
        completedCount++;
        onProgress?.(completedCount, presignedFiles.length, fileInfo.filename);
      }
    }
  };

  const workers = Array.from(
    { length: Math.min(CONCURRENCY, presignedFiles.length) },
    () => uploadWorker(),
  );
  await Promise.all(workers);

  return {
    job_id: jobId,
    accepted,
    rejected,
    total_accepted: accepted.length,
    fileIdMap,
  };
}

/**
 * Upload files via Frontend -> Backend -> S3 (POST /api/v2/jobs/{job_id}/resumes).
 * Tracks real-time upload progress with true byte-level precision using XMLHttpRequest.
 * Sends files in bounded batches (up to 25 files per request) to maximize throughput.
 * Completely eliminates raw AWS S3 URLs in the browser network tab.
 */
export async function uploadResumesToBackend(
  jobId: string,
  files: File[],
  onProgress?: (uploaded: number, total: number, filename: string, percent?: number) => void,
): Promise<UploadResult> {
  if (files.length === 0) {
    return { job_id: jobId, accepted: [], rejected: [], total_accepted: 0, fileIdMap: {} };
  }

  const accepted: string[] = [];
  const rejected: { filename: string; reason: string }[] = [];
  const fileIdMap: Record<string, string> = {};

  const totalBytes = files.reduce((sum, f) => sum + f.size, 0) || 1;
  let previouslyUploadedBytes = 0;
  let totalProcessedFiles = 0;

  // Chunk files into batches of 25 to remain well within multipart limits
  const BATCH_SIZE = 25;
  const batches: File[][] = [];
  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    batches.push(files.slice(i, i + BATCH_SIZE));
  }

  for (const batch of batches) {
    const batchBytes = batch.reduce((sum, f) => sum + f.size, 0) || 1;

    await new Promise<void>((resolve) => {
      const formData = new FormData();
      batch.forEach((f) => formData.append('files', f));

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}/api/v2/jobs/${jobId}/resumes`, true);
      xhr.withCredentials = true;

      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable) {
          const currentBatchLoaded = evt.loaded;
          const totalLoaded = previouslyUploadedBytes + currentBatchLoaded;
          const overallPercent = Math.min(
            99,
            Math.max(1, Math.round((totalLoaded / totalBytes) * 100)),
          );
          const currentEstimatedFiles = Math.min(
            files.length,
            Math.max(
              totalProcessedFiles,
              Math.round((totalLoaded / totalBytes) * files.length),
            ),
          );
          const activeFile = batch[Math.min(batch.length - 1, Math.floor((evt.loaded / batchBytes) * batch.length))];
          onProgress?.(currentEstimatedFiles, files.length, activeFile ? activeFile.name : 'Uploading...', overallPercent);
        }
      };

      xhr.onload = () => {
        previouslyUploadedBytes += batchBytes;
        totalProcessedFiles += batch.length;

        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.accepted && Array.isArray(data.accepted)) {
              accepted.push(...data.accepted);
            }
            if (data.rejected && Array.isArray(data.rejected)) {
              rejected.push(...data.rejected);
            }
            if (data.file_id_map && typeof data.file_id_map === 'object') {
              Object.assign(fileIdMap, data.file_id_map);
            }
          } catch {
            batch.forEach((f) => accepted.push(f.name));
          }
        } else {
          let errorMsg = `HTTP ${xhr.status}`;
          try {
            const data = JSON.parse(xhr.responseText);
            errorMsg = data.detail || errorMsg;
          } catch {
            // ignore
          }
          batch.forEach((f) => rejected.push({ filename: f.name, reason: errorMsg }));
        }

        const overallPercent = Math.min(
          100,
          Math.round((totalProcessedFiles / files.length) * 100),
        );
        onProgress?.(totalProcessedFiles, files.length, batch[batch.length - 1].name, overallPercent);
        resolve();
      };

      xhr.onerror = () => {
        previouslyUploadedBytes += batchBytes;
        totalProcessedFiles += batch.length;
        batch.forEach((f) => rejected.push({ filename: f.name, reason: 'Network upload error' }));
        const overallPercent = Math.min(
          100,
          Math.round((totalProcessedFiles / files.length) * 100),
        );
        onProgress?.(totalProcessedFiles, files.length, 'Upload error', overallPercent);
        resolve();
      };

      xhr.send(formData);
    });
  }

  // Final 100% update
  onProgress?.(files.length, files.length, 'All files uploaded successfully', 100);

  return {
    job_id: jobId,
    accepted,
    rejected,
    total_accepted: accepted.length,
    fileIdMap,
  };
}

/** Notify backend that direct-to-S3 uploads have completed so PyMuPDF starts immediately in background */
export async function notifyFilesUploaded(
  jobId: string,
  fileIds?: string[],
): Promise<void> {
  await apiFetch(`/api/v2/jobs/${jobId}/files/uploaded`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  }).catch((err) => {
    console.warn('Could not notify files uploaded:', err);
  });
}

// ── Real-Time Server-Sent Events (SSE) Stream ───────────────────────────────

export interface ExtractionStreamPayload {
  job_id?: string;
  job_status?: string;
  status?: string;
  total_files?: number;
  remaining?: number;
  usable_files?: number;
  succeeded?: number;
  failed?: number;
  analyze_requested?: boolean;
  is_stalled?: boolean;
  files?: JobFileStatus[];
}

export interface ExtractionStreamCallbacks {
  onProgress?: (data: ExtractionStreamPayload) => void;
  onComplete?: (data: { status?: string; total?: number; usable?: number }) => void;
  onError?: (err: Error) => void;
}

/**
 * Connect to real-time SSE stream for job progress.
 * Eliminates repeated short-polling and network spam.
 * Returns unsubscribe function to close the stream.
 */
export function subscribeToJobExtraction(
  jobId: string,
  callbacks: ExtractionStreamCallbacks,
): () => void {
  const url = `${API_BASE}/api/v2/jobs/${jobId}/extract`;
  const es = new EventSource(url, { withCredentials: true });

  es.addEventListener('progress', (e) => {
    try {
      const data = JSON.parse(e.data) as ExtractionStreamPayload;
      callbacks.onProgress?.(data);
    } catch {
      // ignore
    }
  });

  es.addEventListener('complete', (e) => {
    try {
      const data = JSON.parse(e.data);
      callbacks.onComplete?.(data);
    } catch {
      callbacks.onComplete?.({});
    }
    es.close();
  });

  es.addEventListener('error', () => {
    callbacks.onError?.(new Error('SSE connection error'));
  });

  return () => {
    es.close();
  };
}

// ── Short-Polling Job Status with ETag ───────────────────────────────────────

export interface PollStatusResult {
  notModified: boolean;
  status?: JobStatusResponse;
  etag: string | null;
}

/**
 * Poll job status passing If-None-Match header.
 * Returns notModified=true on HTTP 304 to eliminate redundant re-renders and bandwidth.
 */
export async function pollJobStatus(
  jobId: string,
  currentEtag?: string | null,
): Promise<PollStatusResult> {
  const headers: Record<string, string> = {};
  if (currentEtag) {
    headers['If-None-Match'] = currentEtag;
  }

  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new Error(`Status check for job ${jobId} timed out`)),
    30_000,
  );

  try {
    const res = await fetch(`${API_BASE}/api/v2/jobs/${jobId}/status`, {
      method: 'GET',
      headers,
      signal: controller.signal,
    });

    const newEtag = res.headers.get('ETag');

    if (res.status === 304) {
      return { notModified: true, etag: newEtag || currentEtag || null };
    }

    if (!res.ok) {
      let body: unknown;
      try {
        body = await res.json();
      } catch {
        body = await res.text();
      }
      throw new ApiError(`Status check ${res.status}`, res.status, body);
    }

    const data = (await res.json()) as JobStatusResponse;
    return { notModified: false, status: data, etag: newEtag };
  } finally {
    clearTimeout(timeout);
  }
}

// ── Trigger Analysis Barrier ────────────────────────────────────────────────

export interface TriggerAnalysisPayload {
  title?: string;
  department?: string;
  description?: string;
  must_have_skills?: string[];
  nice_to_have_skills?: string[];
  min_years?: number;
  max_years?: number;
  education_level?: string;
  education_field?: string;
  keywords?: string[];
  weights?: Record<string, number>;
  file_ids?: string[];
}

/**
 * Trigger analysis barrier with explicit file IDs and finalized job criteria.
 */
export async function triggerAnalysis(
  jobId: string,
  payload: TriggerAnalysisPayload,
): Promise<AnalyzeResponseV2> {
  return apiFetch(`/api/v2/jobs/${jobId}/analyze`, {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 120_000,
  });
}

// ── Final Candidate Results ─────────────────────────────────────────────────

export interface ResultsResponse {
  job_id: string;
  status: string;
  total_candidates: number;
  weights?: Record<string, number>;
  candidates: Record<string, unknown>[];
}

/** Retrieve stored final scoring results */
export async function getResults(jobId: string): Promise<ResultsResponse> {
  return apiFetch(`/api/v2/jobs/${jobId}/results`, {
    timeoutMs: 120_000,
  });
}

// ── Auxiliary Endpoints ─────────────────────────────────────────────────────

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
  payload: { decision?: string; reason?: string; note?: string; tags?: string[] },
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
