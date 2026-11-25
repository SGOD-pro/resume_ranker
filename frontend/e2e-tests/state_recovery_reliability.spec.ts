import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E State Recovery and Reliability', () => {
  test.beforeEach(async () => {
    test.setTimeout(240000);
  });

  test('Browser refresh during analysis reattaches to active job and completes', async ({ page }) => {
    await page.goto('/');

    // 1. Fill job criteria
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Distributed Systems Architect');
    await page.fill('input[placeholder="+ Add skill"]', 'Distributed Systems');
    await page.keyboard.press('Enter');

    // 2. Upload resume
    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(p1);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });

    let analyzePostCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/analyze') && req.method() === 'POST') {
        analyzePostCount++;
      }
    });

    // 3. Click analyze and wait for analyze POST to be accepted
    const analyzeResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/analyze') && res.request().method() === 'POST'
    );
    await analyzeBtn.click();
    await analyzeResponsePromise;
    expect(analyzePostCount).toBe(1);

    // 4. Reload browser while processing is underway
    await page.reload();

    // 5. Verify page reattaches: job criteria restored, and no secondary analyze POST occurs
    await expect(page.locator('input[placeholder="Senior Backend Eng."]')).toHaveValue('Distributed Systems Architect', { timeout: 15000 });
    expect(analyzePostCount).toBe(1);

    // 6. Wait for reattached job to finish and render candidate rows
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(1);
    await expect(rows.first().locator('text=Julie Monroe')).toBeVisible();
  });

  test('Browser refresh after completion preserves candidate list and selected candidate details', async ({ page }) => {
    await page.goto('/');

    // 1. Fill job criteria
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Platform Engineer');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');

    // 2. Upload two resumes
    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    const p2 = path.resolve(process.cwd(), '../data/resumes/2.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles([p1, p2]);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // 3. Wait for candidates to be rendered
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 180000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(2);

    // 4. Select candidate and record details
    await rows.first().click();
    const detailNameEl = page.locator('[data-testid="candidate-detail-name"]');
    await expect(detailNameEl).toBeVisible();
    const selectedName = await detailNameEl.textContent();
    expect(selectedName).toBeTruthy();

    const scoreEl = page.locator('[data-testid="match-score-value"]');
    await expect(scoreEl).toBeVisible();
    const selectedScore = await scoreEl.textContent();

    // 5. Reload browser
    await page.reload();

    // 6. Verify candidates and selected candidate detail persist across reload
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 30000 });
    await expect(page.locator('[data-testid="candidate-row"]')).toHaveCount(2);

    const reloadedDetailName = page.locator('[data-testid="candidate-detail-name"]');
    await expect(reloadedDetailName).toBeVisible({ timeout: 15000 });
    expect(await reloadedDetailName.textContent()).toBe(selectedName);

    const reloadedScoreEl = page.locator('[data-testid="match-score-value"]');
    await expect(reloadedScoreEl).toBeVisible();
    expect(await reloadedScoreEl.textContent()).toBe(selectedScore);
  });

  test('Filter reset restores candidate list when all candidates are filtered out', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Data Lead');
    await page.fill('input[placeholder="+ Add skill"]', 'Python');
    await page.keyboard.press('Enter');

    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(p1);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(1);

    // Filter out all candidates using search input
    const searchInput = page.locator('input[placeholder="name or skill..."]');
    await searchInput.fill('NonExistentKeywordXYZ999');

    // Confirm candidate row is hidden and empty state with reset button appears
    await expect(rows).toHaveCount(0);
    await expect(page.locator('text=No candidates match the current filters.')).toBeVisible();

    const resetBtn = page.locator('[data-testid="reset-filters-button"]');
    await expect(resetBtn).toBeVisible();
    await resetBtn.click();

    // Confirm candidate list is restored
    await expect(rows).toHaveCount(1);
    await expect(searchInput).toHaveValue('');
  });

  test('Authoritative backend scores match frontend displayed scores without client drift', async ({ page, context }) => {
    await page.goto('/');

    let capturedJobId = '';
    let capturedSessionId = '';
    page.on('response', async (res) => {
      try {
        const url = new URL(res.url());
        if (url.pathname === '/api/v2/jobs' && res.request().method() === 'POST') {
          const json = await res.json();
          if (json.job_id || json.id) {
            capturedJobId = json.job_id || json.id;
          }
          if (json.session_id) {
            capturedSessionId = json.session_id;
          }
        }
      } catch (err) {
        void err;
      }
    });

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Backend Engineer');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');

    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(p1);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });

    // Fetch authoritative results directly from backend
    expect(capturedJobId).not.toBe('');
    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === 'job_session_id')?.value;
    const finalSessionId = capturedSessionId || sessionCookie || '';
    const backendRes = await fetch(`http://localhost:8000/api/v2/jobs/${capturedJobId}/results`, {
      headers: {
        ...(finalSessionId ? { 'X-Session-ID': finalSessionId, Cookie: `job_session_id=${finalSessionId}` } : {}),
      },
    });
    expect(backendRes.ok).toBe(true);
    const backendData = await backendRes.json();
    const backendCandidate = backendData.candidates[0];

    // Backend score calculation: if 0..1 then multiply by 100, if > 1 it is percentage
    const rawScore = backendCandidate.final_score ?? backendCandidate.overall_score ?? backendCandidate.relevance_score ?? 0;
    const expectedScorePct = rawScore <= 1.0 ? Math.round(rawScore * 1000) / 10 : Math.round(rawScore * 10) / 10;
    const expectedScoreStr = expectedScorePct % 1 === 0 ? `${expectedScorePct}%` : `${expectedScorePct.toFixed(1)}%`;

    // Verify row score in table matches backend
    const rowScoreEl = page.locator('[data-testid="candidate-row-score"]').first();
    const displayedRowScore = (await rowScoreEl.textContent())?.trim();
    expect(displayedRowScore).toBe(expectedScoreStr);

    // Verify detail panel match score matches backend
    await page.locator('[data-testid="candidate-row"]').first().click();
    const detailScoreEl = page.locator('[data-testid="match-score-value"]');
    const displayedDetailScore = (await detailScoreEl.textContent())?.trim();
    expect(displayedDetailScore).toBe(expectedScoreStr);
  });
});
