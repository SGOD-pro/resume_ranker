# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: ui.spec.ts >> E2E UI Test - Dashboard and ATS Checker >> Should test Dashboard fields, upload resume, and perform ATS check
- Location: e2e-tests/ui.spec.ts:6:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 60000ms exceeded.
Call log:
  - waiting for locator('text=Signal') to be visible

```

# Page snapshot

```yaml
- generic [ref=e2]:
  - generic [ref=e3]:
    - banner [ref=e4]:
      - heading "AI Resume Screener" [level=3] [ref=e5]
      - generic [ref=e6]:
        - button "Settings" [ref=e7]: ⚙
        - button "Help" [ref=e8]: "?"
    - generic [ref=e10]:
      - generic [ref=e17]:
        - heading "+ New Job Opening" [level=3] [ref=e18]
        - generic:
          - generic:
            - generic:
              - generic: Job Title
              - textbox "Job Title":
                - /placeholder: Senior Backend Eng.
                - text: Senior React Developer
            - generic:
              - generic: Department
              - textbox "Department":
                - /placeholder: Engineering
                - text: Engineering
          - generic:
            - generic: Job Description
            - textbox "Paste JD here..."
            - generic:
              - button "Upload JD PDF"
          - generic:
            - generic: Must-Have Skills
            - generic:
              - generic:
                - text: React
                - button "Remove React": ×
              - generic:
                - text: TypeScript
                - button "Remove TypeScript": ×
            - generic:
              - textbox "+ Add skill"
          - generic:
            - generic: Nice-to-Have
            - generic:
              - textbox "+ Add item"
          - generic:
            - generic: Experience
            - generic:
              - generic:
                - generic: Min years
                - spinbutton: "3"
              - generic:
                - generic: Max years
                - spinbutton: "7"
          - generic:
            - generic: Education
            - generic:
              - generic:
                - generic: Required
                - combobox:
                  - generic: Bachelor
              - generic:
                - generic: Field
                - textbox "CS / related"
          - generic:
            - generic: Keywords
            - textbox "+ Add keyword"
          - generic:
            - generic: Weights
            - generic:
              - generic:
                - generic:
                  - generic: Skills
                  - generic: 40%
                - generic:
                  - generic:
                    - slider
              - generic:
                - generic:
                  - generic: Experience
                  - generic: 25%
                - generic:
                  - generic:
                    - slider
              - generic:
                - generic:
                  - generic: Keywords
                  - generic: 20%
                - generic:
                  - generic:
                    - slider
              - generic:
                - generic:
                  - generic: Education
                  - generic: 15%
                - generic:
                  - generic:
                    - slider
        - generic [ref=e20]:
          - button "Loading Extracting…" [disabled]:
            - generic:
              - status "Loading"
              - text: Extracting…
      - separator [ref=e23]
      - generic [ref=e27]:
        - generic [ref=e28]:
          - generic [ref=e29]:
            - heading "Upload Resumes" [level=4] [ref=e30]
            - generic [ref=e31] [cursor=pointer]:
              - paragraph [ref=e32]: Drop PDFs here or click browse
              - button "Browse Files" [disabled]
            - generic [ref=e33]:
              - paragraph [ref=e34]: 1 resumes uploaded · 0 analyzed ✓
              - paragraph [ref=e35]: 1 processing...
          - generic [ref=e36]:
            - generic [ref=e37]:
              - generic [ref=e38]: "Filter:"
              - combobox [ref=e39]:
                - generic: All
            - generic [ref=e40]:
              - generic [ref=e41]: "Sort:"
              - combobox [ref=e42]:
                - generic: Score
            - textbox "name or skill..." [ref=e44]
        - generic [ref=e46]:
          - status "Loading" [ref=e47]
          - heading "Extracting Resume Data" [level=4] [ref=e49]
          - paragraph [ref=e50]: Parsing PDFs and extracting structured information…
        - generic [ref=e55]:
          - generic [ref=e56]:
            - switch "Show knockouts" [ref=e57]
            - generic [ref=e58] [cursor=pointer]: Show knockouts
          - button "Export CSV" [ref=e59]
      - separator [ref=e60]
      - generic [ref=e65]:
        - paragraph [ref=e66]: No Candidate Selected
        - paragraph [ref=e67]: Click a candidate from the list to view details.
  - region "Notifications alt+T"
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | import * as path from 'path';
  3  | 
  4  | test.describe('E2E UI Test - Dashboard and ATS Checker', () => {
  5  | 
  6  |   test('Should test Dashboard fields, upload resume, and perform ATS check', async ({ page }) => {
  7  |     test.setTimeout(120000); // Allow up to 2 minutes for full E2E run
  8  |     
  9  |     // 1. Visit the Dashboard (Root URL)
  10 |     await page.goto('/');
  11 | 
  12 |     // 2. Fill the Job Info Section
  13 |     await page.fill('input[placeholder="Senior Backend Eng."]', 'Senior React Developer');
  14 |     await page.fill('input[placeholder="Engineering"]', 'Engineering');
  15 | 
  16 |     // 3. Add Must-Have Skills
  17 |     await page.fill('input[placeholder="+ Add skill"]', 'React');
  18 |     await page.keyboard.press('Enter');
  19 |     
  20 |     await page.fill('input[placeholder="+ Add skill"]', 'TypeScript');
  21 |     await page.keyboard.press('Enter');
  22 | 
  23 |     // 4. Fill Experience & Education
  24 |     await page.locator('text=Min years').locator('xpath=following-sibling::input').fill('3');
  25 |     await page.locator('text=Max years').locator('xpath=following-sibling::input').fill('7');
  26 | 
  27 |     // 5. Upload a resume via the hidden file input (creates the job)
  28 |     const resumePath = path.resolve(process.cwd(), '../backend/data/resumes/cv (1872).pdf');
  29 |     await page.locator('input[type="file"]').first().setInputFiles(resumePath);
  30 |     
  31 |     // Wait for the upload to complete (file to appear in the list)
  32 |     await page.waitForSelector('text=cv (1872).pdf');
  33 | 
  34 |     // 6. Click "Analyze Resumes" to trigger extraction and scoring
  35 |     await page.click('button:has-text("Analyze Resumes")');
  36 | 
  37 |     // 7. Wait for processing progress to finish and candidate list to render
> 38 |     await page.waitForSelector('text=Signal', { timeout: 60000 });
     |                ^ TimeoutError: page.waitForSelector: Timeout 60000ms exceeded.
  39 |     
  40 |     // 8. Navigate to ATS Checker
  41 |     await page.goto('/ats-checker');
  42 | 
  43 |     // 10. Upload a resume to ATS Checker
  44 |     await page.locator('input[type="file"]').first().setInputFiles(resumePath);
  45 | 
  46 |     // 11. Wait for ATS score result
  47 |     await page.waitForSelector('text=ATS Compatibility Score', { timeout: 30000 });
  48 |     
  49 |     // Check if the layout score appears
  50 |     const scoreText = page.locator('.text-5xl');
  51 |     await expect(scoreText).toBeVisible();
  52 |   });
  53 | 
  54 | });
  55 | 
```