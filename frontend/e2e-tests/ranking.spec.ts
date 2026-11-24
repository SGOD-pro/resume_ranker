import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

test.describe('E2E UI Test - Resume Ranking', () => {

  // We test multiple JDs sequentially with 50 PDFs for JD 1
  test('Should test Resume Ranking with multiple JDs and click random candidates', async ({ page }) => {
    test.setTimeout(1800000); // 30 minutes for 50-resume multi-JD test

    page.on('console', (msg) => console.log('[BROWSER CONSOLE]', msg.type(), msg.text()));
    page.on('pageerror', (err) => console.log('[BROWSER ERROR]', err.message));

    // --------- FIRST JD ---------
    await page.goto('/');

    // 1. Fill Job Info for JD 1
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Data Scientist');
    await page.fill('input[placeholder="Engineering"]', 'Data');

    // 2. Add Must-Have Skills for JD 1
    await page.fill('input[placeholder="+ Add skill"]', 'Python');
    await page.keyboard.press('Enter');
    await page.fill('input[placeholder="+ Add skill"]', 'Machine Learning');
    await page.keyboard.press('Enter');

    // 3. Upload 50 resumes for JD 1
    const resumesDir = path.resolve(process.cwd(), '../data/resumes');
    const fiftyPdfs = fs.readdirSync(resumesDir)
      .filter((f) => f.endsWith('.pdf'))
      .sort()
      .slice(0, 50)
      .map((f) => path.join(resumesDir, f));

    console.log(`[TEST] Uploading ${fiftyPdfs.length} resumes for JD 1...`);
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(fiftyPdfs);

    // 4. Click "Analyze Resumes" when upload completes and button enables
    const analyzeBtn1 = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn1).toBeEnabled({ timeout: 360000 });
    await analyzeBtn1.click();

    // Ensure knockouts are visible
    const knockoutSwitch1 = page.locator('#show-knockouts');
    if (await knockoutSwitch1.getAttribute('data-state') === 'unchecked') {
      await page.click('label[for="show-knockouts"]');
    }

    // 5. Wait for the candidate list to render
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 1200000 });

    // 6. Click on the first candidate in the list
    const candidates = page.getByTestId('candidate-row');
    const firstCandidateCard = candidates.first();
    await firstCandidateCard.click();

    // 7. Verify right panel shows exact numeric score, eligibility, and breakdown
    const totalScoreText = page.getByTestId('match-score-value');
    await expect(totalScoreText).toBeVisible();
    const scoreContent = await totalScoreText.textContent();
    expect(scoreContent).toMatch(/^\d+(\.\d+)?%$/);
    const scoreNum = parseFloat(scoreContent!.replace('%', ''));
    expect(scoreNum).toBeGreaterThanOrEqual(0);
    expect(scoreNum).toBeLessThanOrEqual(100);

    // Assert eligibility signal
    const eligibilitySignal = page.getByTestId('eligibility-signal');
    await expect(eligibilitySignal).toBeVisible();
    const signalText = await eligibilitySignal.textContent();
    expect(signalText).toMatch(/^(🟢 Strong Match|🟡 Good Match|🟠 Fair Match|🔴 Knockout)/);

    // Verify sections are present: Match Score, Knockout Checks, and Skill Breakdown
    await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
    await expect(page.locator('h4:has-text("Knockout Checks")')).toBeVisible();
    await expect(page.locator('h4:has-text("Skill Breakdown")').or(page.locator('text=Skill Breakdown'))).toBeVisible();

    // --------- SECOND JD ---------
    // Go back to the dashboard to start a new job
    await page.goto('/');

    // 1. Fill Job Info for JD 2
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Frontend Developer');
    await page.fill('input[placeholder="Engineering"]', 'UI/UX');

    // 2. Add Must-Have Skills for JD 2
    await page.fill('input[placeholder="+ Add skill"]', 'React');
    await page.keyboard.press('Enter');
    await page.fill('input[placeholder="+ Add skill"]', 'Tailwind');
    await page.keyboard.press('Enter');

    // 3. Upload multiple files for JD 2
    const resumePath3 = path.resolve(process.cwd(), '../data/resumes/3.pdf');
    const resumePath4 = path.resolve(process.cwd(), '../data/resumes/5.pdf');
    
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles([resumePath3, resumePath4]);

    // 4. Click "Analyze Resumes" when upload completes and button enables
    const analyzeBtn2 = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn2).toBeEnabled({ timeout: 180000 });
    await analyzeBtn2.click();

    // Ensure knockouts are visible
    const knockoutSwitch2 = page.locator('#show-knockouts');
    if (await knockoutSwitch2.getAttribute('data-state') === 'unchecked') {
      await page.click('label[for="show-knockouts"]');
    }

    // 5. Wait for the candidate list to render (2 PDFs can still hit Nova slow path)
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 600000 });

    // 6. Click on the second candidate in the list (or the last one)
    const candidates2 = page.getByTestId('candidate-row');
    const count = await candidates2.count();
    expect(count).toBeGreaterThan(0);
    
    // Click the last candidate
    await candidates2.nth(count - 1).click();

    // 7. Verify right panel shows exact numeric score and eligibility for JD 2
    const totalScoreText2 = page.getByTestId('match-score-value');
    await expect(totalScoreText2).toBeVisible();
    const scoreContent2 = await totalScoreText2.textContent();
    expect(scoreContent2).toMatch(/^\d+(\.\d+)?%$/);
    const scoreNum2 = parseFloat(scoreContent2!.replace('%', ''));
    expect(scoreNum2).toBeGreaterThanOrEqual(0);
    expect(scoreNum2).toBeLessThanOrEqual(100);

    const eligibilitySignal2 = page.getByTestId('eligibility-signal');
    await expect(eligibilitySignal2).toBeVisible();
    const signalText2 = await eligibilitySignal2.textContent();
    expect(signalText2).toMatch(/^(🟢 Strong Match|🟡 Good Match|🟠 Fair Match|🔴 Knockout)/);

    await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
    await expect(page.locator('h4:has-text("Knockout Checks")')).toBeVisible();
  });

});
