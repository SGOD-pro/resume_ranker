# Acceptance Tests (v2 Release)

This document defines the acceptance tests required for the v2 release of Resume Ranker. 

## Test Format
Each test follows this structure:
- **ID:** Unique identifier
- **Priority:** P0 (Critical), P1 (High), P2 (Medium), P3 (Low)
- **Description:** What the test validates
- **Preconditions:** Required state before execution
- **Steps:** Actions to perform
- **Expected Result:** The verifiable outcome

---

## 1. Security (P0)

### SEC-01: Authentication & Authorization
- **ID:** SEC-01 | **Priority:** P0
- **Description:** Verify endpoints require valid authentication.
- **Preconditions:** Unauthenticated client, valid user credentials.
- **Steps:** 1. Access API without token. 2. Access API with valid token.
- **Expected Result:** 1. 401 Unauthorized. 2. 200 OK.

### SEC-02: Tenant Isolation & IDOR Prevention
- **ID:** SEC-02 | **Priority:** P0
- **Description:** Ensure users cannot access cross-tenant data.
- **Preconditions:** Two distinct tenant accounts (A and B).
- **Steps:** Tenant A attempts to fetch Tenant B's resume via ID.
- **Expected Result:** 403 Forbidden or 404 Not Found.

### SEC-03: Rate Limiting
- **ID:** SEC-03 | **Priority:** P0
- **Description:** Enforce API rate limits.
- **Preconditions:** Valid API token.
- **Steps:** Send requests exceeding the configured limit (e.g., 100/min).
- **Expected Result:** 429 Too Many Requests response after threshold.

### SEC-04: File Validation & CORS
- **ID:** SEC-04 | **Priority:** P0
- **Description:** Reject malicious files and verify CORS policies.
- **Preconditions:** Executable file disguised as PDF, external domain client.
- **Steps:** 1. Upload malicious file. 2. Make cross-origin request from unauthorized domain.
- **Expected Result:** 1. 400 Bad Request (Invalid file type). 2. CORS error / blocked by browser.

---

## 2. Workflow (P1)

### WF-01: Job CRUD
- **ID:** WF-01 | **Priority:** P1
- **Description:** Create, Read, Update, and Delete job profiles.
- **Preconditions:** Authenticated user.
- **Steps:** Perform standard CRUD operations via UI/API.
- **Expected Result:** State updates correctly in DB and UI reflects changes.

### WF-02: E2E Candidate Processing
- **ID:** WF-02 | **Priority:** P1
- **Description:** Full pipeline from upload to export.
- **Preconditions:** Existing Job Profile.
- **Steps:** Upload resume -> Extract -> Score -> View results -> View details -> Check evidence provenance -> Update decision state -> Add notes -> Export.
- **Expected Result:** All steps complete successfully without errors; provenance traces back to raw text.

---

## 3. Scoring (P1)

### SCR-01: Deterministic Same-Input Test
- **ID:** SCR-01 | **Priority:** P1
- **Description:** Identical inputs must yield identical scores.
- **Preconditions:** Fixed resume and job description.
- **Steps:** Score the same resume 5 times.
- **Expected Result:** All 5 executions return the exact same score and factor ledger.

### SCR-02: Prohibited-Attributes Test
- **ID:** SCR-02 | **Priority:** P1
- **Description:** Verify prohibited factors do not influence scores.
- **Preconditions:** Prestige bonus disabled, gap penalty disabled.
- **Steps:** Score resumes with prestigious universities and employment gaps.
- **Expected Result:** Factor ledger shows no points awarded/deducted for these attributes.

### SCR-03: Abstain / Review-Required State
- **ID:** SCR-03 | **Priority:** P1
- **Description:** Handle low-confidence extractions safely.
- **Preconditions:** Heavily redacted or malformed resume.
- **Steps:** Process the resume.
- **Expected Result:** System flags as `REVIEW_REQUIRED` instead of assigning a score.

---

## 4. ATS Integrations (P2)

### ATS-01: Sync Lifecycle
- **ID:** ATS-01 | **Priority:** P2
- **Description:** Validate ATS sync constraints.
- **Preconditions:** Configured ATS integration.
- **Steps:** 1. Check parseability of ATS payload. 2. Verify deletion of temp files after processing. 3. Observe rate limits.
- **Expected Result:** Parsed successfully, files deleted immediately, honors ATS rate limits. Limitations disclaimer is visible.

---

## 5. UI Requirements

### UI-01: Responsive Breakpoints & Keyboard Nav
- **ID:** UI-01 | **Priority:** P1
- **Description:** Ensure accessibility and mobile responsiveness.
- **Preconditions:** Desktop and mobile viewports.
- **Steps:** Resize window, navigate completely via Tab/Enter.
- **Expected Result:** No broken layouts; all actions executable via keyboard.

### UI-02: System States & Score Explanation
- **ID:** UI-02 | **Priority:** P1
- **Description:** Proper feedback for various states.
- **Preconditions:** Mocked slow network, mocked error responses.
- **Steps:** Trigger empty state, loading state, and error state. View a scored candidate.
- **Expected Result:** Clear UI states (spinners, error toasts, empty illustrations). The score explanation must clearly detail the factor ledger.
