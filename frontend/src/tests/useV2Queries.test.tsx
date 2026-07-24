/**
 * useV2Queries.test.tsx
 * =====================
 * Tests the React Query hooks in src/hooks/useV2Queries.ts.
 *
 * Strategy:
 *  - We use `renderHook` from @testing-library/react wrapped in a fresh
 *    QueryClientProvider for each test to prevent cache pollution.
 *  - MSW intercepts the underlying fetch calls.
 *  - We `waitFor` async state transitions (isLoading → isSuccess).
 */

import { describe, it, expect } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { http, HttpResponse } from 'msw';
import { server } from './mocks/server';
import {
  useJobCandidates,
  useCandidateDetail,
  useAtsCheck,
} from '@/hooks/useV2Queries';
import {
  MOCK_JOB_ID,
  MOCK_CANDIDATE_ID,
  MOCK_CANDIDATE_LIST,
  MOCK_CANDIDATE_DETAIL,
  MOCK_ATS_RESULT,
} from './mocks/handlers';
import { ApiError } from '@/lib/api';

// ── Test Utilities ───────────────────────────────────────────────────────────

/**
 * Creates a fresh QueryClient and wrapper for each test.
 * This prevents test-to-test cache leakage.
 */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // Disable retries in tests so errors surface immediately
        retry: false,
      },
    },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, wrapper };
}

// ── useJobCandidates ─────────────────────────────────────────────────────────

describe('useJobCandidates()', () => {
  it('is disabled and returns no data when jobId is null', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates(null), { wrapper });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('fetches candidates successfully for a valid jobId', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates(MOCK_JOB_ID), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const data = result.current.data;
    expect(data).toBeDefined();
    expect(data!.job_id).toBe(MOCK_JOB_ID);
    expect(data!.total_candidates).toBe(2);
    expect(data!.candidates).toHaveLength(2);
  });

  it('data matches the full V2CandidateListResponse interface', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates(MOCK_JOB_ID), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toStrictEqual(MOCK_CANDIDATE_LIST);
  });

  it('each candidate in the list has id, name, and signal fields', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates(MOCK_JOB_ID), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    for (const c of result.current.data!.candidates) {
      expect(c).toHaveProperty('id');
      expect(c).toHaveProperty('name');
      expect(c).toHaveProperty('signal');
    }
  });

  it('transitions to isError state when the API returns a 404', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates('non-existent-job'), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(404);
  });

  it('transitions to isError when the API returns a 500', async () => {
    server.use(
      http.get('http://localhost:8000/api/v2/jobs/:jobId/candidates', () => {
        return HttpResponse.json({ detail: 'DB is down' }, { status: 500 });
      }),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJobCandidates(MOCK_JOB_ID), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as ApiError).status).toBe(500);
  });
});

// ── useCandidateDetail ───────────────────────────────────────────────────────

describe('useCandidateDetail()', () => {
  it('is disabled and returns no data when both IDs are null', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCandidateDetail(null, null), { wrapper });

    expect(result.current.data).toBeUndefined();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('is disabled when jobId is provided but candidateId is null', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCandidateDetail(MOCK_JOB_ID, null), { wrapper });

    expect(result.current.fetchStatus).toBe('idle');
    expect(result.current.data).toBeUndefined();
  });

  it('fetches detail successfully for valid IDs', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const data = result.current.data;
    expect(data).toBeDefined();
    expect(data!.id).toBe(MOCK_CANDIDATE_ID);
    expect(data!.job_id).toBe(MOCK_JOB_ID);
  });

  it('data matches the full V2CandidateDetailResponse interface', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toStrictEqual(MOCK_CANDIDATE_DETAIL);
  });

  it('ats_result is present and has correct ats_score field', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data!.ats_result).toBeDefined();
    expect(result.current.data!.ats_result.ats_score).toBe(74.5);
  });

  it('ats_result.bounding_boxes is a non-empty array', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const boxes = result.current.data!.ats_result.bounding_boxes;
    expect(Array.isArray(boxes)).toBe(true);
    expect(boxes.length).toBeGreaterThan(0);
    expect(boxes[0]).toHaveProperty('x0');
    expect(boxes[0]).toHaveProperty('y0');
    expect(boxes[0]).toHaveProperty('x1');
    expect(boxes[0]).toHaveProperty('y1');
    expect(boxes[0]).toHaveProperty('page');
    expect(boxes[0]).toHaveProperty('issue');
  });

  it('ats_result.flags has AtsIssue with severity and fix_suggestion', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const flags = result.current.data!.ats_result.flags;
    expect(flags.length).toBeGreaterThan(0);
    const flag = flags[0];
    expect(['moderate', 'severe']).toContain(flag.severity);
    expect(typeof flag.message).toBe('string');
    if (flag.fix_suggestion) {
      expect(typeof flag.fix_suggestion).toBe('string');
    }
  });

  it('url field is a non-empty string (presigned URL)', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(typeof result.current.data!.url).toBe('string');
    expect(result.current.data!.url.length).toBeGreaterThan(0);
  });

  it('extraction.explicit_skills is a list of named skills', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const skills = result.current.data!.extraction?.explicit_skills;
    expect(Array.isArray(skills)).toBe(true);
    for (const s of skills!) {
      expect(typeof s.name).toBe('string');
      expect(typeof s.provenance).toBe('string');
      expect(s.confidence).toBeGreaterThanOrEqual(0);
      expect(s.confidence).toBeLessThanOrEqual(1);
    }
  });

  it('transitions to isError when candidate is not found', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useCandidateDetail(MOCK_JOB_ID, 'no-such-candidate'),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as ApiError).status).toBe(404);
  });
});

