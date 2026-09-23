# SWYRA Sortlist v2 — Data Model

> **Status:** Authoritative — supersedes all previous data model documentation
> **Last updated:** 2026-09-20

---

## Storage Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Metadata & State | DynamoDB (single-table, PAY_PER_REQUEST) | Jobs, documents, scoring metadata, audit log |
| Large Objects | S3 | PDFs, extracted JSON, scoring JSON |
| Session/Cache | (Future) Redis or DynamoDB TTL | Auth sessions, rate-limit counters |

---

## DynamoDB Single-Table Design

**Table:** `SwyraResumePlatform`
**Billing:** PAY_PER_REQUEST
**Keys:** PK (String), SK (String)

### Entity Patterns

#### Organization (Future — P0 Auth)
```
PK: ORG#{org_id}
SK: METADATA
Fields: org_id, name, plan, created_at, updated_at, version
```

#### User (Future — P0 Auth)
```
PK: ORG#{org_id}
SK: USER#{user_id}
Fields: user_id, org_id, email, name, role (admin|recruiter|viewer),
        password_hash, created_at, updated_at, version
```

#### Job
```
PK: JOB#{job_id}
SK: METADATA
Fields: job_id, org_id, title, department, description,
        must_have_skills[], nice_to_have_skills[],
        min_years, max_years, education_level, education_field,
        keywords[], weights{}, status (JobStatus enum),
        job_version (incremented on criteria change),
        document_count, version, created_at, updated_at
```

#### Upload Session (v2.2 Durable Pipeline)
```
PK: JOB#{job_id}
SK: SESSION#{session_id}
Fields: session_id, job_id, org_id, entity_type ("UPLOAD_SESSION"),
        job_version (pinned integer),
        expected_document_count, uploaded_document_count,
        status (UploadSessionStatus enum),
        error_message, version, expires_at,
        created_at, updated_at
```

#### Document
```
PK: JOB#{job_id}
SK: DOC#{document_id}
Fields: document_id, job_id, org_id, filename, file_size,
        content_hash (SHA-256), s3_pdf_key, s3_extracted_key,
        extraction_quality, page_count, candidate_name,
        parser_version, pipeline_version,
        status (DocumentStatus enum),
        version, created_at, updated_at
```

#### Scoring Run
```
PK: JOB#{job_id}
SK: SCORING#{scoring_id}
Fields: scoring_id, job_id, org_id, s3_result_key,
        score_version, policy_version, job_version,
        ranking_version, scoring_algorithm_version,
        candidate_count, weights_used{},
        top_candidate_name, top_candidate_score,
        status (ScoringStatus enum),
        version, created_at, completed_at
```

#### Audit Log Event (Future — P0)
```
PK: ORG#{org_id}
SK: AUDIT#{timestamp}#{event_id}
Fields: event_id, org_id, actor_id, action, resource_type,
        resource_id, details{}, timestamp
```

#### Human Decision (Future — P1)
```
PK: JOB#{job_id}
SK: DECISION#{document_id}
Fields: document_id, job_id, org_id, reviewer_id,
        decision (NEW|REVIEWING|SHORTLISTED|REJECTED|INTERVIEW|ARCHIVED),
        reason (mandatory for REJECTED), notes,
        tags[], previous_decision, system_score, system_recommendation,
        version, created_at, updated_at
```

### Status Enums

```python
class UploadSessionStatus(str, Enum):
    UPLOADING = "UPLOADING"
    UPLOAD_FINALIZED = "UPLOAD_FINALIZED"
    FAST_PREPROCESSING = "FAST_PREPROCESSING"
    FAST_PARSING = "FAST_PARSING"
    READY_TO_ANALYZE = "READY_TO_ANALYZE"
    ANALYSIS_REQUESTED = "ANALYSIS_REQUESTED"
    FALLBACK_PROCESSING = "FALLBACK_PROCESSING"
    FINAL_RANKING = "FINAL_RANKING"
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class JobStatus(str, Enum):
    CREATED = "created"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SCORING = "scoring"
    SCORED = "scored"
    ARCHIVED = "archived"

class DocumentStatus(str, Enum):
    # Pipeline lifecycle states (v2.2)
    UPLOAD_INITIALIZED = "UPLOAD_INITIALIZED"
    UPLOADED = "UPLOADED"
    FAST_PARSE_QUEUED = "FAST_PARSE_QUEUED"
    FAST_PARSING = "FAST_PARSING"
    NEEDS_ODL = "NEEDS_ODL"
    ODL_QUEUED = "ODL_QUEUED"
    ODL_PARSING = "ODL_PARSING"
    NEEDS_NOVA = "NEEDS_NOVA"
    NOVA_QUEUED = "NOVA_QUEUED"
    NOVA_PARSING = "NOVA_PARSING"
    STRUCTURED_PARSED = "STRUCTURED_PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    NOVA_QUEUED = "NOVA_QUEUED"
    NOVA_PARSING = "NOVA_PARSING"
    STRUCTURED_PARSED = "STRUCTURED_PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"

    # Legacy compatibility aliases
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    SCORED = "scored"
    PARSE_FAILED = "parse_failed"

class ScoringStatus(str, Enum):
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"

class HumanDecision(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    ARCHIVED = "archived"

class SystemRecommendation(str, Enum):
    UNSCORED = "unscored"
    SCORED = "scored"
    REVIEW_REQUIRED = "review_required"
    ABSTAIN = "abstain"
```

