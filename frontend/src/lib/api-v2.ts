import { ApiError } from './api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function apiFetchV2<T>(
  path: string,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 30_000, ...fetchOpts } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...fetchOpts,
      signal: controller.signal,
      headers: {
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

// --- Types ---
export interface AtsIssue {
  severity: 'moderate' | 'severe';
  message: string;
  fix_suggestion?: string;
  issue: string; // the sub-evaluator that flagged this
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
  signals: Record<string, string>; // e.g. {"Chronology": "moderate"}
  flags: AtsIssue[];
  bounding_boxes: BoundingBox[];
}

export interface V2CandidateListResponse {
  job_id: string;
  total_candidates: number;
  limit: number;
  cursor: number | null;
  candidates: Record<string, unknown>[]; // Basic candidate info
}

export interface V2CandidateDetailResponse {
  id: string;
  job_id: string;
  status: string;
  s3_pdf_key: string;
  url: string; // Presigned URL from backend
  ats_result: AtsResult;
  extraction?: {
    explicit_skills?: { name: string; provenance: string; confidence: number }[];
    // ...
  };
  score: number;
  skill_score: number;
  experience_score: number;
  education_score: number;
  semantic_score: number;
  // mapped into the frontend format
  [key: string]: unknown;
}

// --- Endpoints ---

export async function getCandidatesV2(
  jobId: string,
  limit: number = 20,
  cursor: number = 0
): Promise<V2CandidateListResponse> {
  return apiFetchV2(`/api/v2/jobs/${jobId}/candidates?limit=${limit}&cursor=${cursor}`);
}

export async function getCandidateDetailV2(
  jobId: string,
  candidateId: string
): Promise<V2CandidateDetailResponse> {
  return apiFetchV2(`/api/v2/jobs/${jobId}/candidates/${candidateId}`);
}

export async function runAtsCheck(file: File): Promise<AtsResult> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetchV2('/api/v2/ats-check', {
    method: 'POST',
    body: formData,
  });
}
