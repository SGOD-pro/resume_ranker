import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import fs from 'fs';
import path from 'path';

const SAMPLE_DIR = '/home/swyra/projects/resume_ranker/scratch_resumes/sample_20';
const FRONTEND_URL = 'http://localhost:5173/';
const BACKEND_URL = 'http://localhost:8000';

async function run() {
  console.log('===============================================================');
  console.log('PHASE 0.5: MEASUREMENT HARNESS FOR CURRENT v2.1 UPLOAD PATH');
  console.log('===============================================================\n');

  // Verify sample files
  const sampleFiles = fs.readdirSync(SAMPLE_DIR)
    .filter(f => f.endsWith('.pdf'))
    .sort()
    .map(f => path.join(SAMPLE_DIR, f));

  console.log(`Found ${sampleFiles.length} sample resumes in ${SAMPLE_DIR}`);
  let totalBytes = 0;
  for (const f of sampleFiles) {
    totalBytes += fs.statSync(f).size;
  }
  console.log(`Total sample size: ${(totalBytes / 1024).toFixed(1)} KB (Avg: ${(totalBytes / sampleFiles.length / 1024).toFixed(1)} KB/file)\n`);

  // ── Step 1: Real Browser Measurement of Presigned S3 Upload Flow ─────────────
  console.log('--- Step 1: Launching Chromium to instrument browser flow ---');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const networkEvents = [];
  const activeRequests = new Map();

  page.on('request', req => {
    const url = req.url();
    const method = req.method();
    const isTarget = url.includes('/upload-sessions') || 
                     url.includes('s3.') || 
                     url.includes('amazonaws.com') ||
                     url.includes('/complete') ||
                     url.includes('/finalize') ||
                     url.includes('/status') ||
                     url.includes('/jobs');

    if (isTarget) {
      activeRequests.set(req, {
        method,
        url,
        startTime: performance.now(),
        startEpoch: new Date().toISOString(),
      });
    }
  });

  page.on('response', resp => {
    const req = resp.request();
    const tracked = activeRequests.get(req);
    if (tracked) {
      const endTime = performance.now();
      const duration = endTime - tracked.startTime;
      networkEvents.push({
        method: tracked.method,
        url: tracked.url,
        status: resp.status(),
        statusText: resp.statusText(),
        durationMs: Math.round(duration),
        startTime: tracked.startTime,
        endTime,
      });
      activeRequests.delete(req);
    }
  });

  page.on('requestfailed', req => {
    const tracked = activeRequests.get(req);
    if (tracked) {
      const endTime = performance.now();
      const duration = endTime - tracked.startTime;
      networkEvents.push({
        method: tracked.method,
        url: tracked.url,
        status: 0,
        statusText: `FAILED: ${req.failure()?.errorText || 'Unknown error'}`,
        durationMs: Math.round(duration),
        startTime: tracked.startTime,
        endTime,
        failed: true,
      });
      activeRequests.delete(req);
    }
  });

  console.log(`Navigating to ${FRONTEND_URL}...`);
  await page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });

  // Baseline zero time
  const t_start = performance.now();

  console.log(`Selecting ${sampleFiles.length} files in file input...`);
  const fileInput = await page.$('input[type="file"]');
  if (!fileInput) {
    throw new Error('File input not found on page!');
  }

  await fileInput.setInputFiles(sampleFiles);

  console.log('Files submitted to browser. Monitoring uploads...');

  // Wait until either:
  // - "Analyze Resumes" button becomes enabled (upload & fast preprocessing finished)
  // - Or 60 seconds timeout
  const maxWaitMs = 60000;
  const pollIntervalMs = 500;
  let elapsed = 0;
  let done = false;

  while (elapsed < maxWaitMs) {
    await page.waitForTimeout(pollIntervalMs);
    elapsed += pollIntervalMs;

    const analyzeBtn = await page.$('button:has-text("Analyze Resumes")');
    if (analyzeBtn) {
      const isDisabled = await analyzeBtn.isDisabled();
      const uploadText = await page.locator('text=resumes uploaded').first().textContent().catch(() => '');
      if (!isDisabled || (uploadText && uploadText.includes(`${sampleFiles.length} resumes uploaded`))) {
        done = true;
        break;
      }
    }
  }

  const t_end = performance.now();
  const totalWallClockMs = t_end - t_start;
  console.log(`Browser flow finished in ${totalWallClockMs.toFixed(1)} ms (${(totalWallClockMs / 1000).toFixed(2)} s)\n`);

  await browser.close();

  // Categorize network events
  const sessionInitEvents = networkEvents.filter(e => e.url.includes('/upload-sessions') && !e.url.includes('/complete') && !e.url.includes('/finalize') && e.method === 'POST');
  const s3PutEvents = networkEvents.filter(e => e.method === 'PUT' && (e.url.includes('s3.') || e.url.includes('amazonaws.com')));
  const completeEvents = networkEvents.filter(e => e.url.includes('/complete') && e.method === 'POST');
  const finalizeEvents = networkEvents.filter(e => e.url.includes('/finalize') && e.method === 'POST');
  const statusEvents = networkEvents.filter(e => e.url.includes('/status') || (e.url.includes('/upload-sessions/') && e.method === 'GET'));

  console.log('=== WATERFALL SUMMARY (Current v2.1 Upload Flow) ===');
  console.log(`Total Wall Clock: ${totalWallClockMs.toFixed(1)} ms (${(totalWallClockMs / 1000).toFixed(2)} s)`);
  console.log(`Files Processed:  ${sampleFiles.length} files`);
  console.log();

  if (sessionInitEvents.length > 0) {
    const e = sessionInitEvents[0];
    console.log(`1. POST /upload-sessions: status ${e.status} in ${e.durationMs} ms`);
  } else {
    console.log('1. POST /upload-sessions: [None captured]');
  }

  console.log(`\n2. S3 Direct PUTs (${s3PutEvents.length} captured):`);
  let s3TotalDuration = 0;
  s3PutEvents.forEach((e, i) => {
    s3TotalDuration += e.durationMs;
    const filenameMatch = e.url.match(/raw\/([^/?]+)/);
    const label = filenameMatch ? filenameMatch[1] : `File #${i+1}`;
    console.log(`   - PUT #${i + 1} (${label}): status ${e.status} in ${e.durationMs} ms`);
  });
  const avgS3Put = s3PutEvents.length ? (s3TotalDuration / s3PutEvents.length).toFixed(1) : 'N/A';
  console.log(`   -> S3 PUT average: ${avgS3Put} ms per file (concurrency pool of 4)`);

  console.log(`\n3. POST /complete calls (${completeEvents.length} captured):`);
  let completeTotalDuration = 0;
  completeEvents.forEach((e, i) => {
    completeTotalDuration += e.durationMs;
    console.log(`   - Complete #${i + 1}: status ${e.status} in ${e.durationMs} ms`);
  });
  const avgComplete = completeEvents.length ? (completeTotalDuration / completeEvents.length).toFixed(1) : 'N/A';
  console.log(`   -> Complete average: ${avgComplete} ms per call`);

  console.log(`\n4. POST /finalize call (${finalizeEvents.length} captured):`);
  if (finalizeEvents.length > 0) {
    const e = finalizeEvents[0];
    console.log(`   - Finalize: status ${e.status} (${e.statusText}) in ${e.durationMs} ms`);
    if (e.failed) {
      console.log(`     ⚠️ Finalize request failed / aborted: ${e.statusText}`);
    }
  } else {
    console.log('   - Finalize: [None captured]');
  }

  console.log(`\n5. Time to First Status Poll:`);
  if (statusEvents.length > 0) {
    const firstStatus = statusEvents[0];
    const timeToFirstStatus = firstStatus.startTime - t_start;
    console.log(`   - First status request fired at +${Math.round(timeToFirstStatus)} ms, duration: ${firstStatus.durationMs} ms, status ${firstStatus.status}`);
  } else {
    console.log('   - First status: [None captured]');
  }

  // ── Step 2: Measured Benchmark of Direct Lambda Multipart Upload ─────────────
  console.log('\n===============================================================');
  console.log('--- Step 2: Measured Benchmark of Multipart Upload via Lambda ---');
  console.log('===============================================================');
  console.log('Testing legacy/fallback POST /api/v2/jobs/{id}/resumes directly with multipart payload...\n');

  try {
    // Create a job first
    const createRes = await fetch(`${BACKEND_URL}/api/v2/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Benchmark Job' }),
    });
    const jobData = await createRes.json();
    const jobId = jobData.id || jobData.job_id;

    // Build multipart FormData
    const formData = new FormData();
    for (const filePath of sampleFiles) {
      const fileBuffer = fs.readFileSync(filePath);
      const blob = new Blob([fileBuffer], { type: 'application/pdf' });
      formData.append('files', blob, path.basename(filePath));
    }

    const t_lambda_start = performance.now();
    const uploadRes = await fetch(`${BACKEND_URL}/api/v2/jobs/${jobId}/resumes`, {
      method: 'POST',
      body: formData,
    });
    const t_lambda_end = performance.now();
    const lambdaUploadMs = t_lambda_end - t_lambda_start;

    const uploadJson = await uploadRes.json().catch(() => ({}));
    console.log(`Direct-through-Lambda Multipart Upload Result:`);
    console.log(`- Status:              HTTP ${uploadRes.status}`);
    console.log(`- Total 20-file batch: ${lambdaUploadMs.toFixed(1)} ms (${(lambdaUploadMs / 1000).toFixed(2)} s)`);
    console.log(`- Accepted files:      ${uploadJson.total_accepted || uploadJson.accepted?.length || 0}`);
    console.log(`- Rejected files:      ${uploadJson.rejected?.length || 0}`);
  } catch (err) {
    console.error('Direct-through-Lambda upload failed:', err.message);
  }

  // Save results to scratch json file
  const reportPath = '/home/swyra/projects/resume_ranker/scratch_resumes/phase_0_5_measurement.json';
  fs.writeFileSync(reportPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    sampleCount: sampleFiles.length,
    totalSizeBytes: totalBytes,
    totalWallClockMs,
    sessionInitEvents,
    s3PutEvents,
    completeEvents,
    finalizeEvents,
    statusEvents,
  }, null, 2));

  console.log(`\nDetailed waterfall measurements saved to: ${reportPath}`);
}

run().catch(err => {
  console.error('Measurement failed:', err);
  process.exit(1);
});