// ── useAtsCheck ──────────────────────────────────────────────────────────────

describe('useAtsCheck()', () => {
  it('starts as idle with no data', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    expect(result.current.isIdle).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('transitions through isPending to isSuccess after mutateAsync', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4 content'], 'resume.pdf', { type: 'application/pdf' });

    result.current.mutate(file);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.isPending).toBe(false);
  });

  it('returns AtsResult matching the full interface after success', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' });
    const data = await result.current.mutateAsync(file);

    expect(data).toStrictEqual(MOCK_ATS_RESULT);
  });

  it('ats_result from mutation has valid ats_score', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' });
    const data = await result.current.mutateAsync(file);

    expect(data.ats_score).toBeGreaterThanOrEqual(0);
    expect(data.ats_score).toBeLessThanOrEqual(100);
  });

  it('ats_result.signals contains string evaluator names mapped to string statuses', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' });
    const data = await result.current.mutateAsync(file);

    expect(typeof data.signals).toBe('object');
    for (const [key, val] of Object.entries(data.signals)) {
      expect(typeof key).toBe('string');
      expect(typeof val).toBe('string');
    }
  });

  it('ats_result.bounding_boxes is a valid array of coordinate objects', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' });
    const data = await result.current.mutateAsync(file);

    expect(Array.isArray(data.bounding_boxes)).toBe(true);
    for (const box of data.bounding_boxes) {
      expect(typeof box.x0).toBe('number');
      expect(typeof box.y0).toBe('number');
      expect(typeof box.x1).toBe('number');
      expect(typeof box.y1).toBe('number');
      expect(typeof box.page).toBe('number');
      expect(typeof box.issue).toBe('string');
      expect(box.x1).toBeGreaterThan(box.x0);
      expect(box.y1).toBeGreaterThan(box.y0);
    }
  });

  it('ats_result.flags is an array of AtsIssue objects with required fields', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    const file = new File(['%PDF-1.4'], 'resume.pdf', { type: 'application/pdf' });
    const data = await result.current.mutateAsync(file);

    expect(Array.isArray(data.flags)).toBe(true);
    for (const flag of data.flags) {
      expect(['moderate', 'severe']).toContain(flag.severity);
      expect(typeof flag.issue).toBe('string');
      expect(typeof flag.message).toBe('string');
      // fix_suggestion is optional; if present, must be a string
      if (flag.fix_suggestion !== undefined) {
        expect(typeof flag.fix_suggestion).toBe('string');
      }
    }
  });

  it('transitions to isError state when the API returns 422', async () => {
    server.use(
      http.post('http://localhost:8000/api/v2/ats-check', () => {
        return HttpResponse.json({ detail: 'No file provided' }, { status: 422 });
      }),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    let caughtError: unknown;
    try {
      const file = new File([], 'bad.pdf');
      await result.current.mutateAsync(file);
    } catch (e) {
      caughtError = e;
    }

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(caughtError).toBeInstanceOf(ApiError);
    expect((caughtError as ApiError).status).toBe(422);
  });

  it('transitions to isError state when the API returns 500', async () => {
    server.use(
      http.post('http://localhost:8000/api/v2/ats-check', () => {
        return HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 });
      }),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useAtsCheck(), { wrapper });

    let caughtError: unknown;
    try {
      const file = new File(['%PDF-1.4'], 'crash.pdf');
      await result.current.mutateAsync(file);
    } catch (e) {
      caughtError = e;
    }

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((caughtError as ApiError).status).toBe(500);
  });
});
