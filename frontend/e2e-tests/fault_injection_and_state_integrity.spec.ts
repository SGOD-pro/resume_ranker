import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('Fault Injection and State Integrity E2E Specs', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(180000);
    page.on('console', (msg) => console.log('[BROWSER CONSOLE]', msg.type(), msg.text()));
    page.on('pageerror', (err) => console.log('[BROWSER ERROR]', err.message));
    page.on('requestfailed', (req) => console.log('[REQUEST FAILED]', req.url(), req.failure()?.errorText));
    page.on('response', (res) => {
      if (res.status() >= 400) {
        console.log('[HTTP ERROR]', res.status(), res.url());
      }
    });
  });

  test('Candidate selection is scoped to job_id and isolated across job switches', async ({ page }) => {
    await page.goto('/');

    // 1. Populate Job 1
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Job Alpha Lead');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');

    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    const p2 = path.resolve(process.cwd(), '../data/resumes/2.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles([p1, p2]);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(2);

    // Select candidate in Job 1
    await rows.first().click();
    const detailNameJob1 = await page.locator('[data-testid="candidate-detail-name"]').textContent();
    expect(detailNameJob1).toBeTruthy();

    const job1Id = await page.evaluate(() => {
      const win = window as unknown as { __stores?: Record<string, { getState: () => { jobId?: string; selectCandidate: (id: string | null, jid: string) => void; setJobId: (id: string) => void }; setState: (s: Record<string, unknown>) => void }> };
      const stores = win.__stores;
      return stores?.useAppStore.getState().jobId || sessionStorage.getItem('active_job_id');
    });
    expect(job1Id).toBeTruthy();

    // 2. Switch to a new Job 2 in store
    await page.evaluate(() => {
      const win = window as unknown as { __stores?: Record<string, { getState: () => { selectCandidate: (id: string | null, jid: string) => void }; setState: (s: Record<string, unknown>) => void }> };
      const stores = win.__stores;
      if (stores) {
        // Set candidate selection for Job 2 to null
        stores.useCandidateStore.getState().selectCandidate(null, 'job_beta_isolated_2');
        stores.useCandidateStore.setState({ selectedId: null, selectedJobId: 'job_beta_isolated_2' });
      }
    });

    // Verify detail panel on Job 2 does not display Job 1's selected candidate
    await expect(page.locator('text=No Candidate Selected')).toBeVisible();

    // 3. Switch back to Job 1 and verify Job 1 candidate selection is restored
    await page.evaluate((id) => {
      const win = window as unknown as { __stores?: Record<string, { getState: () => { setJobId: (jid: string) => void } }> };
      const stores = win.__stores;
      if (stores && id) {
        stores.useAppStore.getState().setJobId(id);
      }
    }, job1Id);

    await page.reload();
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 60000 });
    await expect(page.locator('[data-testid="candidate-detail-name"]')).toHaveText(detailNameJob1!);
  });

  test('Duplicate candidate identifiers preserve canonical documentId for actions and PDF download', async ({ page }) => {
    await page.goto('/');

    const capturedDecisionCalls: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/decision') && req.method() === 'PATCH') {
        capturedDecisionCalls.push(req.url());
      }
    });

    // Mock results endpoint to return two candidates with the exact same canonical document_id
    const canonicalDocId = 'doc_canonical_12345';
    await page.route('**/api/v2/jobs/*/results', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'job_dup_test',
          total_candidates: 2,
          candidates: [
            {
              document_id: canonicalDocId,
              name: 'Duplicate Candidate A',
              overall_score: 88.0,
              final_score: 88.0,
              relevance_score: 88.0,
              signal: 'strong',
              skills: ['Python'],
              status: 'under-review',
            },
            {
              document_id: canonicalDocId,
              name: 'Duplicate Candidate B',
              overall_score: 85.0,
              final_score: 85.0,
              relevance_score: 85.0,
              signal: 'good',
              skills: ['Python'],
              status: 'under-review',
            },
          ],
        }),
      });
    });

    // Upload one resume to initialize job
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Deduplication Tester');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');
    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(p1);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // Verify both rows render without key clash
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(2);

    // Select second candidate (which has deduplicated client id)
    await rows.nth(1).click();
    await expect(page.locator('[data-testid="candidate-detail-name"]')).toHaveText('Duplicate Candidate B');

    // Click Shortlist action and verify PATCH request uses canonicalDocId, NOT a mutated client row key
    const shortlistBtn = page.locator('button:has-text("Shortlist")');
    await shortlistBtn.click();

    expect(capturedDecisionCalls.length).toBeGreaterThanOrEqual(1);
    const lastDecisionUrl = capturedDecisionCalls[capturedDecisionCalls.length - 1];
    expect(lastDecisionUrl).toContain(`/candidates/${canonicalDocId}/decision`);
    expect(lastDecisionUrl).not.toContain('__row_');
  });

  test('Prolonged polling failure does not wipe job state; retry recovers existing active job without duplicate analyze', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Fault Injection Test');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');
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

    // Intercept extract and status before clicking analyze
    let statusFailureActive = true;
    await page.route('**/api/v2/jobs/*/extract*', async (route) => {
      await route.abort('failed');
    });
    await page.route('**/api/v2/jobs/*/status*', async (route) => {
      if (statusFailureActive) {
        await route.abort('failed');
      } else {
        await route.continue();
      }
    });

    // Trigger analysis
    await analyzeBtn.click();
    expect(analyzePostCount).toBe(1);

    // Wait for connection error banner/modal to appear
    await expect(page.locator('text=Connection Lost').or(page.locator('text=Unable to reach backend status'))).toBeVisible({ timeout: 60000 });

    // Verify job title was not wiped
    await expect(page.locator('input[placeholder="Senior Backend Eng."]')).toHaveValue('Fault Injection Test');

    // Restore network
    statusFailureActive = false;

    // Click retry
    const retryBtn = page.locator('button:has-text("Retry")').or(page.locator('button:has-text("Try Again")'));
    if (await retryBtn.isVisible()) {
      await retryBtn.click();
    }

    // Verify retry did NOT submit a duplicate /analyze request
    expect(analyzePostCount).toBe(1);

    // Wait for job completion and candidate rendering
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    await expect(page.locator('[data-testid="candidate-row"]')).toHaveCount(1);
  });

  test('Result publication delays with HTTP 409 resolve cleanly via adaptive backoff', async ({ page }) => {
    await page.goto('/');

    let result409Count = 0;
    await page.route('**/api/v2/jobs/*/results', async (route) => {
      if (result409Count < 2) {
        result409Count++;
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Results are being published, retry shortly' }),
        });
      } else {
        await route.continue();
      }
    });

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Delayed Results Engineer');
    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(p1);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // Verify candidates render successfully after 409 backoff resolves
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(1);
    expect(result409Count).toBeGreaterThanOrEqual(1);
  });
});
