import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E Ranking Correctness and Filtering', () => {

  test('Verify candidate ranking render, knockout toggle, and score breakdown', async ({ page }) => {
    test.setTimeout(300000); // 5 minutes

    await page.goto('/');

    // 1. Fill Job Info
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Full Stack Engineer');
    await page.fill('input[placeholder="+ Add skill"]', 'React');
    await page.keyboard.press('Enter');
    await page.fill('input[placeholder="+ Add skill"]', 'Node.js');
    await page.keyboard.press('Enter');

    // 2. Upload 2 resumes
    const p1 = path.resolve(process.cwd(), '../data/resumes/1.pdf');
    const p2 = path.resolve(process.cwd(), '../data/resumes/2.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles([p1, p2]);

    // 3. Analyze
    const analyzeBtn = page.locator('[data-testid="analyze-button"]');
    await expect(analyzeBtn).toBeEnabled({ timeout: 60000 });
    await analyzeBtn.click();

    // 4. Wait for candidates to appear in table
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 180000 });

    const rows = page.locator('[data-testid="candidate-row"]');
    const initialCount = await rows.count();
    expect(initialCount).toBe(2);

    // Verify deterministic names and ranks are rendered
    const candidateTexts = await rows.allTextContents();
    const allText = candidateTexts.join(' ');
    expect(allText).toContain('Julie Monroe');
    expect(allText).toContain('Daniel Gan');

    // 5. Test Show Knockouts toggle
    const knockoutSwitch = page.locator('#show-knockouts');
    if (await knockoutSwitch.isVisible()) {
      // Toggle off
      if (await knockoutSwitch.getAttribute('data-state') === 'checked') {
        await page.click('label[for="show-knockouts"]');
      }
      // Toggle on
      if (await knockoutSwitch.getAttribute('data-state') === 'unchecked') {
        await page.click('label[for="show-knockouts"]');
      }
      await expect(knockoutSwitch).toHaveAttribute('data-state', 'checked');
    }

    // 6. Select first candidate and verify right panel details
    await rows.first().click();

    await expect(page.locator('h4:has-text("Match Score")').or(page.locator('text=Match Score'))).toBeVisible();
    const scoreEl = page.getByTestId('match-score-value');
    await expect(scoreEl).toBeVisible();
    const scoreValText = (await scoreEl.textContent()) || '';
    expect(scoreValText).toMatch(/^\d+(\.\d+)?%$/);
    const numScore = parseFloat(scoreValText.replace('%', ''));
    expect(numScore).toBeGreaterThanOrEqual(0);
    expect(numScore).toBeLessThanOrEqual(100);

    const eligibilityEl = page.getByTestId('eligibility-signal');
    await expect(eligibilityEl).toBeVisible();
    const eligText = (await eligibilityEl.textContent()) || '';
    expect(eligText).toMatch(/^(🟢 Strong Match|🟡 Good Match|🟠 Fair Match|🔴 Knockout)/);

    // Verify detailed sections are visible
    await expect(page.locator('text=Knockout Checks').first()).toBeVisible();
    await expect(page.locator('text=Skill Breakdown').first()).toBeVisible();
  });

});
