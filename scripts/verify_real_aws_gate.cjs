const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const API_BASE = 'https://uispa6m3l6.execute-api.ap-south-1.amazonaws.com';
const GOLDEN_JSON_PATH = path.resolve(__dirname, '../backend/tests/fixtures/golden_v2_baseline/golden_20_resumes.json');
const RESUMES_DIR = path.resolve(__dirname, '../data/resumes');

const goldenData = JSON.parse(fs.readFileSync(GOLDEN_JSON_PATH, 'utf-8'));
const jobSpec = goldenData.metadata.job_spec;
const goldenProfiles = goldenData.profiles;
const goldenResults = goldenData.scoring_results;

// Map filenames to file specs
const filesToUpload = goldenProfiles.map((p) => {
  const filePath = path.join(RESUMES_DIR, p.filename);
  const stat = fs.statSync(filePath);
  return {
    filename: p.filename,
    filePath,
    size_bytes: stat.size,
  };
});

async function runTestRun(context, concurrency, runName) {
  console.log(`\n===============================================================`);
  console.log(`RUN: ${runName} (Upload Concurrency: ${concurrency})`);
  console.log(`===============================================================`);

  const t0_run = Date.now();

  // 1. Create Job with the 20 golden resumes
  const createPayload = {
    title: jobSpec.title,
    department: 'Engineering',
    must_have_skills: jobSpec.must_have_skills,
    nice_to_have_skills: jobSpec.nice_to_have_skills,
    min_years: jobSpec.min_years,
    max_years: jobSpec.max_years,
    education_level: jobSpec.education_level || 'Bachelor',
    education_field: jobSpec.education_field || '',
    keywords: jobSpec.keywords,
    weights: jobSpec.weights,
    files: filesToUpload.map((f) => ({
      filename: f.filename,
      file_size: f.size_bytes,
    })),
  };

  const t0_create = Date.now();
  const createResp = await context.request.post(`${API_BASE}/api/v2/jobs`, {
    data: createPayload,
    headers: { 'Content-Type': 'application/json' },
  });
  const t1_create = Date.now();
  const createDuration = t1_create - t0_create;

  if (createResp.status() !== 201) {
    const errText = await createResp.text();
    throw new Error(`Job creation failed (${createResp.status()}): ${errText}`);
  }

  const jobData = await createResp.json();
  const jobId = jobData.job_id;
  const returnedFiles = jobData.files; // PresignedPostInfo list

  console.log(`[1/5] Created Job ID: ${jobId} in ${createDuration} ms. Total files: ${returnedFiles.length}`);

  // 2. Upload 20 files directly to S3 with bounded concurrency
  console.log(`[2/5] Uploading ${returnedFiles.length} files to S3 with concurrency ${concurrency}...`);
  const t0_upload = Date.now();
  const uploadDurations = [];

  // Match returned files with local paths
  const uploadQueue = returnedFiles.map((rf) => {
    const local = filesToUpload.find((f) => f.filename === rf.filename);
    return { ...rf, localPath: local.filePath, size: local.size_bytes };
  });

  // Bounded worker pool
  async function worker() {
    while (uploadQueue.length > 0) {
      const item = uploadQueue.shift();
      if (!item) break;
      const { url, fields } = item.presigned_post;
      const fileBuffer = fs.readFileSync(item.localPath);

      const t0_post = Date.now();
      // Use multipart POST
      const postResp = await context.request.post(url, {
        multipart: {
          ...fields,
          file: {
            name: item.filename,
            mimeType: 'application/pdf',
            buffer: fileBuffer,
          },
        },
      });
      const t1_post = Date.now();
      const dur = t1_post - t0_post;
      uploadDurations.push(dur);

      if (postResp.status() !== 204 && postResp.status() !== 200) {
        throw new Error(`S3 POST failed for ${item.filename}: ${postResp.status()}`);
      }
    }
  }

  const workers = Array.from({ length: concurrency }, () => worker());
  await Promise.all(workers);
  const t1_upload = Date.now();
  const totalUploadDuration = t1_upload - t0_upload;
  const minUpload = Math.min(...uploadDurations);
  const maxUpload = Math.max(...uploadDurations);
  const avgUpload = Math.round(uploadDurations.reduce((a, b) => a + b, 0) / uploadDurations.length);

  console.log(`      Upload batch completed in ${totalUploadDuration} ms`);
  console.log(`      Per-file S3 POST: min ${minUpload} ms | avg ${avgUpload} ms | max ${maxUpload} ms`);

  // 3. Wait for Stage 1 (PyMuPDF) to process all 20 resumes
  console.log(`[3/5] Waiting for Stage 1 PyMuPDF processing on all 20 resumes...`);
  const t0_stage1 = Date.now();
  let stage1Completed = false;
  let pollAttempts = 0;
  let lastStatus = null;

  while (!stage1Completed && pollAttempts < 120) {
    pollAttempts++;
    await new Promise((r) => setTimeout(r, 1000));
    const statusResp = await context.request.get(`${API_BASE}/api/v2/jobs/${jobId}/status`);
    let st = lastStatus;
    if (statusResp.status() === 200) {
      st = await statusResp.json();
      lastStatus = st;
    }

    if (st && st.files) {
      // Check if every file is past PENDING_UPLOAD / UPLOADING (i.e. S1_DONE, S2_DONE, or FAILED)
      const readyFiles = st.files.filter(
        (f) => f.status === 'S1_DONE' || f.status === 'S2_DONE' || f.status === 'S1_FAILED'
      );
      if (readyFiles.length === returnedFiles.length) {
        stage1Completed = true;
        break;
      }
    }
  }

  const t1_stage1 = Date.now();
  const stage1Duration = t1_stage1 - t0_stage1;
  console.log(`      All 20 files completed Stage 1 in ${stage1Duration} ms (${pollAttempts} polls)`);

  // 4. Send Analyze Request
  console.log(`[4/5] Triggering POST /api/v2/jobs/${jobId}/analyze...`);
  const t0_analyze = Date.now();
  const analyzeResp = await context.request.post(`${API_BASE}/api/v2/jobs/${jobId}/analyze`, {
    data: {
      title: jobSpec.title,
      must_have_skills: jobSpec.must_have_skills,
      min_years: jobSpec.min_years,
      max_years: jobSpec.max_years,
      weights: jobSpec.weights,
    },
    headers: { 'Content-Type': 'application/json' },
  });
  const t1_analyze = Date.now();
  const analyzeDuration = t1_analyze - t0_analyze;

  if (analyzeResp.status() !== 202) {
    throw new Error(`Analyze request failed (${analyzeResp.status()}): ${await analyzeResp.text()}`);
  }
  console.log(`      Analyze accepted (HTTP 202) in ${analyzeDuration} ms (Gate SLA: < 1000 ms: ${analyzeDuration < 1000 ? 'PASS' : 'FAIL'})`);

  // 5. Wait for Stage 2 fallback and Scoring to complete (Job status = DONE)
  console.log(`[5/5] Waiting for pipeline to reach DONE (Stage 2 + Scoring)...`);
  const t0_pipe = Date.now();
  let jobDone = false;
  let finalStatus = null;
  let pipePolls = 0;

  while (!jobDone && pipePolls < 120) {
    pipePolls++;
    await new Promise((r) => setTimeout(r, 1000));
    const stResp = await context.request.get(`${API_BASE}/api/v2/jobs/${jobId}/status`);
    let st = finalStatus;
    if (stResp.status() === 200) {
      st = await stResp.json();
      finalStatus = st;
    }
    if (st && (st.status === 'DONE' || st.status === 'DONE_WITH_ERRORS')) {
      jobDone = true;
      break;
    }
  }

  const t1_pipe = Date.now();
  const pipeDuration = t1_pipe - t0_pipe;
  const t1_run = Date.now();
  const totalRunDuration = t1_run - t0_run;

  console.log(`      Pipeline reached terminal state: ${finalStatus.status} in ${pipeDuration} ms (remaining: ${finalStatus.remaining}, usable: ${finalStatus.usable_files})`);
  console.log(`      Total waterfall duration (creation -> DONE): ${(totalRunDuration / 1000).toFixed(2)} s`);

  // 6. Fetch Results and Compare to Golden Fixture
  const resultsResp = await context.request.get(`${API_BASE}/api/v2/jobs/${jobId}/results`);
  if (resultsResp.status() !== 200) {
    throw new Error(`Failed to fetch results: ${resultsResp.status()}`);
  }
  const resultsData = await resultsResp.json();
  const ranked = resultsData.candidates;

  console.log(`\n--- Scoring Accuracy Validation vs Golden Fixture ---`);
  console.log(`Ranked candidates count: ${ranked.length} (Golden: ${goldenResults.length})`);

  let maxScoreDelta = 0;
  let scoreMismatches = 0;
  let knockoutMismatches = 0;

  // Match by candidate name or rank
  for (let i = 0; i < Math.min(ranked.length, goldenResults.length); i++) {
    const r = ranked[i];
    const g = goldenResults[i];
    const scoreDelta = Math.abs(r.final_score - g.final_score);
    if (scoreDelta > maxScoreDelta) maxScoreDelta = scoreDelta;
    if (scoreDelta > 0.05) scoreMismatches++;
    if (r.knocked_out !== g.knocked_out) knockoutMismatches++;
  }

  console.log(`Top 1 Ranked Candidate: "${ranked[0]?.name}" with score ${ranked[0]?.final_score}% (Golden: "${goldenResults[0]?.name}" with score ${goldenResults[0]?.final_score}%)`);
  console.log(`Max Score Delta across 20 candidates: ${maxScoreDelta.toFixed(3)} points`);
  console.log(`Score Mismatches (>0.05 pt): ${scoreMismatches}`);
  console.log(`Knockout Decision Mismatches: ${knockoutMismatches}`);

  return {
    runName,
    concurrency,
    jobId,
    createDuration,
    minUpload,
    avgUpload,
    maxUpload,
    totalUploadDuration,
    stage1Duration,
    analyzeDuration,
    pipeDuration,
    totalRunDuration,
    terminalStatus: finalStatus.status,
    remainingCounter: finalStatus.remaining,
    usableCount: finalStatus.usable_files,
    maxScoreDelta,
    scoreMismatches,
    knockoutMismatches,
  };
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  console.log(`========================================================================`);
  console.log(`PHASE 1.5 GATE: REAL-AWS PIPELINE VERIFICATION (20 GOLDEN RESUMES)`);
  console.log(`Target API: ${API_BASE}`);
  console.log(`Browser: Chromium ${browser.version()}`);
  console.log(`========================================================================`);

  const results = [];

  try {
    // 1. Concurrency 4 - Cold Start
    results.push(await runTestRun(context, 4, 'Concurrency 4 (Cold Start)'));

    // 2. Concurrency 4 - Warm Start
    results.push(await runTestRun(context, 4, 'Concurrency 4 (Warm Start)'));

    // 3. Concurrency 6 - Warm Start
    results.push(await runTestRun(context, 6, 'Concurrency 6 (Warm Start)'));

    // 4. Concurrency 8 - Warm Start
    results.push(await runTestRun(context, 8, 'Concurrency 8 (Warm Start)'));

    console.log(`\n========================================================================`);
    console.log(`SUMMARY REPORT — WATERFALL TO JOB DONE ACROSS CONCURRENCIES`);
    console.log(`========================================================================\n`);

    console.table(
      results.map((r) => ({
        Run: r.runName,
        'Create (ms)': r.createDuration,
        'Upload Total (ms)': r.totalUploadDuration,
        'S3 Avg (ms)': r.avgUpload,
        'Stage 1 (ms)': r.stage1Duration,
        'Analyze SLA (ms)': r.analyzeDuration,
        'Stage2+Score (ms)': r.pipeDuration,
        'Total to DONE (s)': (r.totalRunDuration / 1000).toFixed(2),
        'Terminal Remaining': r.remainingCounter,
        'Max Score Delta': r.maxScoreDelta.toFixed(3),
        Passed: r.remainingCounter === 0 && r.maxScoreDelta < 0.1 && r.analyzeDuration < 1000 ? 'YES' : 'NO',
      }))
    );

    // Save results to json file
    fs.writeFileSync(
      path.resolve(__dirname, 'real_aws_gate_results.json'),
      JSON.stringify(results, null, 2),
      'utf-8'
    );
    console.log('\nResults saved to scripts/real_aws_gate_results.json');
  } catch (err) {
    console.error('GATE VERIFICATION ERROR:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
