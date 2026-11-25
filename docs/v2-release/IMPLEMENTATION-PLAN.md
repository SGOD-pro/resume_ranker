# Resume Ranker v2: Implementation Plan

This document outlines the phased implementation plan for the Resume Ranker v2 release.

## Phase A: Security Foundation (P0) — Week 1-2
1. Remove `.env` from git, add `.env.example`, update `.gitignore`
2. Add auth module: user/org models, registration, login, session management
3. Add auth middleware to all routes
4. Add tenant isolation (`org_id` scoping on all queries)
5. Add rate limiting middleware
6. Add security headers middleware
7. Add file validation (type, size, page count, magic bytes)
8. Add audit logging
9. Remove prestige bonus, gap penalty from scorer
10. Fix production assert in `b2b_ats_scorer.py`
11. Remove debug `console.group` calls from frontend
12. Fix hardcoded `localhost:8000` in `AtsCheckerPage.tsx`

## Phase B: Evidence-First Workflow (P1) — Week 3-4
1. Add human decision model and endpoints
2. Add score versioning (`score_version`, `policy_version`, `job_version`)
3. Add factor ledger to scored candidates
4. Add abstain/review-required states
5. Add candidate comparison endpoint
6. Add CSV export endpoint
7. Add notes, tags, activity timeline
8. Update frontend with decision states, explain actions, notes UI
9. Add responsive layout with mobile fallback
10. Fix accessibility issues (contrast, focus states, aria-live, emoji)

## Phase C: ATS Health Check (P2) — Week 5
1. Add transparent limitations to ATS checker
2. Add data retention/deletion for ATS uploads
3. Add rate limiting to ATS-check endpoint
4. Fix bounding box stub in `b2b_ats_scorer.py`

## Phase D: Test Suite & Evaluation — Week 5-6
1. Create 25+ curated test resumes
2. Build benchmark command
3. Write scoring policy tests
4. Write auth/tenant isolation tests
5. Write Playwright E2E tests
6. Create gold-set fixtures

## Phase E: Documentation Cleanup — Week 6
1. Update `README.md` to link to v2-release docs
2. Mark superseded docs clearly
3. Remove dead code (`deploy` dir, `PDFPipelineV3`, dead services)
4. Final audit and release checklist
