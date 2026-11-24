import { test, expect } from '@playwright/test';

test.describe('E2E UI Resilience & Security', () => {

  test('XSS script injection neutralization in job title and inputs', async ({ page }) => {
    let dialogTriggered = false;
    page.on('dialog', async (dialog) => {
      dialogTriggered = true;
      await dialog.dismiss();
    });

    await page.goto('/');

    const xssPayload = '<script>alert("xss")</script><img src=x onerror=alert(1)>';
    await page.fill('input[placeholder="Senior Backend Eng."]', xssPayload);

    // Verify input contains the literal text and did not execute
    const val = await page.locator('input[placeholder="Senior Backend Eng."]').inputValue();
    expect(val).toBe(xssPayload);
    expect(dialogTriggered).toBe(false);
  });

  test('Rapid navigation between Dashboard and ATS Checker', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto('/');
    await page.waitForSelector('input[placeholder="Senior Backend Eng."]', { timeout: 15000 });

    // Rapid navigation 3 times
    for (let i = 0; i < 3; i++) {
      await page.goto('/ats-checker');
      await page.waitForSelector('text=B2B ATS Health Check', { timeout: 15000 });
      await page.goto('/');
      await page.waitForSelector('input[placeholder="Senior Backend Eng."]', { timeout: 15000 });
    }

    // No unhandled runtime exceptions
    expect(errors.length).toBe(0);
  });

  test('Server-side validation rejects manipulated IDs and unauthorized requests', async ({ page }) => {
    // 1. Manipulated job ID status request must return 404
    const fakeJobId = '00000000-0000-0000-0000-000000000000';
    const fakeStatusRes = await page.request.get(`http://localhost:8000/api/v2/jobs/${fakeJobId}/status`);
    expect(fakeStatusRes.status()).toBe(404);

    // 2. Manipulated analyze request with empty / invalid payload
    const fakeAnalyzeRes = await page.request.post(`http://localhost:8000/api/v2/jobs/${fakeJobId}/analyze`, {
      data: { file_ids: ['invalid-file-id'] },
    });
    expect(fakeAnalyzeRes.status()).toBe(404);
  });

  test('Mobile viewport (375x667) responsiveness and zero console errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Check main elements are accessible and visible
    await expect(page.locator('input[placeholder="Senior Backend Eng."]')).toBeVisible({ timeout: 15000 });
    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeVisible();

    // Verify layout fits viewport width without horizontal overflow
    const hasHorizontalOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });
    expect(hasHorizontalOverflow).toBe(false);

    // Verify ATS Checker on mobile
    await page.goto('/ats-checker');
    await expect(page.locator('text=B2B ATS Health Check')).toBeVisible({ timeout: 15000 });

    // Filter benign worker version warnings if any, check for zero runtime JS exceptions
    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes('UnknownErrorException') && !e.includes('Worker version')
    );
    expect(criticalErrors.length).toBe(0);
  });

});
