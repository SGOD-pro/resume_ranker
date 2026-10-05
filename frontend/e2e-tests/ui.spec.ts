import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E UI Test - Dashboard and ATS Checker', () => {

  test('Should test Dashboard fields, upload resume, and perform ATS check', async ({ page }) => {
    test.setTimeout(1200000); // 20 minutes for parallel test run
    
    page.on('console', (msg) => console.log('[BROWSER CONSOLE]', msg.type(), msg.text()));
    page.on('pageerror', (err) => console.log('[BROWSER ERROR]', err.message));

    // 1. Visit the Dashboard (Root URL)
    await page.goto('/');

    // 2. Fill the Job Info Section
    await page.fill('input[placeholder="Senior Backend Eng."]', 'Senior React Developer');
    await page.fill('input[placeholder="Engineering"]', 'Engineering');

    // 3. Add Must-Have Skills
    await page.fill('input[placeholder="+ Add skill"]', 'React');
    await page.keyboard.press('Enter');
    
    await page.fill('input[placeholder="+ Add skill"]', 'TypeScript');
    await page.keyboard.press('Enter');

    // 4. Fill Experience & Education
    await page.locator('text=Min years').locator('xpath=following-sibling::input').fill('3');
    await page.locator('text=Max years').locator('xpath=following-sibling::input').fill('7');

    // 5. Upload a resume via the hidden file input (creates the job)
    const resumePath = path.resolve(process.cwd(), '../backend/data/resumes/1.pdf');
    await page.locator('input[data-testid="resume-file-input"]').setInputFiles(resumePath);
    
    // Wait for upload to complete: "Analyze Resumes" button becomes enabled
    const analyzeBtn = page.locator('button:has-text("Analyze Resumes")');
    await expect(analyzeBtn).toBeEnabled({ timeout: 180000 });
    await analyzeBtn.click();

    // Ensure knockouts are visible
    const knockoutSwitch = page.locator('#show-knockouts');
    if (await knockoutSwitch.getAttribute('data-state') === 'unchecked') {
      await page.click('label[for="show-knockouts"]');
    }

    // 7. Wait for processing progress to finish and candidate list to render
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 900000 });
    
    // 8. Navigate to ATS Checker
    await page.goto('/ats-checker');

    // 10. Upload a resume to ATS Checker
    await page.locator('input[type="file"]').first().setInputFiles(resumePath);

    // 11. Wait for ATS score result
    await page.waitForSelector('text=Parseability Score', { timeout: 30000 });
    
    // Check if the layout score appears
    const scoreText = page.locator('.text-5xl');
    await expect(scoreText).toBeVisible();
  });

});