---

## S3 Object Structure

```
{org_id}/
├── jobs/
│   └── {job_id}/
│       ├── resumes/
│       │   └── {document_id}.pdf
│       ├── extracted/
│       │   └── {document_id}.json
│       └── scoring/
│           └── {scoring_id}.json
└── ats-checks/
    └── {check_id}.pdf (TTL: 1 hour)
```

All S3 keys are prefixed with `org_id` for tenant isolation.

---

## Extraction Output Schema

```typescript
interface ExtractionResult {
  document_id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  github: string | null;
  location: string | null;
  skills: string[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  projects: ProjectEntry[];
  certifications: string[];
  languages: string[];
  raw_text: string;
  extraction_quality: number;  // 0.0-1.0
  extraction_strategy: string;
  pipeline_version: string;
  page_count: number;
  warnings: string[];
  stage_timings: StageTiming[];
}

interface ExperienceEntry {
  role: string | null;
  company: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string;
  source_page: number | null;  // For evidence provenance
}

interface EducationEntry {
  degree: string | null;
  field: string | null;
  institution: string | null;
  start_date: string | null;
  end_date: string | null;
  grade: string | null;
}

interface ProjectEntry {
  name: string | null;
  description: string;
  technologies: string[];
  url: string | null;
}

interface StageTiming {
  stage: string;
  duration_ms: number;
  status: "success" | "fallback" | "error";
  details: string | null;
}
```

---

## Scored Candidate Schema

```typescript
interface ScoredCandidate {
  // Identity
  document_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  pdf_url: string;

  // Scores (0-100)
  final_score: number;
  skill_score: number;
  experience_score: number;
  keyword_score: number;
  education_score: number;

  // Bonuses
  project_bonus: number;
  cert_bonus: number;

  // Metadata
  rank: number;
  percentile: number;
  knocked_out: boolean;
  knockout_reasons: string[];

  // Skill provenance
  matched_must_have: string[];
  missing_must_have: string[];
  matched_inferred: SkillMatchResult[];
  matched_related: SkillMatchResult[];
  extra_skills: string[];

  // Domain
  candidate_domain: string;
  candidate_subdomain: string | null;
  domain_penalty: number;

  // ATS
  ats_score: number;
  ats_warnings: string[];

  // Factor ledger
  score_factors: ScoreFactor[];

  // Versioning
  score_version: string;
  policy_version: string;
  job_version: number;

  // System recommendation (separate from human decision)
  system_recommendation: SystemRecommendation;
  extraction_confidence: number;
}

interface ScoreFactor {
  factor: string;
  contribution: number;
  source: string;
  confidence: number;
  rule_version: string;
}

interface SkillMatchResult {
  jd_skill: string;
  candidate_skill: string;
  match_type: "explicit" | "alias" | "inferred" | "related";
  weight: number;
  explanation: string;
}
```

---

## Data Integrity Rules

1. **Optimistic concurrency**: All DynamoDB writes use condition expressions on `version` field
2. **SHA-256 deduplication**: Duplicate PDFs within a job are rejected at upload time
3. **Tenant isolation**: All queries include `org_id` in key conditions (not filter expressions)
4. **Cascade deletion**: Deleting a job removes all DOC, SCORING, and DECISION items
5. **Score immutability**: Once a scoring run completes, its S3 JSON is never modified. New runs create new scoring items.
