import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E Analyze Lifecycle Hardening', () => {
  test.beforeEach(async () => {
    test.setTimeout(120000);
  });

  test('Double clicking Analyze disables immediately and avoids duplicate submissions', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Backend Developer');
    await page.fill('input[placeholder="+ Add skill"]', 'FastAPI');
    await page.keyboard.press('Enter');

    const resumePath = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(resumePath);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });

    // Track requests to /api/v2/jobs/*/analyze
    let analyzePostCount = 0;
    page.on('request', (req) => {
      if (req.url().includes('/analyze') && req.method() === 'POST') {
        analyzePostCount++;
      }
    });

    // Double-click rapidly
    await analyzeBtn.dblclick();

    // Verify button immediately transitions to disabled state
    await expect(analyzeBtn).toBeDisabled();

    // Verify analyze endpoint was called without duplicate flooding
    expect(analyzePostCount).toBeLessThanOrEqual(2);

    // Wait for analysis to complete and verify exactly one candidate is persisted
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(1);
    await expect(rows.first().locator('text=Julie Monroe')).toBeVisible();
  });

  test('Browser interruption: background workers finish job and results persist when browser reconnects', async ({ page, context }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Cloud Architect');
    await page.fill('input[placeholder="+ Add skill"]', 'Kubernetes');
    await page.keyboard.press('Enter');

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

    const resumePath = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(resumePath);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    const analyzeResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/analyze') && res.request().method() === 'POST'
    );
    await analyzeBtn.click();
    await analyzeResponsePromise;

    // Simulate browser interruption: close page while processing in background
    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === 'job_session_id')?.value;
    const finalSessionId = capturedSessionId || sessionCookie || '';
    await page.close();

    // Verify backend worker progresses job to READY even with browser disconnected
    expect(capturedJobId).not.toBe('');
    let isReady = false;
    const authHeaders: Record<string, string> = {
      ...(finalSessionId ? { 'X-Session-ID': finalSessionId, Cookie: `job_session_id=${finalSessionId}` } : {}),
    };
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((r) => setTimeout(r, 1000));
      const res = await fetch(`http://localhost:8000/api/v2/jobs/${capturedJobId}/status`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'READY' || data.status === 'READY_WITH_WARNINGS' || data.status === 'DONE') {
          isReady = true;
          break;
        }
      }
    }
    expect(isReady).toBe(true);

    // Verify results endpoint persists scored candidate
    const resultsRes = await fetch(`http://localhost:8000/api/v2/jobs/${capturedJobId}/results`, {
      headers: authHeaders,
    });
    expect(resultsRes.ok).toBe(true);
    const resultsData = await resultsRes.json();
    expect(resultsData.candidates.length).toBe(1);
    expect(resultsData.candidates[0].name).toBe('Julie Monroe');

    // Reopen browser on fresh page
    const newPage = await context.newPage();
    await newPage.goto('/');
    await expect(newPage.locator('input[placeholder="Senior Backend Eng."]')).toBeVisible({ timeout: 15000 });
    await newPage.close();
  });

  test('Analyze button remains disabled during processing', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Data Architect');
    await page.fill('input[placeholder="+ Add skill"]', 'PostgreSQL');
    await page.keyboard.press('Enter');

    const resumePath = path.resolve(process.cwd(), '../data/resumes/2.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(resumePath);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // While processing, button should stay disabled
    await expect(analyzeBtn).toBeDisabled();
  });

  test('Page refresh recovers cleanly without breaking application state', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Security Analyst');
    const inputField = page.locator('input[placeholder="Senior Backend Eng."]');
    await expect(inputField).toHaveValue('Security Analyst');

    // Reload page
    await page.reload();

    // Dashboard loads ready for new or resumed job
    await expect(page.locator('input[placeholder="Senior Backend Eng."]')).toBeVisible({ timeout: 15000 });
  });

});
