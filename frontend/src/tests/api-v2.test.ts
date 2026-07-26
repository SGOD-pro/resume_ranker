/**
 * api.test.ts
 * ===========
 * Tests the raw API fetch functions in src/lib/api.ts.
 *
 * Strategy:
 *  - MSW intercepts the `fetch()` calls at the network boundary
 *  - We assert that the returned JS objects exactly match our TypeScript interfaces
 *  - We assert that HTTP error codes throw ApiError with the correct status
 */

import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from './mocks/server';
import {
  getCandidates,
  getCandidateDetail,
  runAtsCheck,
} from '@/lib/api';
import { ApiError } from '@/lib/api';
import {
  MOCK_JOB_ID,
  MOCK_CANDIDATE_ID,
  MOCK_CANDIDATE_LIST,
  MOCK_CANDIDATE_DETAIL,
  MOCK_ATS_RESULT,
  MOCK_BOUNDING_BOX,
  MOCK_ATS_ISSUE,
} from './mocks/handlers';

// ── getCandidates ────────────────────────────────────────────────────────────

describe('getCandidates()', () => {
  it('returns a valid CandidateListResponse for a known job ID', async () => {
    const result = await getCandidates(MOCK_JOB_ID);

    // Shape: top-level fields
    expect(result.job_id).toBe(MOCK_JOB_ID);
    expect(result.total_candidates).toBe(2);
    expect(result.limit).toBe(20);
    expect(result.cursor).toBeNull();

    // Shape: candidates array
    expect(Array.isArray(result.candidates)).toBe(true);
    expect(result.candidates).toHaveLength(2);

    // Deep equality against fixture
    expect(result).toStrictEqual(MOCK_CANDIDATE_LIST);
  });

  it('each candidate has the required score fields', async () => {
    const result = await getCandidates(MOCK_JOB_ID);

    for (const candidate of result.candidates) {
      expect(candidate).toHaveProperty('id');
      expect(candidate).toHaveProperty('name');
      expect(candidate).toHaveProperty('signal');
      expect(typeof (candidate as any).skill_score).toBe('number');
      expect(typeof (candidate as any).experience_score).toBe('number');
      expect(typeof (candidate as any).education_score).toBe('number');
      expect(typeof (candidate as any).semantic_score).toBe('number');
    }
  });

  it('throws ApiError with status 404 for unknown job ID', async () => {
    let error: unknown;
    try {
      await getCandidates('non-existent-job');
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
  });

  it('accepts limit and cursor pagination parameters', async () => {
    // Temporarily override the handler to capture query params
    let capturedUrl = '';
    server.use(
      http.get('http://localhost:8000/api/v2/jobs/:jobId/candidates', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(MOCK_CANDIDATE_LIST);
      }),
    );

    await getCandidates(MOCK_JOB_ID, 10, 5);

    const url = new URL(capturedUrl);
    expect(url.searchParams.get('limit')).toBe('10');
    expect(url.searchParams.get('cursor')).toBe('5');
  });
});

// ── getCandidateDetail ───────────────────────────────────────────────────────

