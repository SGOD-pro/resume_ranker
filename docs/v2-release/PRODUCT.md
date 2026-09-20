# SWYRA Sortlist v2 — Product Specification

This is the authoritative product document for SWYRA Sortlist v2. It serves as a binding product specification.

## Product Identity

- **Name:** SWYRA Sortlist
- **Tagline:** "Explainable Candidate Review Workspace"
- **Positioning:** This is NOT an autonomous hiring system, and NOT a generic enterprise ATS.
- **Core Promise:** "Every recommendation is evidence-linked, configurable, reviewable, and reversible by a human recruiter."

## Target Users

SWYRA Sortlist is designed specifically for:
- Small hiring teams (2-15 people)
- Recruitment agencies handling multiple clients
- Technical recruiters screening engineering candidates

## Core Capabilities (v2 Release)

The v2 release includes the following core capabilities:
1. Job creation with versioned criteria and explicit scoring weights.
2. PDF resume upload, extraction, and structured parsing.
3. Evidence-first candidate ranking with transparent relevance scores.
4. Score breakdown with skill provenance (direct/inferred/related).
5. Human decision workflow: NEW → REVIEWING → SHORTLISTED → REJECTED → INTERVIEW → ARCHIVED.
6. System recommendation and human decision are SEPARATE fields.
7. Notes, tags, activity timeline.
8. Candidate comparison (2-4 candidates).
9. ATS Health Check (separate candidate-facing tool).
10. CSV export.

## What Sortlist Does NOT Do

To maintain transparency and ethical hiring standards, Sortlist explicitly avoids the following:
- **Does NOT** make hiring decisions.
- **Does NOT** auto-reject candidates.
- **Does NOT** use prestige bonuses, gap penalties, or protected attributes.
- **Does NOT** claim scores are hiring recommendations.
- **Does NOT** guarantee ATS compatibility.

## Decision States

System recommendations and human decisions are always separate. The system cannot change a human decision.

### System States
- `UNSCORED`
- `SCORED`
- `REVIEW_REQUIRED`
- `ABSTAIN`

### Human States
- `NEW`
- `REVIEWING`
- `SHORTLISTED`
- `REJECTED`
- `INTERVIEW`
- `ARCHIVED`

## Scoring Philosophy

- Scores represent **RELEVANCE**, not suitability or overall hiring scores.
- The scoring range is a normalized 0-100 scale.
- Every score has an adjacent "Explain" action to provide immediate context.
- Scoring inputs are strictly limited to:
  - Explicit job requirements
  - Candidate-provided work evidence
  - Skills
  - Role-relevant experience
  - Job-relevant projects
  - Certifications
  - Education (only when the job explicitly requires it)

## Prohibited Scoring Factors

The following factors are never used as ranking criteria:
- Protected attributes: Age, gender, race, caste, religion, nationality, disability, marital status
- Personal details: Photo, address
- Name-based or location-based proxies
- Institutional prestige: University prestige, employer prestige, or FAANG bonuses
- Work history: Career gaps
- Subjective measures: Inferred "culture fit"

## ATS Health Check Positioning

The ATS Health Check is a separate, candidate-facing tool with the following characteristics:
- It returns actionable feedback including: parseability, missing/weak sections, formatting risks, extracted contact fields, and concrete fixes.
- It **does NOT** claim that passing means a resume will "beat ATS systems".
- It includes a transparent limitations section.
- Uploaded data is deleted after a short, documented retention period.
