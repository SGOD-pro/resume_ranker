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
  | 'FAST_PARSING'
  | 'FALLBACK_PROCESSING'
  | 'FINAL_RANKING'
  | 'READY'
  | 'READY_WITH_WARNINGS'
  | 'FAILED'
  | 'EXPIRED';

