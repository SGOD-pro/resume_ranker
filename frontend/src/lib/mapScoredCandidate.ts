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
  const name = raw.name || 'Unknown';
  const finalScore = typeof raw.final_score === 'number' ? raw.final_score : 0;
  const knockedOut = Boolean(raw.knocked_out);

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

  // ── DEBUG: Step 6 — Raw backend → mapped frontend trace ──────────────────
  // Compare every knockout field: backend raw value vs. what enters the store.
  // Remove or guard with an env flag before shipping to production.
  console.group(`[KNOCKOUT DEBUG] ${name}`);
  console.log('Backend raw fields:');
  console.table({
    knocked_out:        { backend: raw.knocked_out,        frontend: knockedOut },
    matched_must_have:  { backend: JSON.stringify(raw.matched_must_have  ?? []), frontend: JSON.stringify(skillMatch.matched.slice(0, (raw.matched_must_have || []).length)) },
    missing_must_have:  { backend: JSON.stringify(raw.missing_must_have  ?? []), frontend: JSON.stringify(skillMatch.missing) },
    final_score:        { backend: raw.final_score,        frontend: finalScore },
    knockout_reasons:   { backend: JSON.stringify(raw.knockout_reasons ?? []), frontend: JSON.stringify(knockoutChecks.filter(k => !k.passed).map(k => k.label)) },
  });
  console.log('Knockout checks (computed in mapper):');
  knockoutChecks.forEach(k => console.log(`  ${k.passed ? '✅' : '❌'} ${k.label}: ${k.detail}`));
  console.groupEnd();

  return mapped;
}

/** Map an array of backend ScoredCandidate dicts to frontend Candidate[] */
export function mapScoredCandidates(rawCandidates: any[]): Candidate[] {
  return rawCandidates.map((raw, i) => mapScoredCandidate(raw, i));
}
