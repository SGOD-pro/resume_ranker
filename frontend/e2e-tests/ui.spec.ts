import { test, expect } from '@playwright/test';
import * as path from 'path';

test.describe('E2E UI Test - Dashboard and ATS Checker', () => {

  test('Should test Dashboard fields, upload resume, and perform ATS check', async ({ page }) => {
    test.setTimeout(120000); // Allow up to 2 minutes for full E2E run
    
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
    const resumePath = path.resolve(process.cwd(), '../backend/data/resumes/cv (1872).pdf');
    await page.locator('input[type="file"]').first().setInputFiles(resumePath);
    
    // Wait for the upload to complete (file to appear in the list)
    await page.waitForSelector('text=cv (1872).pdf');

    // 6. Click "Analyze Resumes" to trigger extraction and scoring
    await page.click('button:has-text("Analyze Resumes")');

    // 7. Wait for processing progress to finish and candidate list to render
    await page.waitForSelector('text=Signal', { timeout: 60000 });
    
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
