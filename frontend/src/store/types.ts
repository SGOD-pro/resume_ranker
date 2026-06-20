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

export interface Candidate {
  id: string;
  rank: number;
  name: string;
  title: string;
  location: string;
  email: string;
  phone: string;
  overallScore: number;
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