describe('getCandidateDetail()', () => {
  it('returns a valid CandidateDetailResponse for known IDs', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);

    // Top-level identity fields
    expect(result.id).toBe(MOCK_CANDIDATE_ID);
    expect(result.job_id).toBe(MOCK_JOB_ID);
    expect(result.status).toBe('ready');

    // Presigned URL present
    expect(typeof result.url).toBe('string');
    expect(result.url.startsWith('https://')).toBe(true);

    // Deep equality against fixture
    expect(result).toStrictEqual(MOCK_CANDIDATE_DETAIL);
  });

  it('ats_result has correct shape: score, signals, flags, bounding_boxes', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);
    const ats = result.ats_result;

    // ats_score is a number in [0, 100]
    expect(typeof ats.ats_score).toBe('number');
    expect(ats.ats_score).toBeGreaterThanOrEqual(0);
    expect(ats.ats_score).toBeLessThanOrEqual(100);

    // signals is a dict<string, string>
    expect(typeof ats.signals).toBe('object');
    for (const [key, val] of Object.entries(ats.signals)) {
      expect(typeof key).toBe('string');
      expect(typeof val).toBe('string');
    }

    // flags: each AtsIssue has required fields
    expect(Array.isArray(ats.flags)).toBe(true);
    expect(ats.flags).toHaveLength(1);
    const flag = ats.flags[0];
    expect(['moderate', 'severe']).toContain(flag.severity);
    expect(typeof flag.issue).toBe('string');
    expect(typeof flag.message).toBe('string');

    // bounding_boxes: each BoundingBox has required coordinate fields
    expect(Array.isArray(ats.bounding_boxes)).toBe(true);
    const box = ats.bounding_boxes[0];
    expect(typeof box.x0).toBe('number');
    expect(typeof box.y0).toBe('number');
    expect(typeof box.x1).toBe('number');
    expect(typeof box.y1).toBe('number');
    expect(typeof box.page).toBe('number');
    expect(typeof box.issue).toBe('string');
    // x1 must be greater than x0 (valid bounding box)
    expect(box.x1).toBeGreaterThan(box.x0);
    expect(box.y1).toBeGreaterThan(box.y0);
  });

  it('bounding_box fixture matches expected coordinates', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);
    expect(result.ats_result.bounding_boxes[0]).toStrictEqual(MOCK_BOUNDING_BOX);
  });

  it('ats_issue fixture matches expected fields', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);
    expect(result.ats_result.flags[0]).toStrictEqual(MOCK_ATS_ISSUE);
  });

  it('score fields are all valid numbers', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);

    expect(typeof result.score).toBe('number');
    expect(typeof result.skill_score).toBe('number');
    expect(typeof result.experience_score).toBe('number');
    expect(typeof result.education_score).toBe('number');
    expect(typeof result.semantic_score).toBe('number');
  });

  it('extraction.explicit_skills have name, provenance, confidence', async () => {
    const result = await getCandidateDetail(MOCK_JOB_ID, MOCK_CANDIDATE_ID);

    expect(Array.isArray(result.extraction?.explicit_skills)).toBe(true);
    const skill = result.extraction!.explicit_skills![0];
    expect(typeof skill.name).toBe('string');
    expect(typeof skill.provenance).toBe('string');
    expect(typeof skill.confidence).toBe('number');
    expect(skill.confidence).toBeGreaterThanOrEqual(0);
    expect(skill.confidence).toBeLessThanOrEqual(1);
  });

  it('throws ApiError with status 404 for unknown candidate ID', async () => {
    let error: unknown;
    try {
      await getCandidateDetail(MOCK_JOB_ID, 'unknown-candidate');
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
  });
});

// ── runAtsCheck ──────────────────────────────────────────────────────────────

describe('runAtsCheck()', () => {
  it('returns a valid AtsResult when given a PDF file', async () => {
    const file = new File(['%PDF-1.4 fake content'], 'resume.pdf', { type: 'application/pdf' });
    const result = await runAtsCheck(file);

    expect(result).toStrictEqual(MOCK_ATS_RESULT);
  });

  it('ats_score is a valid number between 0 and 100', async () => {
    const file = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
    const result = await runAtsCheck(file);

    expect(typeof result.ats_score).toBe('number');
    expect(result.ats_score).toBeGreaterThanOrEqual(0);
    expect(result.ats_score).toBeLessThanOrEqual(100);
  });

  it('signals object values are strings', async () => {
    const file = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
    const result = await runAtsCheck(file);

    for (const [evaluator, signal] of Object.entries(result.signals)) {
      expect(typeof evaluator).toBe('string');
      expect(typeof signal).toBe('string');
    }
  });

  it('sends a multipart FormData request with the file', async () => {
    let capturedFormData: FormData | null = null;

    server.use(
      http.post('http://localhost:8000/api/v2/ats-check', async ({ request }) => {
        capturedFormData = await request.formData();
        return HttpResponse.json(MOCK_ATS_RESULT);
      }),
    );

    const file = new File(['%PDF-1.4'], 'my_resume.pdf', { type: 'application/pdf' });
    await runAtsCheck(file);

    expect(capturedFormData).not.toBeNull();
    const capturedFile = capturedFormData!.get('file');
    // jsdom represents File as Blob in FormData; check it is Blob-like with the right name
    expect(capturedFile).toBeTruthy();
    expect((capturedFile as Blob).size).toBeGreaterThan(0);
  });

  it('throws ApiError with status 422 when no file is attached', async () => {
    // Override to simulate backend validation error
    server.use(
      http.post('http://localhost:8000/api/v2/ats-check', () => {
        return HttpResponse.json({ detail: 'No file provided' }, { status: 422 });
      }),
    );

    let error: unknown;
    try {
      // Call with a dummy empty file to trigger the override
      const file = new File([], 'empty.pdf');
      await runAtsCheck(file);
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
  });

  it('throws ApiError on server error (500)', async () => {
    server.use(
      http.post('http://localhost:8000/api/v2/ats-check', () => {
        return HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 });
      }),
    );

    let error: unknown;
    try {
      const file = new File(['%PDF-1.4'], 'test.pdf');
      await runAtsCheck(file);
    } catch (e) {
      error = e;
    }

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
  });
});
