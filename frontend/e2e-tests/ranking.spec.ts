import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E UI Test - Resume Ranking', () => {

  // We test multiple JDs sequentially
  test('Should test Resume Ranking with multiple JDs and click random candidates', async ({ page }) => {
    test.setTimeout(180000); // 3 minutes for this complex test

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

    // 3. Upload multiple files for JD 1
    const resumePath1 = path.resolve(process.cwd(), '../backend/data/resumes/1.pdf');
    const resumePath2 = path.resolve(process.cwd(), '../backend/data/resumes/2.pdf');
    
    // We can upload one by one. The first one creates the job.
    await page.locator('input[type="file"]').first().setInputFiles(resumePath1);
    await page.waitForSelector('text=1.pdf');
    
    await page.locator('input[type="file"]').first().setInputFiles(resumePath2);
    await page.waitForSelector('text=2.pdf');

    // 4. Click "Analyze Resumes"
    await page.click('button:has-text("Analyze Resumes")');

    // 5. Wait for the candidate list to render
    await page.waitForSelector('text=Signal', { timeout: 60000 });
    
    // Toggle "Show knockouts" in case our random resumes didn't match the JD
    await page.click('label[for="show-knockouts"]');

    // Wait for at least one candidate row to appear
    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 30000 });

    // 6. Click on the first candidate in the list
    const candidates = page.getByTestId('candidate-row');
    const firstCandidateCard = candidates.first();
    await firstCandidateCard.click();

    // 7. Verify right panel shows the score and details
    // The right panel should display the candidate's score breakdown
    const totalScoreText = page.locator('.text-5xl');
    await expect(totalScoreText).toBeVisible();

    // Verify sections are present like "Match Score" and "Skills"
    await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
    await expect(page.locator('h3:has-text("Skills Analysis")').or(page.locator('text=Skills Analysis'))).toBeVisible();

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
    const resumePath3 = path.resolve(process.cwd(), '../backend/data/resumes/3.pdf');
    const resumePath4 = path.resolve(process.cwd(), '../backend/data/resumes/5.pdf');
    
    await page.locator('input[type="file"]').first().setInputFiles(resumePath3);
    await page.waitForSelector('text=3.pdf');
    
    await page.locator('input[type="file"]').first().setInputFiles(resumePath4);
    await page.waitForSelector('text=5.pdf');

    // 4. Click "Analyze Resumes"
    await page.click('button:has-text("Analyze Resumes")');

    // 5. Wait for the candidate list to render
    await page.waitForSelector('text=Signal', { timeout: 60000 });
    
    // Toggle "Show knockouts" in case our random resumes didn't match the JD
    await page.click('label[for="show-knockouts"]');

    await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 30000 });

    // 6. Click on the second candidate in the list (or the last one)
    const candidates2 = page.getByTestId('candidate-row');
    const count = await candidates2.count();
    expect(count).toBeGreaterThan(0);
    
    // Click the last candidate
    await candidates2.nth(count - 1).click();

    // 7. Verify right panel shows the score and details
    const totalScoreText2 = page.locator('.text-5xl');
    await expect(totalScoreText2).toBeVisible();
    await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
  });

});
