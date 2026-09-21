/**
 * mapScoredCandidate.ts — Maps backend ScoredCandidate to frontend Candidate
 * =============================================================================
 * The backend CandidateScorer returns ScoredCandidate dataclasses (serialized
 * as JSON dicts). This mapper transforms them into the frontend's Candidate
 * interface shape, computing derived fields like signal, topSkills, and
 * knockout checks.
 */

import type {
  Candidate,
  Signal,
  ScoreBreakdown,
  SkillMatch,
  KnockoutCheck,
  ExperienceEntry,
  EducationEntry,
  CandidateFlag,
} from '@/store/types';

/* eslint-disable @typescript-eslint/no-explicit-any */

/** Derive the signal tier from the final score and knockout status */
function deriveSignal(finalScore: number, knockedOut: boolean): Signal {
  if (knockedOut) return 'knockout';
  if (finalScore >= 75) return 'strong';
  if (finalScore >= 50) return 'good';
  return 'fair';
}

/** Map a single backend ScoredCandidate dict to the frontend Candidate shape */
export function mapScoredCandidate(raw: any, index: number): Candidate {
  const id = raw.document_id || `candidate-${index}`;
  const rawName = raw.name;
  const identityStatus = raw.identity_status || (rawName && rawName !== 'Unknown' ? 'VERIFIED' : 'UNRESOLVED');
  const isUnresolvedName = !rawName || rawName === 'Unknown' || identityStatus === 'UNRESOLVED';
  const name = isUnresolvedName ? 'Name needs review' : rawName;
  const finalScore = typeof raw.final_score === 'number' ? raw.final_score : (typeof raw.relevance_score === 'number' ? raw.relevance_score : 0);
  const relevanceScore = typeof raw.relevance_score === 'number' ? raw.relevance_score : finalScore;
  const knockedOut = Boolean(raw.knocked_out) || raw.eligibility_status === 'DOES_NOT_MEET_CRITERIA';

  // Score breakdown
  const scoreBreakdown: ScoreBreakdown = {
    skills: typeof raw.skill_score === 'number' ? raw.skill_score : 0,
    experience: typeof raw.experience_score === 'number' ? raw.experience_score : 0,
    keywords: typeof raw.keyword_score === 'number' ? raw.keyword_score : 0,
    education: typeof raw.education_score === 'number' ? raw.education_score : 0,
  };

  // Skill match
  const skillMatch: SkillMatch = {
    matched: [
      ...(raw.matched_must_have || []),
      ...(raw.matched_nice_to_have || []),
    ],
    missing: raw.missing_must_have || [],
    extra: raw.extra_skills || [],
  };

  // Top skills — combination of matched must-have + nice-to-have, then extra
  const topSkills = [
    ...(raw.matched_must_have || []),
    ...(raw.matched_nice_to_have || []),
    ...(raw.extra_skills || []).slice(0, 5),
  ].slice(0, 8);

  // Knockout checks — build from knockout reasons + must-have matching
  const knockoutChecks: KnockoutCheck[] = [];

  // Must-have skills check
  const hasAllMustHave = (raw.missing_must_have || []).length === 0;
  knockoutChecks.push({
    label: 'Must-have skills',
    passed: hasAllMustHave,
    detail: hasAllMustHave
      ? `All required skills matched`
      : `Missing: ${(raw.missing_must_have || []).join(', ')}`,
  });

  // Experience check
  const totalYears = typeof raw.total_exp_years === 'number' ? raw.total_exp_years : 0;
  const expKO = (raw.knockout_reasons || []).some((r: string) =>
    r.toLowerCase().includes('experience')
  );
  knockoutChecks.push({
    label: 'Minimum experience',
    passed: !expKO,
    detail: expKO
      ? `${totalYears} years (insufficient)`
      : `${totalYears} years`,
  });

  // Education check
  const eduKO = (raw.knockout_reasons || []).some((r: string) =>
    r.toLowerCase().includes('degree') || r.toLowerCase().includes('education')
  );
  knockoutChecks.push({
    label: 'Education requirement',
    passed: !eduKO,
    detail: raw.degree_level
      ? `${raw.degree_level}${raw.degree_field ? ` in ${raw.degree_field}` : ''}`
      : 'Not specified',
  });

  // Experience entries — we don't have full structured experience from scorer,
  // but we can provide what's available
  const experience: ExperienceEntry[] = [];
  // The scorer's ScoredCandidate has best_title_match but not full experience list.
  // We'll show what's available from the best match.
  if (raw.best_title_match) {
    experience.push({
      id: `exp-${index}-0`,
      role: raw.best_title_match,
      company: '',
      startDate: '',
      endDate: '',
      durationYears: totalYears,
    });
  }

  // Education entries
  const education: EducationEntry[] = [];
  if (raw.degree_level) {
    education.push({
      id: `edu-${index}-0`,
      degree: raw.degree_level,
      field: raw.degree_field || '',
      institution: '',
      yearRange: '',
    });
  }

  // Flags — anomalies from the extraction/scoring
  const flags: CandidateFlag[] = (raw.anomalies || []).map((a: string) => ({
    type: a.includes('LOW_QUALITY') || a.includes('GAP') ? ('warning' as const) : ('info' as const),
    message: a,
  }));

  // Title — use best_title_match or fallback
  const title = raw.best_title_match || '';

  // ── Contact info from backend extraction ──────────────────────────────
  const pdfUrlPath = raw.pdf_url || '';
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  const pdfUrl = pdfUrlPath ? `${apiBase}${pdfUrlPath}` : '';

  const mapped: Candidate = {
    id,
    rank: typeof raw.rank === 'number' ? raw.rank : index + 1,
    name,
    title,
    location: raw.location || '',
    email: raw.email || '',
    phone: raw.phone || '',
    pdfUrl,
    overallScore: finalScore,
    relevanceScore,
    eligibilityStatus: raw.eligibility_status || (knockedOut ? 'DOES_NOT_MEET_CRITERIA' : (isUnresolvedName ? 'REVIEW_REQUIRED' : 'ELIGIBLE')),
    humanDecision: raw.human_decision || 'NEW',
    identityStatus,
    identityConfidence: typeof raw.identity_confidence === 'number' ? raw.identity_confidence : (isUnresolvedName ? 0.0 : 1.0),
    identityProvenance: raw.identity_provenance || raw.identity || {},
    factorLedger: raw.factor_ledger || [],
    scoreVersion: raw.score_version || '2.2.0',
    policyVersion: raw.policy_version || '2026.1',
    jobVersion: raw.job_version || 1,
    atsScore: typeof raw.ats_score === 'number' ? raw.ats_score : undefined,
    atsWarnings: raw.ats_warnings || [],
    signal: deriveSignal(finalScore, knockedOut),
    scoreBreakdown,
    skillMatch,
    knockoutChecks,
    experience,
    education,
    flags,
    topSkills,
    totalYears,
    status: 'under-review',
    note: '',
  };

  return mapped;
}

/** Map an array of backend ScoredCandidate dicts to frontend Candidate[] */
export function mapScoredCandidates(rawCandidates: any[]): Candidate[] {
  return rawCandidates.map((raw, i) => mapScoredCandidate(raw, i));
}
