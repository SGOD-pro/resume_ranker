/**
 * e2e-api-test.ts — One-click multi-JD integration test
 * ========================================================
 * Mirrors test_scorer.py's predefined JDs but tests through the ACTUAL
 * HTTP APIs (not the scorer directly). Uses ONE job ID per JD — creates
 * the job, uploads ALL 20 PDFs, patches JD config, extracts, scores,
 * and validates the full pipeline.
 *
 * Predefined JD roles (from test_scorer.py):
 *   0. Full Stack Developer      (UI screenshot JD)
 *   1. Senior Backend Engineer   (regression)
 *   2. Digital Marketing Manager (regression)
 *   3. Security Guard            (regression)
 *   4. Junior Web Developer      (fresher-friendly)
 *
 * Run: open /test/e2e.html in browser while backend + vite dev are running
 */

// ── Imports ─────────────────────────────────────────────────────────────────

import {
  checkHealth,
  createJob,
  updateJob,
  scoreJob,
  startExtraction,
  type CreateJobPayload,
  type ScoreResponse,
  type ExtractionEvent,
} from '../src/lib/api';

import { mapScoredCandidates } from '../src/lib/mapScoredCandidate';

// ── Types ───────────────────────────────────────────────────────────────────

interface JDTestCase {
  name: string;
  jd: CreateJobPayload;
  weights: Record<string, number>;
  /** Optional assertions to run on the score response */
  assertions?: (res: ScoreResponse, ctx: TestContext) => void;
}

interface TestContext {
  assert: (condition: boolean, label: string, detail?: string) => void;
  logData: (label: string, data: unknown) => void;
}

// ── API Base ────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// ── All 20 PDF filenames ────────────────────────────────────────────────────

const ALL_PDF_NAMES = [
  '1.pdf', '2.pdf', '3.pdf', '4.pdf', '5.pdf',
  '6.pdf', '7.pdf', '8.pdf', '9.pdf', '10.pdf',
  '11.pdf', '12.pdf', '13.pdf', '14.pdf', '15.pdf',
  '16.pdf', '17.pdf', '18.pdf', 'souvik.pdf', 'SUBHADIPcv.pdf', 'backend.pdf', 'fullstack.pdf'
];

// ── Predefined JD Test Cases (mirrors test_scorer.py) ───────────────────────

