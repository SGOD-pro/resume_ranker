export type Signal = 'strong' | 'good' | 'fair' | 'knockout' | 'processing' | 'parse-failed';

export type CandidateStatus = 'under-review' | 'shortlisted' | 'rejected' | 'assessment-sent';

export type EducationLevel = 'high-school' | 'associate' | 'bachelor' | 'master' | 'doctorate' | 'any';

export interface ExperienceEntry {
  id: string;
  role: string;
  company: string;
  startDate: string;
  endDate: string;
  durationYears: number;
}

export interface EducationEntry {
  id: string;
  degree: string;
  field: string;
  institution: string;
  yearRange: string;
}

export interface SkillMatch {
  matched: string[];
  missing: string[];
  extra: string[];
}

export interface KnockoutCheck {
  label: string;
  passed: boolean;
  detail: string;
}

export interface CandidateFlag {
  type: 'warning' | 'info';
  message: string;
}

export interface ScoreBreakdown {
  skills: number;
  experience: number;
  keywords: number;
  education: number;
}

export interface IdentityProvenance {
  source?: string;
  page?: number;
  bounding_box?: number[];
  evidence_text?: string;
  candidate_rejections?: Array<string | { text?: string; reason?: string }>;
  [key: string]: unknown;
}

export interface BoundingBox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  severity: 'warning' | 'severe';
  reason: string;
}

export interface AtsCheckResponse {
  score: number;
  breakdown: Record<string, number>;
  layout_flags: string[];
  font_health: string;
  contact_info_visibility: {
    email: boolean;
    phone: boolean;
  };
  section_detection: {
    found: string[];
    missed: string[];
  };
  keyword_preview: string[];
  date_consistency: string;
  bounding_boxes: BoundingBox[];
  limitations_disclaimer?: string;
}

export interface Candidate {
  id: string;
  rank: number;
  name: string;
  title: string;
  location: string;
  email: string;
  phone: string;
  pdfUrl: string;
  overallScore: number;
  relevanceScore?: number;
  eligibilityStatus?: 'ELIGIBLE' | 'REVIEW_REQUIRED' | 'DOES_NOT_MEET_CRITERIA' | string;
  humanDecision?: string;
  identityStatus?: 'VERIFIED' | 'PLAUSIBLE' | 'UNRESOLVED' | string;
  identityConfidence?: number;
  identityProvenance?: IdentityProvenance;
  factorLedger?: Record<string, unknown>[];
  scoreVersion?: string;
  policyVersion?: string;
  jobVersion?: number;
  atsScore?: number;
  atsWarnings?: string[];
  signal: Signal;
  scoreBreakdown: ScoreBreakdown;
  skillMatch: SkillMatch;
  knockoutChecks: KnockoutCheck[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  flags: CandidateFlag[];
  topSkills: string[];
  totalYears: number;
  status: CandidateStatus;
  note: string;
}

export interface Job {
  title: string;
  department: string;
  description: string;
  mustHaveSkills: string[];
  niceToHaveSkills: string[];
  minYears: number;
  maxYears: number;
  educationLevel: EducationLevel;
  educationField: string;
  keywords: string[];
  weights: {
    skills: number;
    experience: number;
    keywords: number;
    education: number;
  };
}

export interface UploadState {
  totalFiles: number;
  analyzedFiles: number;
  processingFiles: number;
  isUploading: boolean;
}

export type JobStatus =
  | 'CREATED'
  | 'UPLOADING'
  | 'FAST_PARSING'
  | 'FALLBACK_PROCESSING'
  | 'FINAL_RANKING'
  | 'READY'
  | 'READY_WITH_WARNINGS'
  | 'FAILED';

export type UploadSessionStatus =
  | 'UPLOADING'
  | 'UPLOAD_FINALIZED'
  | 'FAST_PREPROCESSING'
  | 'FAST_PARSING'
  | 'READY_TO_ANALYZE'
  | 'ANALYSIS_REQUESTED'
  | 'FALLBACK_PROCESSING'
  | 'FINAL_RANKING'
  | 'READY'
  | 'READY_WITH_WARNINGS'
  | 'FAILED'
  | 'EXPIRED';

// ── Phase 2 Direct Presigned S3 POST & Pipeline Status Types ────────────────

export type FileProcessingStatus =
  | 'PENDING_UPLOAD'
  | 'S1_PROCESSING'
  | 'S1_DONE'
  | 'S2_PROCESSING'
  | 'S2_DONE'
  | 'S1_FAILED'
  | 'S2_FAILED'
  | 'REMOVED';

export type JobPipelineStatus =
  | 'UPLOADING'
  | 'READY_TO_ANALYZE'
  | 'PROCESSING'
  | 'SCORING'
  | 'DONE'
  | 'DONE_WITH_ERRORS'
  | 'FAILED';

export interface JobFileStatus {
  file_id: string;
  filename: string;
  status: FileProcessingStatus;
  candidate_name?: string | null;
  needs_fallback?: boolean;
  low_confidence_extraction?: boolean;
  fallback_reason?: string | null;
  error_message?: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobPipelineStatus;
  total_files: number;
  remaining: number;
  usable_files: number;
  analyze_requested: boolean;
  is_stalled: boolean;
  updated_at?: string;
  files: JobFileStatus[];
}

export interface PresignedPostInfo {
  url: string;
  fields: Record<string, string>;
}

export interface CreateJobFileSpec {
  filename: string;
  file_size: number;
}

export interface CreateJobFileResponse {
  file_id: string;
  filename: string;
  s3_key: string;
  presigned_post: PresignedPostInfo;
}

export interface CreateJobResponseV2 {
  job_id: string;
  id: string;
  title: string;
  status: string;
  total_files: number;
  remaining: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
  has_more?: boolean;
  next_page?: number | null;
  files: CreateJobFileResponse[];
}

export interface AnalyzeResponseV2 {
  job_id: string;
  status: string;
  analyze_requested: boolean;
  remaining: number;
  usable_files: number;
  message?: string;
}



