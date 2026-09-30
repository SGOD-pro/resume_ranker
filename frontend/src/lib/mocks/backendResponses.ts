/**
 * backendResponses.ts — Mock payloads strictly derived from actual backend routes
 * ==============================================================================
 * Used for deterministic frontend testing and offline verification.
 * Shapes match backend responses from:
 *   - POST /api/v2/jobs (CreateJobResponse)
 *   - GET  /api/v2/jobs/{id}/status (JobStatusResponse)
 *   - POST /api/v2/jobs/{id}/analyze (AnalyzeResponse)
 *   - GET  /api/v2/jobs/{id}/results (ResultsResponse)
 */

import type {
  CreateJobResponseV2,
  JobStatusResponse,
  AnalyzeResponseV2,
} from '@/store/types';

export const mockCreateJobResponse: CreateJobResponseV2 = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  title: 'Staff Backend Engineer',
  status: 'UPLOADING',
  total_files: 2,
  remaining: 2,
  page: 1,
  page_size: 50,
  total_pages: 1,
  has_more: false,
  next_page: null,
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      s3_key: 'jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f101-uuid4.pdf',
      presigned_post: {
        url: 'https://resume-ranker-dev-isolated-445567096027.s3.ap-south-1.amazonaws.com/',
        fields: {
          key: 'jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f101-uuid4.pdf',
          bucket: 'resume-ranker-dev-isolated-445567096027',
          'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
          'X-Amz-Credential': 'ASIAEXAMPLE...',
          'X-Amz-Date': '20260927T000000Z',
          'X-Amz-Security-Token': 'IQoJEXAMPLE...',
          Policy: 'eyEXAMPLE...',
          'X-Amz-Signature': '3a9fEXAMPLE...',
        },
      },
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      s3_key: 'jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f102-uuid4.pdf',
      presigned_post: {
        url: 'https://resume-ranker-dev-isolated-445567096027.s3.ap-south-1.amazonaws.com/',
        fields: {
          key: 'jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/raw/f102-uuid4.pdf',
          bucket: 'resume-ranker-dev-isolated-445567096027',
          'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
          'X-Amz-Credential': 'ASIAEXAMPLE...',
          'X-Amz-Date': '20260927T000000Z',
          'X-Amz-Security-Token': 'IQoJEXAMPLE...',
          Policy: 'eyEXAMPLE...',
          'X-Amz-Signature': '7b2cEXAMPLE...',
        },
      },
    },
  ],
};

export const mockJobStatusUploading: JobStatusResponse = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'UPLOADING',
  total_files: 2,
  remaining: 2,
  usable_files: 0,
  analyze_requested: false,
  is_stalled: false,
  updated_at: '2026-09-27T10:00:05Z',
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      status: 'PENDING_UPLOAD',
      candidate_name: null,
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      status: 'PENDING_UPLOAD',
      candidate_name: null,
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
  ],
};

export const mockJobStatusReadyToAnalyze: JobStatusResponse = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'READY_TO_ANALYZE',
  total_files: 2,
  remaining: 2,
  usable_files: 2,
  analyze_requested: false,
  is_stalled: false,
  updated_at: '2026-09-27T10:00:15Z',
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      status: 'S1_DONE',
      candidate_name: 'Alex Morgan',
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      status: 'S1_DONE',
      candidate_name: 'Marcus Vance',
      needs_fallback: true,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
  ],
};

export const mockAnalyzeResponse: AnalyzeResponseV2 = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'PROCESSING',
  remaining: 2,
  usable_files: 2,
  analyze_requested: true,
  message: 'Analysis requested. Pipeline executing.',
};

export const mockJobStatusProcessing: JobStatusResponse = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'PROCESSING',
  total_files: 2,
  remaining: 1,
  usable_files: 1,
  analyze_requested: true,
  is_stalled: false,
  updated_at: '2026-09-27T10:00:30Z',
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      status: 'S2_DONE',
      candidate_name: 'Alex Morgan',
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      status: 'S2_PROCESSING',
      candidate_name: 'Marcus Vance',
      needs_fallback: true,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
  ],
};

export const mockJobStatusDone: JobStatusResponse = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'DONE',
  total_files: 2,
  remaining: 0,
  usable_files: 2,
  analyze_requested: true,
  is_stalled: false,
  updated_at: '2026-09-27T10:00:45Z',
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      status: 'S2_DONE',
      candidate_name: 'Alex Morgan',
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      status: 'S2_DONE',
      candidate_name: 'Marcus Vance',
      needs_fallback: true,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
  ],
};

export const mockJobStatusStalled: JobStatusResponse = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'PROCESSING',
  total_files: 2,
  remaining: 1,
  usable_files: 1,
  analyze_requested: true,
  is_stalled: true,
  updated_at: '2026-09-27T09:45:00Z',
  files: [
    {
      file_id: 'f101-uuid4',
      filename: 'alex_morgan.pdf',
      status: 'S2_DONE',
      candidate_name: 'Alex Morgan',
      needs_fallback: false,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
    {
      file_id: 'f102-uuid4',
      filename: 'marcus_vance.pdf',
      status: 'S2_PROCESSING',
      candidate_name: 'Marcus Vance',
      needs_fallback: true,
      low_confidence_extraction: false,
      fallback_reason: null,
      error_message: null,
    },
  ],
};

export const mockJobResults = {
  job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
  status: 'DONE',
  total_candidates: 2,
  candidates: [
    {
      rank: 1,
      document_id: 'f101-uuid4',
      job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
      name: 'Alex Morgan',
      email: 'alex.morgan@example.com',
      phone: '+1 555-0192',
      final_score: 91.5,
      skill_score: 95.0,
      experience_score: 90.0,
      keyword_score: 88.0,
      education_score: 90.0,
      knocked_out: false,
      knockout_reasons: [],
      skills: ['Python', 'FastAPI', 'Distributed Systems', 'Docker', 'AWS'],
      experience: [
        {
          role: 'Staff Backend Engineer',
          company: 'Acme Cloud',
          duration_years: 5,
        },
      ],
      pdf_url: '/api/v2/jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/resumes/f101-uuid4/download',
    },
    {
      rank: 2,
      document_id: 'f102-uuid4',
      job_id: '4a71e8bf-4a92-482a-bc91-ec129e928a01',
      name: 'Marcus Vance',
      email: 'marcus.vance@example.com',
      phone: '+1 555-0144',
      final_score: 82.0,
      skill_score: 84.0,
      experience_score: 80.0,
      keyword_score: 82.0,
      education_score: 80.0,
      knocked_out: false,
      knockout_reasons: [],
      skills: ['Python', 'PostgreSQL', 'FastAPI'],
      experience: [
        {
          role: 'Senior Software Engineer',
          company: 'DataFlow Inc',
          duration_years: 4,
        },
      ],
      pdf_url: '/api/v2/jobs/4a71e8bf-4a92-482a-bc91-ec129e928a01/resumes/f102-uuid4/download',
    },
  ],
};