const JD_TESTS: JDTestCase[] = [
  {
    name: 'Full Stack Developer (UI Screenshot JD)',
    jd: {
      title: 'Full Stack Developer',
      department: 'Engineering',
      description:
        'need a full stack developer who knows backend and front-end both with little bit of devops knowledge',
      must_have_skills: ['React', 'Node', 'Python', 'JS', 'Docker'],
      nice_to_have_skills: ['Redis', 'AWS', 'K8S'],
      min_years: 0,
      max_years: 10,
      education_level: 'bachelor',
      education_field: 'CS / related',
      keywords: [],
    },
    weights: { skills: 40, experience: 25, keywords: 20, education: 15 },
    assertions: (res, { assert, logData }) => {
      // JULIE MONROE sanity check — dietitian must be knocked out
      const julie = res.candidates.find(
        (c: Record<string, unknown>) =>
          typeof c.name === 'string' &&
          (c.name.toUpperCase().includes('JULIE') || c.name.toUpperCase().includes('MONROE')),
      ) as Record<string, unknown> | undefined;

      if (julie) {
        logData('JULIE MONROE diagnostic', {
          name: julie.name,
          document_id: julie.document_id,
          final_score: julie.final_score,
          knocked_out: julie.knocked_out,
          knockout_reasons: julie.knockout_reasons,
          matched_must_have: julie.matched_must_have,
          missing_must_have: julie.missing_must_have,
          skill_score: julie.skill_score,
          degree_level: julie.degree_level,
          degree_field: julie.degree_field,
        });
        assert(
          julie.knocked_out === true,
          '🎯 JULIE MONROE is knocked out (dietitian, zero dev skills)',
          `knocked_out=${julie.knocked_out}`,
        );
        assert(
          julie.final_score === 0,
          '🎯 JULIE MONROE final_score is 0',
          `final_score=${julie.final_score}`,
        );
      } else {
        assert(false, 'JULIE MONROE found in results', 'not found — check PDF extraction');
      }
    },
  },

  {
    name: 'Senior Backend Engineer',
    jd: {
      title: 'Senior Backend Engineer',
      department: 'Engineering',
      description: 'Looking for a senior backend engineer with strong Python and SQL skills, experienced in microservices architecture.',
      must_have_skills: ['Python', 'SQL'],
      nice_to_have_skills: ['Docker', 'Kubernetes', 'AWS', 'MongoDB', 'REST', 'Java'],
      min_years: 3,
      max_years: 10,
      education_level: 'bachelor',
      education_field: 'Computer Science',
      keywords: ['microservices', 'api', 'database', 'scalable', 'agile', 'backend', 'server', 'deployment'],
    },
    weights: { skills: 40, experience: 25, keywords: 20, education: 15 },
    assertions: (res, { assert }) => {
      // Backend engineer should rank Python/SQL candidates higher
      const top = res.candidates[0] as Record<string, unknown>;
      if (top) {
        const mustHave = (top.matched_must_have as string[]) || [];
        assert(
          mustHave.some((s) => s.toLowerCase().includes('python')),
          'Top candidate matches Python',
          `matched: ${mustHave.join(', ')}`,
        );
      }
    },
  },

  {
    name: 'Digital Marketing Manager',
    jd: {
      title: 'Digital Marketing Manager',
      department: 'Marketing',
      description: 'Seeking a digital marketing manager to lead brand campaigns, social media, and performance marketing.',
      must_have_skills: ['SEO', 'Marketing'],
      nice_to_have_skills: ['Social Media', 'Email Marketing', 'Instagram', 'Facebook', 'Google Ads', 'Analytics'],
      min_years: 2,
      max_years: 15,
      education_level: 'bachelor',
      education_field: 'Marketing',
      keywords: ['campaign', 'brand', 'content', 'traffic', 'conversion', 'strategy', 'audience', 'engagement'],
    },
    weights: { skills: 35, experience: 30, keywords: 20, education: 15 },
    assertions: (res, { assert }) => {
      // Most dev candidates should be knocked out (missing SEO/Marketing must-haves)
      const knockedOutCount = res.candidates.filter(
        (c: Record<string, unknown>) => c.knocked_out === true,
      ).length;
      assert(
        knockedOutCount > res.total_candidates * 0.5,
        'Most candidates knocked out for marketing role (dev resumes)',
        `${knockedOutCount}/${res.total_candidates} knocked out`,
      );
    },
  },

  {
    name: 'Security Guard',
    jd: {
      title: 'Security Guard',
      department: 'Operations',
      description: 'Looking for a security guard with surveillance and access control experience.',
      must_have_skills: ['Surveillance', 'Access Control'],
      nice_to_have_skills: ['Criminal Justice', 'Law Enforcement', 'Martial Arts', 'CPR', 'First Aid'],
      min_years: 1,
      max_years: 20,
      education_level: 'any',
      education_field: '',
      keywords: ['security', 'patrol', 'monitor', 'safety', 'guard', 'investigation', 'compliance'],
    },
    weights: { skills: 40, experience: 30, keywords: 20, education: 10 },
    assertions: (res, { assert }) => {
      // ALL dev candidates should be knocked out for a security guard role
      const knockedOutCount = res.candidates.filter(
        (c: Record<string, unknown>) => c.knocked_out === true,
      ).length;
      assert(
        knockedOutCount >= res.total_candidates * 0.8,
        'Nearly all candidates knocked out for security guard role',
        `${knockedOutCount}/${res.total_candidates} knocked out`,
      );
    },
  },

  {
    name: 'Junior Web Developer (Fresher-Friendly)',
    jd: {
      title: 'Junior Web Developer',
      department: 'Engineering',
      description: 'Looking for a junior web developer. No prior experience required. Must know HTML, CSS, and JavaScript.',
      must_have_skills: ['HTML', 'CSS', 'JavaScript'],
      nice_to_have_skills: ['React', 'Python', 'Django', 'MongoDB', 'Git', 'TypeScript', 'Node.js'],
      min_years: 0,
      max_years: 3,
      education_level: 'any',
      education_field: 'Computer Science',
      keywords: ['web', 'frontend', 'responsive', 'api', 'github'],
    },
    weights: { skills: 50, experience: 10, keywords: 25, education: 15 },
    assertions: (res, { assert }) => {
      // Fresher-friendly: some candidates should NOT be knocked out
      const active = res.candidates.filter(
        (c: Record<string, unknown>) => c.knocked_out !== true,
      ).length;
      assert(
        active >= 1,
        'At least 1 candidate NOT knocked out for fresher web dev role',
        `${active} active candidates`,
      );
    },
  },
];

