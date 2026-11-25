# SWYRA Sortlist v2 — Trust, Safety & Privacy Policy

This is the binding trust and safety document.

## Core Commitments
1. Every recommendation is evidence-linked and reversible by a human
2. No score is presented as a hiring decision
3. Protected attributes are never used as ranking factors
4. Candidate data has defined retention and deletion policies
5. All system actions are auditable

## Authentication & Authorization (P0)
- Session-based auth with secure httpOnly cookies
- Organization/tenant model: every resource belongs to an organization
- Role-based access: Admin, Recruiter, Viewer
- Authorization enforced on every read/write route
- No anonymous access to candidate data

## Data Protection
### What We Store
- Job criteria and configuration (tenant-scoped)
- Uploaded PDF resumes (S3, tenant-scoped keys)
- Extracted structured data (S3 JSON, tenant-scoped)
- Scoring results (S3 JSON, tenant-scoped)
- Audit log events

### Retention Policy
- Job data: Retained until explicitly deleted by tenant admin
- ATS Health Check uploads: Deleted within 1 hour after processing
- All data: Subject to tenant-initiated deletion
- Deletion is cascading: deleting a job removes all associated documents, extractions, and scores

### PII Handling
- Candidate PII (name, email, phone, address) is extracted for display purposes only
- PII is never used as a ranking factor
- PII is stored in tenant-scoped S3 objects, not in DynamoDB item bodies
- Export includes only data the requesting user is authorized to see

## Fairness Policy
### Prohibited Factors
The system MUST NEVER use, infer, rank, filter, or expose as a recommendation factor:
- Age, date of birth
- Gender
- Race, ethnicity
- Caste
- Religion
- Nationality
- Disability
- Marital status
- Photo
- Address (beyond city-level, and only if job specifies location requirement)
- Name-based proxies
- Location-based proxies
- University prestige
- Employer prestige / FAANG bonus
- Career gaps
- Inferred "culture fit"

### Implementation
- Prestige company bonus: DELETED from scorer
- Prestigious cert issuer bonus: DELETED from scorer
- Career gap anomaly detection: DISABLED
- Contact parser: Does not extract or store photo, date of birth, gender, or religion
- Domain classifier: Uses professional domain (engineering, healthcare, etc.) based on job skills, not personal attributes

## Audit Logging
All state-changing operations are logged:
- Job created/updated/deleted
- Documents uploaded/deleted
- Extraction completed/failed
- Scoring completed
- Human decision made (with reason)
- Score override applied (with reason)
- Data exported
- Data deleted

Audit log fields: timestamp, actor_id, org_id, action, resource_type, resource_id, details

## Upload Safety
- PDF type validation (extension + MIME + magic bytes)
- File size limit: 10MB per file
- Page count limit: 50 pages per document
- Rate limiting: configurable per endpoint
- No executable content processing from PDFs

## Security Headers & CORS
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Content-Security-Policy: configured per environment
- CORS: Explicit allow-list of frontend origins (no wildcards in production)
- Strict-Transport-Security: max-age=31536000; includeSubDomains

## ATS Health Check Privacy
- Uploaded PDFs are processed and results returned
- PDF data is deleted within 1 hour (configurable)
- No candidate data is stored persistently from ATS checks
- Rate limited to prevent abuse
- Clear disclaimer: results are informational, not guarantees
