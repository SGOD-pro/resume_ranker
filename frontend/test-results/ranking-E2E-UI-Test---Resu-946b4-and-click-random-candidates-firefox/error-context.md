# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: ranking.spec.ts >> E2E UI Test - Resume Ranking >> Should test Resume Ranking with multiple JDs and click random candidates
- Location: e2e-tests/ranking.spec.ts:7:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.text-5xl')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.text-5xl')

```

# Test source

```ts
  1   | import { test, expect } from '@playwright/test';
  2   | import * as path from 'path';
  3   | 
  4   | test.describe('E2E UI Test - Resume Ranking', () => {
  5   | 
  6   |   // We test multiple JDs sequentially
  7   |   test('Should test Resume Ranking with multiple JDs and click random candidates', async ({ page }) => {
  8   |     test.setTimeout(180000); // 3 minutes for this complex test
  9   | 
  10  |     // --------- FIRST JD ---------
  11  |     await page.goto('/');
  12  | 
  13  |     // 1. Fill Job Info for JD 1
  14  |     await page.fill('input[placeholder="Senior Backend Eng."]', 'Data Scientist');
  15  |     await page.fill('input[placeholder="Engineering"]', 'Data');
  16  | 
  17  |     // 2. Add Must-Have Skills for JD 1
  18  |     await page.fill('input[placeholder="+ Add skill"]', 'Python');
  19  |     await page.keyboard.press('Enter');
  20  |     await page.fill('input[placeholder="+ Add skill"]', 'Machine Learning');
  21  |     await page.keyboard.press('Enter');
  22  | 
  23  |     // 3. Upload multiple files for JD 1
  24  |     const resumePath1 = path.resolve(process.cwd(), '../backend/data/resumes/1.pdf');
  25  |     const resumePath2 = path.resolve(process.cwd(), '../backend/data/resumes/2.pdf');
  26  |     
  27  |     // We can upload one by one. The first one creates the job.
  28  |     await page.locator('input[type="file"]').first().setInputFiles(resumePath1);
  29  |     await page.waitForSelector('text=1.pdf');
  30  |     
  31  |     await page.locator('input[type="file"]').first().setInputFiles(resumePath2);
  32  |     await page.waitForSelector('text=2.pdf');
  33  | 
  34  |     // 4. Click "Analyze Resumes"
  35  |     await page.click('button:has-text("Analyze Resumes")');
  36  | 
  37  |     // 5. Wait for the candidate list to render
  38  |     await page.waitForSelector('text=Signal', { timeout: 60000 });
  39  |     
  40  |     // Toggle "Show knockouts" in case our random resumes didn't match the JD
  41  |     await page.click('label[for="show-knockouts"]');
  42  | 
  43  |     // Wait for at least one candidate row to appear
  44  |     await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 30000 });
  45  | 
  46  |     // 6. Click on the first candidate in the list
  47  |     const candidates = page.getByTestId('candidate-row');
  48  |     const firstCandidateCard = candidates.first();
  49  |     await firstCandidateCard.click();
  50  | 
  51  |     // 7. Verify right panel shows the score and details
  52  |     // The right panel should display the candidate's score breakdown
  53  |     const totalScoreText = page.locator('.text-5xl');
> 54  |     await expect(totalScoreText).toBeVisible();
      |                                  ^ Error: expect(locator).toBeVisible() failed
  55  | 
  56  |     // Verify sections are present like "Match Score" and "Skills"
  57  |     await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
  58  |     await expect(page.locator('h3:has-text("Skills Analysis")').or(page.locator('text=Skills Analysis'))).toBeVisible();
  59  | 
  60  |     // --------- SECOND JD ---------
  61  |     // Go back to the dashboard to start a new job
  62  |     await page.goto('/');
  63  | 
  64  |     // 1. Fill Job Info for JD 2
  65  |     await page.fill('input[placeholder="Senior Backend Eng."]', 'Frontend Developer');
  66  |     await page.fill('input[placeholder="Engineering"]', 'UI/UX');
  67  | 
  68  |     // 2. Add Must-Have Skills for JD 2
  69  |     await page.fill('input[placeholder="+ Add skill"]', 'React');
  70  |     await page.keyboard.press('Enter');
  71  |     await page.fill('input[placeholder="+ Add skill"]', 'Tailwind');
  72  |     await page.keyboard.press('Enter');
  73  | 
  74  |     // 3. Upload multiple files for JD 2
  75  |     const resumePath3 = path.resolve(process.cwd(), '../backend/data/resumes/3.pdf');
  76  |     const resumePath4 = path.resolve(process.cwd(), '../backend/data/resumes/5.pdf');
  77  |     
  78  |     await page.locator('input[type="file"]').first().setInputFiles(resumePath3);
  79  |     await page.waitForSelector('text=3.pdf');
  80  |     
  81  |     await page.locator('input[type="file"]').first().setInputFiles(resumePath4);
  82  |     await page.waitForSelector('text=5.pdf');
  83  | 
  84  |     // 4. Click "Analyze Resumes"
  85  |     await page.click('button:has-text("Analyze Resumes")');
  86  | 
  87  |     // 5. Wait for the candidate list to render
  88  |     await page.waitForSelector('text=Signal', { timeout: 60000 });
  89  |     
  90  |     // Toggle "Show knockouts" in case our random resumes didn't match the JD
  91  |     await page.click('label[for="show-knockouts"]');
  92  | 
  93  |     await page.waitForSelector('[data-testid="candidate-row"]', { timeout: 30000 });
  94  | 
  95  |     // 6. Click on the second candidate in the list (or the last one)
  96  |     const candidates2 = page.getByTestId('candidate-row');
  97  |     const count = await candidates2.count();
  98  |     expect(count).toBeGreaterThan(0);
  99  |     
  100 |     // Click the last candidate
  101 |     await candidates2.nth(count - 1).click();
  102 | 
  103 |     // 7. Verify right panel shows the score and details
  104 |     const totalScoreText2 = page.locator('.text-5xl');
  105 |     await expect(totalScoreText2).toBeVisible();
  106 |     await expect(page.locator('h4:has-text("Match Score")')).toBeVisible();
  107 |   });
  108 | 
  109 | });
  110 | 
```