// ── Counters & Helpers ──────────────────────────────────────────────────────

let passCount = 0;
let failCount = 0;
let totalTests = 0;

function assert(condition: boolean, label: string, detail?: string) {
  totalTests++;
  if (condition) {
    passCount++;
    console.log(`  ✅ ${label}${detail ? ` — ${detail}` : ''}`);
    appendLog(`✅ ${label}${detail ? ` — ${detail}` : ''}`, 'pass');
  } else {
    failCount++;
    console.error(`  ❌ ${label}${detail ? ` — ${detail}` : ''}`);
    appendLog(`❌ ${label}${detail ? ` — ${detail}` : ''}`, 'fail');
  }
}

function logData(label: string, data: unknown) {
  console.log(`  📋 ${label}:`, data);
}

function logSection(title: string) {
  console.log('');
  console.log(`${'═'.repeat(70)}`);
  console.log(`  ${title}`);
  console.log(`${'═'.repeat(70)}`);
  appendLog('', 'info');
  appendLog(`━━━ ${title} ━━━`, 'info');
}

function logPhase(phase: string) {
  console.log('');
  console.log(`── ${phase} ${'─'.repeat(Math.max(0, 60 - phase.length))}`);
}

function setStatus(text: string, type: 'running' | 'pass' | 'fail' | 'info' = 'info') {
  const el = document.getElementById('status');
  if (el) {
    el.textContent = text;
    el.className = `status-${type}`;
  }
}

function appendLog(text: string, type: 'pass' | 'fail' | 'info' | 'data' = 'info') {
  const el = document.getElementById('log');
  if (el) {
    const line = document.createElement('div');
    line.className = `log-${type}`;
    line.textContent = text;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }
}

function updateProgress(current: number, total: number, label: string) {
  const el = document.getElementById('progress');
  if (el) {
    el.textContent = `[${current}/${total}] ${label}`;
  }
}

// ── PDF Loading ─────────────────────────────────────────────────────────────

async function loadTestPdf(filename: string): Promise<File> {
  const resp = await fetch(`/test/resumes/${filename}`);
  if (!resp.ok) throw new Error(`Failed to load test PDF: ${filename} (${resp.status})`);
  const blob = await resp.blob();
  return new File([blob], filename, { type: 'application/pdf' });
}

async function uploadResumesRaw(
  jobId: string,
  files: File[],
): Promise<{ job_id: string; accepted: string[]; rejected: { filename: string; reason: string }[]; total_accepted: number }> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));

  const resp = await fetch(`${API_BASE}/jobs/${jobId}/resumes`, {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    const errBody = await resp.text();
    throw new Error(`Upload failed (${resp.status}): ${errBody}`);
  }

  return resp.json();
}

function waitForExtraction(jobId: string): Promise<ExtractionEvent[]> {
  return new Promise((resolve, reject) => {
    const events: ExtractionEvent[] = [];
    const timeout = setTimeout(() => reject(new Error('Extraction timed out (180s)')), 180_000);

    startExtraction(
      jobId,
      (event) => events.push(event),
      (error) => { clearTimeout(timeout); reject(error); },
      () => { clearTimeout(timeout); resolve(events); },
    );
  });
}

async function getResults(jobId: string): Promise<unknown> {
  const resp = await fetch(`${API_BASE}/jobs/${jobId}/results`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok) throw new Error(`GET results failed (${resp.status})`);
  return resp.json();
}

