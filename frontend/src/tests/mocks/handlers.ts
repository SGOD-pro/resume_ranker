import { http, HttpResponse } from 'msw';
import type {
  V2CandidateListResponse,
  V2CandidateDetailResponse,
  AtsResult,
} from '@/lib/api-v2';

const API_BASE = 'http://localhost:8000';

// ── Shared mock data fixtures ────────────────────────────────────────────────

export const MOCK_JOB_ID = 'job-abc-123';
export const MOCK_CANDIDATE_ID = 'cand-xyz-456';

export const MOCK_BOUNDING_BOX = {
  x0: 72,
  y0: 100,
  x1: 300,
  y1: 115,
  page: 1,
  issue: 'chronology_inconsistency',
};

export const MOCK_ATS_ISSUE = {
  severity: 'moderate' as const,
  issue: 'ChronologyConsistencyEvaluator',
  message: 'Employment gap of 14 months detected between 2020-01 and 2021-03.',
  fix_suggestion: 'Add a brief note or role to explain the gap.',
};

export const MOCK_ATS_RESULT: AtsResult = {
  ats_score: 74.5,
  signals: {
    ChronologyConsistencyEvaluator: 'moderate',
    ReadingOrderEvaluator: 'ok',
    LayoutStabilityEvaluator: 'ok',
  },
  flags: [MOCK_ATS_ISSUE],
  bounding_boxes: [MOCK_BOUNDING_BOX],
};

export const MOCK_CANDIDATE_LIST: V2CandidateListResponse = {
  job_id: MOCK_JOB_ID,
  total_candidates: 2,
  limit: 20,
  cursor: null,
  candidates: [
    {
      id: MOCK_CANDIDATE_ID,
      name: 'Alice Smith',
      signal: 'strong',
      skill_score: 88,
      experience_score: 75,
      education_score: 90,
      semantic_score: 82,
    },
    {
      id: 'cand-zzz-789',
      name: 'Bob Jones',
      signal: 'maybe',
      skill_score: 60,
      experience_score: 55,
      education_score: 70,
      semantic_score: 58,
    },
  ],
};

export const MOCK_CANDIDATE_DETAIL: V2CandidateDetailResponse = {
  id: MOCK_CANDIDATE_ID,
  job_id: MOCK_JOB_ID,
  status: 'ready',
  s3_pdf_key: 'resumes/alice.pdf',
  url: 'https://s3.example.com/resumes/alice.pdf?signed=true',
  ats_result: MOCK_ATS_RESULT,
  extraction: {
    explicit_skills: [
      { name: 'Python', provenance: 'text', confidence: 0.99 },
      { name: 'FastAPI', provenance: 'text', confidence: 0.95 },
    ],
  },
  score: 83.75,
  skill_score: 88,
  experience_score: 75,
  education_score: 90,
  semantic_score: 82,
};

// ── MSW Handlers ─────────────────────────────────────────────────────────────

export const handlers = [
  // GET /api/v2/jobs/:jobId/candidates
  http.get(`${API_BASE}/api/v2/jobs/:jobId/candidates`, ({ params }) => {
    if (params.jobId !== MOCK_JOB_ID) {
      return HttpResponse.json({ detail: 'Job not found' }, { status: 404 });
    }
    return HttpResponse.json(MOCK_CANDIDATE_LIST);
  }),

  // GET /api/v2/jobs/:jobId/candidates/:candidateId
  http.get(
    `${API_BASE}/api/v2/jobs/:jobId/candidates/:candidateId`,
    ({ params }) => {
      if (params.candidateId !== MOCK_CANDIDATE_ID) {
        return HttpResponse.json({ detail: 'Candidate not found' }, { status: 404 });
      }
      return HttpResponse.json(MOCK_CANDIDATE_DETAIL);
    },
  ),

  // POST /api/v2/ats-check
  http.post(`${API_BASE}/api/v2/ats-check`, async ({ request }) => {
    const formData = await request.formData();
    const file = formData.get('file');

    if (!file) {
      return HttpResponse.json({ detail: 'No file provided' }, { status: 422 });
    }

    return HttpResponse.json(MOCK_ATS_RESULT);
  }),
];
