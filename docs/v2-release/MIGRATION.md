# Resume Ranker v2: Migration Guide

This document covers the steps and changes required to migrate from the current state to the v2 release.

## Database Changes
New entities have been introduced to support multi-tenancy and security features:
- **User**: Represents individual accounts with authentication credentials.
- **Org**: Represents organizations/tenants.
- **Decision**: Captures human decisions and evidence-first workflow states.
- **AuditLog**: Records critical system and security events.

## S3 Restructuring
- **Key Prefixing**: All S3 objects must now be prefixed with their respective `org_id` to enforce tenant isolation at the storage level.

## Scorer Changes
- **Removed Factors**: The prestige bonus and gap penalty have been completely removed to ensure fairer, evidence-based scoring.
- **Versioning**: Score versioning is now mandatory. Submissions will track `score_version`, `policy_version`, and `job_version`.

## Frontend Changes
- **Authentication**: All views are now behind an auth gate.
- **Responsive Design**: Mobile fallback layouts have been added.
- **Accessibility**: Significant improvements including contrast adjustments, correct focus states, `aria-live` regions, and proper emoji handling.

## API Changes (Breaking)
- **Auth Requirement**: Authentication tokens are now strictly required on all endpoints. Unauthenticated requests will return a `401 Unauthorized`.
- **Environment Variables**: The `.env` file is no longer tracked in git. Use `.env.example` as a template for your local or production environment.

## Backward Compatibility Notes
- Existing records will need to be associated with an `org_id` through a data backfill script before enabling tenant isolation.
- Unversioned legacy scores will need to be assigned a default legacy version identifier to maintain query compatibility.