// ── Single JD Test Run ──────────────────────────────────────────────────────
// Creates one job → uploads all PDFs → patches JD → extracts → scores

async function runSingleJdTest(
  testIndex: number,
  test: JDTestCase,
  pdfFiles: File[],
): Promise<{ jobId: string; scoreRes: ScoreResponse } | null> {
  logSection(`TEST ${testIndex}: ${test.name}`);
  const testStart = performance.now();

  // ── Step 1: Create Job ──────────────────────────────────────────────────
  logPhase('POST /jobs (create)');
  const jobRes = await createJob({ title: test.jd.title || 'Untitled Job' });
  const jobId = jobRes.id;
  assert(typeof jobId === 'string' && jobId.length > 0, `[${test.name}] Job created`, jobId);

  // ── Step 2: Upload All PDFs ─────────────────────────────────────────────
  logPhase(`POST /jobs/${jobId}/resumes (${pdfFiles.length} PDFs)`);
  appendLog(`⏳ Uploading ${pdfFiles.length} resumes...`, 'info');

  const uploadRes = await uploadResumesRaw(jobId, pdfFiles);
  assert(uploadRes.accepted.length === pdfFiles.length, `[${test.name}] All ${pdfFiles.length} PDFs accepted`, `${uploadRes.accepted.length} accepted, ${uploadRes.rejected.length} rejected`);

  if (uploadRes.rejected.length > 0) {
    logData('Rejected files', uploadRes.rejected);
  }

  // ── Step 3: PATCH JD Config ─────────────────────────────────────────────
  logPhase(`PATCH /jobs/${jobId} (JD config)`);
  logData('JD config', test.jd);

  const updateRes = await updateJob(jobId, test.jd);
  assert(updateRes.status === 'updated', `[${test.name}] Config updated`);

  // Verify critical fields persisted
  const cfg = updateRes.config as Record<string, unknown>;
  assert(
    JSON.stringify(cfg.must_have_skills) === JSON.stringify(test.jd.must_have_skills),
    `[${test.name}] must_have_skills persisted`,
    JSON.stringify(cfg.must_have_skills),
  );
  assert(
    JSON.stringify(cfg.keywords) === JSON.stringify(test.jd.keywords),
    `[${test.name}] keywords persisted`,
    JSON.stringify(cfg.keywords),
  );

  // ── Step 4: Extract ─────────────────────────────────────────────────────
  logPhase(`GET /jobs/${jobId}/extract (SSE)`);
  appendLog(`⏳ Extracting ${pdfFiles.length} resumes... (this may take a while)`, 'info');

  const events = await waitForExtraction(jobId);
  const successEvents = events.filter((e) => e.type === 'extraction_progress' && e.status === 'extracted');
  const failedEvents = events.filter((e) => e.type === 'extraction_progress' && e.status === 'failed');
  assert(successEvents.length > 0, `[${test.name}] Extraction succeeded`, `${successEvents.length} OK, ${failedEvents.length} failed`);

  // ── Step 5: Score ───────────────────────────────────────────────────────
  logPhase(`POST /jobs/${jobId}/score`);
  logData('Weights', test.weights);

  let scoreRes: ScoreResponse;
  try {
    scoreRes = await scoreJob(jobId, { weights: test.weights });
  } catch (err) {
    assert(false, `[${test.name}] Scoring succeeded`, `${err}`);
    return null;
  }

  assert(scoreRes.status === 'scored', `[${test.name}] Status is "scored"`, scoreRes.status);
  assert(scoreRes.total_candidates > 0, `[${test.name}] Has candidates`, `${scoreRes.total_candidates}`);

  // ── Verify debug_jd (THE KEY CHECK) ─────────────────────────────────────
  const debugJd = (scoreRes as unknown as Record<string, unknown>).debug_jd as Record<string, unknown> | undefined;
  if (debugJd) {
    const mustHave = debugJd.must_have_skills as string[] | undefined;
    assert(
      Array.isArray(mustHave) && mustHave.length === (test.jd.must_have_skills || []).length,
      `[${test.name}] 🔑 debug_jd.must_have_skills matches JD`,
      JSON.stringify(mustHave),
    );
    assert(
      debugJd.title === test.jd.title,
      `[${test.name}] debug_jd.title matches`,
      `${debugJd.title}`,
    );
  } else {
    assert(false, `[${test.name}] debug_jd present in response`, 'missing');
  }

  // ── Step 6: GET /results ────────────────────────────────────────────────
  logPhase(`GET /jobs/${jobId}/results`);
  const resultsRes = (await getResults(jobId)) as Record<string, unknown>;
  assert(
    (resultsRes.candidates as unknown[]).length === scoreRes.total_candidates,
    `[${test.name}] GET /results matches score count`,
    `${(resultsRes.candidates as unknown[]).length}`,
  );

  // ── Step 7: Ranking Summary ─────────────────────────────────────────────
  logPhase(`Rankings for: ${test.name}`);
  console.log('');
  console.log(`  ${'#'.padStart(3)}  ${'Score'.padStart(6)}  ${'Signal'.padStart(8)}  ${'KO'.padStart(3)}  ${'Name'.padEnd(28)}  Must-Have Match`);
  console.log(`  ${'─'.repeat(90)}`);

  // Sort by final_score descending (knocked-out at bottom)
  const sorted = [...scoreRes.candidates].sort((a: Record<string, unknown>, b: Record<string, unknown>) => {
    const aKO = a.knocked_out ? 0 : 1;
    const bKO = b.knocked_out ? 0 : 1;
    if (aKO !== bKO) return bKO - aKO;
    return (b.final_score as number) - (a.final_score as number);
  });

  sorted.forEach((c: Record<string, unknown>, i: number) => {
    const ko = c.knocked_out ? '❌' : '✓';
    const score = (c.final_score as number).toFixed(1);
    const name = (c.name as string || 'Unknown').substring(0, 28);
    const matched = (c.matched_must_have as string[] || []).join(', ');
    const missing = (c.missing_must_have as string[] || []).join(', ');
    const signal = c.knocked_out ? 'KO' : (c.final_score as number) >= 75 ? 'STRONG' : (c.final_score as number) >= 50 ? 'GOOD' : 'FAIR';

    console.log(
      `  ${(i + 1).toString().padStart(3)}  ${score.padStart(6)}  ${signal.padStart(8)}  ${ko.padStart(3)}  ${name.padEnd(28)}  ✓[${matched}] ✗[${missing}]`,
    );
  });

  // ── Top 5 Scores → HTML log panel ──────────────────────────────────────
  appendLog('', 'info');
  appendLog(`🏆 TOP 5 — ${test.name}`, 'data');
  appendLog(`${'#'.padStart(3)}  ${'Score'.padStart(6)}  ${'Signal'.padStart(8)}  KO  ${'Name'.padEnd(28)}  Must-Have ✓ / ✗`, 'info');
  appendLog('─'.repeat(95), 'info');

  const top5 = sorted.slice(0, 5);
  top5.forEach((c: Record<string, unknown>, i: number) => {
    const ko = c.knocked_out ? '❌' : '✅';
    const score = (c.final_score as number).toFixed(1);
    const name = (c.name as string || 'Unknown').substring(0, 28);
    const matched = (c.matched_must_have as string[] || []).join(', ');
    const missing = (c.missing_must_have as string[] || []).join(', ');
    const signal = c.knocked_out ? 'KO' : (c.final_score as number) >= 75 ? 'STRONG' : (c.final_score as number) >= 50 ? 'GOOD' : 'FAIR';

    const logType = c.knocked_out ? 'fail' : (c.final_score as number) >= 75 ? 'pass' : 'data';
    appendLog(
      `${(i + 1).toString().padStart(3)}  ${score.padStart(6)}  ${signal.padStart(8)}  ${ko}  ${name.padEnd(28)}  ✓[${matched}]  ✗[${missing}]`,
      logType as 'pass' | 'fail' | 'data',
    );
  });
  appendLog('', 'info');

  // ── Step 8: mapScoredCandidates ─────────────────────────────────────────
  const mapped = mapScoredCandidates(scoreRes.candidates as Record<string, unknown>[]);
  assert(mapped.length === scoreRes.total_candidates, `[${test.name}] Mapper output count matches`, `${mapped.length}`);

  // Validate mapped shapes
  const shapeErrors: string[] = [];
  for (const c of mapped) {
    if (typeof c.id !== 'string' || !c.id) shapeErrors.push(`${c.name}: missing id`);
    if (typeof c.overallScore !== 'number') shapeErrors.push(`${c.name}: overallScore not number`);
    if (!['strong', 'good', 'fair', 'knockout', 'processing', 'parse-failed'].includes(c.signal)) {
      shapeErrors.push(`${c.name}: invalid signal=${c.signal}`);
    }
    if (!Array.isArray(c.knockoutChecks) || c.knockoutChecks.length < 3) {
      shapeErrors.push(`${c.name}: knockoutChecks count=${c.knockoutChecks?.length}`);
    }
  }
  assert(shapeErrors.length === 0, `[${test.name}] All mapped candidates have valid shape`, shapeErrors.length > 0 ? shapeErrors.join('; ') : 'OK');

  // ── Step 9: JD-specific assertions ──────────────────────────────────────
  if (test.assertions) {
    logPhase(`Custom assertions for: ${test.name}`);
    test.assertions(scoreRes, { assert, logData });
  }

  // ── Step 10: Zustand Store Verification ─────────────────────────────────
  logPhase(`Store verification for: ${test.name}`);

  const { useAppStore } = await import('../src/store/app-store');
  const { useCandidateStore } = await import('../src/store/candidate-store');
  const { useJobStore } = await import('../src/store/job-store');

  // Set job ID
  useAppStore.getState().setJobId(jobId);
  assert(useAppStore.getState().jobId === jobId, `[${test.name}] appStore.jobId set`);

  // Populate JD form state
  useJobStore.getState().setTitle(test.jd.title || '');
  (test.jd.must_have_skills || []).forEach((s) => useJobStore.getState().addMustHaveSkill(s));

  // Feed candidates into store
  useCandidateStore.getState().setCandidates(mapped);
  assert(
    useCandidateStore.getState().candidates.length === mapped.length,
    `[${test.name}] candidateStore populated`,
    `${useCandidateStore.getState().candidates.length} candidates`,
  );

  const filtered = useCandidateStore.getState().getFilteredCandidates();
  assert(filtered.length >= 0, `[${test.name}] getFilteredCandidates works`, `${filtered.length} results`);

  // Cleanup store for next test
  useCandidateStore.getState().setCandidates([]);
  useAppStore.getState().setJobId(null);
  useAppStore.getState().setAppPhase('idle');
  // Reset job store skills/keywords for clean next iteration
  for (const s of (test.jd.must_have_skills || [])) {
    useJobStore.getState().removeMustHaveSkill(s);
  }

  const elapsed = ((performance.now() - testStart) / 1000).toFixed(1);
  appendLog(`✅ TEST ${testIndex} complete: ${test.name} (${elapsed}s)`, 'pass');

  return { jobId, scoreRes };
}

