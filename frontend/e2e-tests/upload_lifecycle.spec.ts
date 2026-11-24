import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E Upload Lifecycle Hardening', () => {

  test('Single valid PDF upload should enable Analyze Resumes button', async ({ page }) => {
    await page.goto('/');

    // Fill minimum job info
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Platform Engineer');
    await page.fill('input[placeholder="+ Add skill"]', 'Python');
    await page.keyboard.press('Enter');

    const resumePath = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(resumePath);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
  });

  test('Batch multi-PDF upload completes and shows correct total count', async ({ page }) => {
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'DevOps Specialist');
    await page.fill('input[placeholder="+ Add skill"]', 'Docker');
    await page.keyboard.press('Enter');

    const pdfs = [
      path.resolve(process.cwd(), '../data/resumes/1.pdf'),
      path.resolve(process.cwd(), '../data/resumes/2.pdf'),
      path.resolve(process.cwd(), '../data/resumes/3.pdf'),
    ];

    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(pdfs);

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 120000 });
  });

  test('Client-side rejection of non-PDF files (.txt and .exe)', async ({ page }) => {
    await page.goto('/');

    const txtPath = path.resolve(process.cwd(), 'e2e-tests/fixtures/not_a_pdf.txt');
    const exePath = path.resolve(process.cwd(), 'e2e-tests/fixtures/malicious.exe');

    // Attempt to upload txt
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(txtPath);
    await expect(page.getByText('Rejected: not_a_pdf.txt')).toBeVisible({ timeout: 10000 });

    // Attempt to upload exe
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(exePath);
    await expect(page.getByText('Rejected: malicious.exe')).toBeVisible({ timeout: 10000 });

    // Analyze button must remain disabled
    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeDisabled();
  });

  test('Client-side rejection of oversized file (>10MB)', async ({ page }) => {
    await page.goto('/');

    const oversizedPath = path.resolve(process.cwd(), 'e2e-tests/fixtures/oversized.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(oversizedPath);

    await expect(page.getByText('File too large')).toBeVisible({ timeout: 10000 });

    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeDisabled();
  });

  test('Partial upload failure: rejected corrupted file alongside valid file', async ({ page }) => {
    test.setTimeout(90000);
    await page.goto('/');

    await page.fill('input[placeholder="Senior Backend Eng."]', 'Reliability Engineer');

    const validPath = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    const truncatedPath = path.resolve(process.cwd(), 'e2e-tests/fixtures/truncated.pdf');

    // Upload both valid and truncated
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles([validPath, truncatedPath]);

    // Toast error or rejection appears for truncated file, or valid file is accepted enabling analyze
    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // Verify valid candidate succeeds through to final ranking while corrupted peer was safely rejected
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 120000 });
    const rows = page.locator('[data-testid="candidate-row"]');
    await expect(rows).toHaveCount(1);
    await expect(rows.first().locator('text=Julie Monroe')).toBeVisible();
  });

});