// ── Main Test Runner ────────────────────────────────────────────────────────

async function runTests() {
  // Reset
  passCount = 0;
  failCount = 0;
  totalTests = 0;
  const logEl = document.getElementById('log');
  if (logEl) logEl.innerHTML = '';

  const startTime = performance.now();
  setStatus('Running tests...', 'running');
  appendLog('Starting multi-JD E2E API test suite...');
  appendLog(`Testing ${JD_TESTS.length} JD roles × ${ALL_PDF_NAMES.length} resumes`, 'info');

  try {
    // ── Health Check ────────────────────────────────────────────────────────
    logSection('HEALTH CHECK');
    try {
      const health = await checkHealth();
      assert(
        health.status === 'ok' || health.status === 'healthy',
        'Backend is alive',
        `status=${health.status}`,
      );
    } catch (err) {
      assert(false, 'Backend reachable', `${err}`);
      appendLog(`❌ Backend unreachable at ${API_BASE} — start it first!`, 'fail');
      setStatus('Backend unreachable! Start the backend first.', 'fail');
      return;
    }

    // ── Load All PDFs Once ──────────────────────────────────────────────────
    logSection('LOADING ALL PDFs');
    appendLog(`⏳ Loading ${ALL_PDF_NAMES.length} PDFs from test/resumes/...`, 'info');

    const allFiles: File[] = [];
    const failedLoads: string[] = [];
    for (const name of ALL_PDF_NAMES) {
      try {
        const f = await loadTestPdf(name);
        allFiles.push(f);
      } catch {
        failedLoads.push(name);
      }
    }
    assert(allFiles.length > 0, `PDFs loaded`, `${allFiles.length}/${ALL_PDF_NAMES.length}`);
    if (failedLoads.length > 0) {
      logData('Failed to load', failedLoads);
      appendLog(`⚠️ ${failedLoads.length} PDFs failed to load: ${failedLoads.join(', ')}`, 'fail');
    }
    appendLog(`✅ Loaded ${allFiles.length} PDFs`, 'pass');

    // ── Run Each JD Test ────────────────────────────────────────────────────
    const testResults: Array<{ name: string; jobId: string; candidateCount: number; elapsed: string } | null> = [];

    for (let i = 0; i < JD_TESTS.length; i++) {
      updateProgress(i + 1, JD_TESTS.length, JD_TESTS[i].name);
      try {
        const result = await runSingleJdTest(i, JD_TESTS[i], allFiles);
        if (result) {
          testResults.push({
            name: JD_TESTS[i].name,
            jobId: result.jobId,
            candidateCount: result.scoreRes.total_candidates,
            elapsed: '—',
          });
        } else {
          testResults.push(null);
        }
      } catch (err) {
        assert(false, `TEST ${i} (${JD_TESTS[i].name}) completed`, `CRASHED: ${err}`);
        appendLog(`💥 TEST ${i} crashed: ${err}`, 'fail');
        testResults.push(null);
      }
    }

    // ── Summary ─────────────────────────────────────────────────────────────
    const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);

    logSection('FINAL SUMMARY');

    console.log('');
    console.log(`  ${'JD Test'.padStart(4)}  ${'Name'.padEnd(45)}  ${'Job ID'.padEnd(38)}  ${'Candidates'.padStart(10)}`);
    console.log(`  ${'─'.repeat(100)}`);
    testResults.forEach((r, i) => {
      if (r) {
        console.log(`  ${i.toString().padStart(4)}  ${r.name.padEnd(45)}  ${r.jobId.padEnd(38)}  ${r.candidateCount.toString().padStart(10)}`);
      } else {
        console.log(`  ${i.toString().padStart(4)}  ${JD_TESTS[i].name.padEnd(45)}  ${'FAILED'.padEnd(38)}  ${'—'.padStart(10)}`);
      }
    });
    console.log('');

    console.log(`  Total assertions: ${totalTests}`);
    console.log(`  Passed: ${passCount} ✅`);
    console.log(`  Failed: ${failCount} ❌`);
    console.log(`  Time: ${elapsed}s`);

    if (failCount === 0) {
      console.log(
        '%c  ALL TESTS PASSED  ',
        'background: #22c55e; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;',
      );
      setStatus(`✅ ALL ${totalTests} TESTS PASSED across ${JD_TESTS.length} JDs (${elapsed}s)`, 'pass');
    } else {
      console.log(
        `%c  ${failCount} TEST(S) FAILED  `,
        'background: #ef4444; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;',
      );
      setStatus(`❌ ${failCount}/${totalTests} FAILED across ${JD_TESTS.length} JDs (${elapsed}s)`, 'fail');
    }

    appendLog('', 'info');
    appendLog(`━━━ ${passCount}/${totalTests} passed, ${failCount} failed across ${JD_TESTS.length} JD roles (${elapsed}s) ━━━`, failCount > 0 ? 'fail' : 'pass');

    updateProgress(JD_TESTS.length, JD_TESTS.length, 'Done');

  } catch (err) {
    console.error('💥 Test runner crashed:', err);
    setStatus(`💥 CRASH: ${err}`, 'fail');
    appendLog(`💥 Test runner crashed: ${err}`, 'fail');
  }
}

// ── Export & Auto-run ───────────────────────────────────────────────────────

(window as unknown as Record<string, unknown>).runTests = runTests;
runTests();
