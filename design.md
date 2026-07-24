# design.md — Resume Ranker V2
> Low-level design, design patterns (DDD, SOLID), and API contracts.
> **Rev 2** — hybrid extraction (deterministic-first, Nova fallback), deterministic ATS engine.

---

## 1. Domain Model

### 1.1 Bounded Contexts

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  JOB CONTEXT      │  │ EXTRACTION        │  │  SCORING CONTEXT  │  │  ATS CONTEXT      │
│                   │  │ CONTEXT            │  │                    │  │                    │
│  Job              │  │  Document          │  │  ScoringResult     │  │  AtsResult         │
│  JobConfig        │  │  StructuralParse   │  │  SkillMatch        │  │  AtsSignal         │
│  KnockoutCriteria │  │  (ODL output)      │  │  KnockoutResult    │  │  AtsFlag           │
│  ScoringWeights   │  │  ExtractionResult  │  │  Flag              │  │  FixSuggestion      │
│                   │  │  FallbackRecord    │  │                    │  │  (standalone-       │
│                   │  │  (Nova audit trail)│  │                    │  │   capable, no Job    │
│                   │  │                     │  │                    │  │   dependency)        │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
          │                        │                       │                     │
          └────────────────────────┴───────────────────────┴─────────────────────┘
                                  SHARED KERNEL
                          (SkillGraph, DomainRegistry, SectionRegistry)
```

**Key boundary decision:** ATS Context has **no required dependency** on Job or Scoring contexts. It operates on `StructuralParse` alone. This is what makes the standalone `/ats-check` route possible without creating a Job — the ATS engine was designed context-first to be job-independent, not bolted on afterward.

### 1.2 Aggregates

**Document Aggregate (root: Document)** — extended from Rev 1 with fallback audit trail:

```python
@dataclass
class Document:
    id: DocumentId
    job_id: JobId | None          # None for standalone ATS-checker documents
    s3_key: str
    content_hash: str              # SHA-256, dedup key
    structural_parse: StructuralParse   # raw ODL output, cached, immutable
    extraction: ExtractionResult | None
    fallback_records: list[FallbackRecord]  # audit trail of what Nova filled in
    ats_result: AtsResult | None
    status: DocumentStatus         # UPLOADED | PARSING | EXTRACTING | EXTRACTED | FAILED
    created_at: datetime
```

```python
@dataclass(frozen=True)
class StructuralParse:
    """Direct wrapper around opendataloader-pdf output. This is the ONLY
    place in the codebase allowed to know ODL's raw field names."""
    kids: list[OdlElement]
    markdown: str
    page_count: int
    parser_version: str    # opendataloader-pdf version, for reproducibility

@dataclass(frozen=True)
class OdlElement:
    type: str               # "heading" | "paragraph" | "table" | "list"
    text: str
    bounding_box: tuple[float, float, float, float]  # x0, y0, x1, y1
    hidden: bool
    page: int

@dataclass(frozen=True)
class FallbackRecord:
    """Audit trail: what did the deterministic engine fail to extract,
    and what did Nova return. Required for debugging Nova fallback rate creep."""
    field_name: str
    raw_text_chunk: str
    deterministic_confidence: float  # confidence before fallback (0 = total failure)
    nova_model_used: str             # "nova-micro" | "nova-lite" | "claude-sonnet-4-6"
    nova_response: dict | None
    accepted: bool                   # False if Nova also returned null/low-confidence
```

**AtsResult (entity, standalone — no Job/ScoringResult dependency)**

```python
@dataclass
class AtsResult:
    id: AtsResultId
    document_id: DocumentId | None   # None for /ats-check requests never persisted
    signals: dict[str, AtsSignal]    # keyed by signal name
    ats_score: float                 # 0-100
    flags: list[AtsFlag]
    fix_suggestions: list[FixSuggestion]
    computed_at: datetime

@dataclass(frozen=True)
class AtsSignal:
    name: str            # "two_column_layout" | "hidden_text" | "table_as_layout" |
                          # "parseability" | "contact_presence"
    score: float          # 0.0 or 1.0 for binary signals, continuous for parseability
    weight: float          # contribution to final ats_score
    detail: str | None     # e.g., "3 of 5 pages show multi-column clustering"

@dataclass(frozen=True)
class AtsFlag:
    signal_name: str
    severity: Literal["instant_fail", "severe", "moderate"]
    message: str          # human-readable, shown to recruiter AND job-seeker

@dataclass(frozen=True)
class FixSuggestion:
    signal_name: str
    action: str            # "Convert two-column layout to single-column"
```

### 1.3 ExtractionResult — Now Tracks Provenance Per Field

Rev 1's `ExtractionResult` didn't distinguish where a field came from. Rev 2 requires this — it's how the Nova fallback rate metric gets computed and how a recruiter can trust (or distrust) a low-confidence field.

```python
class FieldProvenance(str, Enum):
    DETERMINISTIC = "deterministic"   # regex/dictionary engine resolved it
    NOVA_FALLBACK = "nova_fallback"    # LLM filled a gap
    UNRESOLVED = "unresolved"          # neither could resolve it — surfaced as null, not guessed

class ExtractedField(BaseModel, Generic[T]):
    value: T | None
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: FieldProvenance

class ExtractionResult(BaseModel):
    name: ExtractedField[str]
    email: ExtractedField[str]
    phone: ExtractedField[str]
    experiences: list[Experience]
    education: list[Education]
    explicit_skills: ExtractedField[list[str]]
    inferred_skills: ExtractedField[list[str]]
    certifications: ExtractedField[list[str]]
    total_experience_months: ExtractedField[int]
    overall_confidence: float
    nova_fields_used: int    # denormalized count, drives the fallback-rate metric
```

---

## 2. Service Layer Design

### 2.1 StructuralParsingService (new — wraps opendataloader-pdf)

```python
class StructuralParsingService:
    """
    Single responsibility: PDF bytes → StructuralParse.
    This is the ONLY class that imports the opendataloader-pdf client.
    Everything downstream consumes StructuralParse, never touches ODL directly.
    This IS the anti-corruption layer — see boundaries.md §2.
    """
    def __init__(self, odl_client: OpenDataLoaderClient, cache: DocumentCache): ...

    async def parse(self, pdf_bytes: bytes, content_hash: str) -> StructuralParse:
        """
        1. Check S3 cache by content_hash — never re-run ODL on identical bytes
        2. Call ODL convert() — this spawns/reuses the warm JVM process
        3. Map raw ODL JSON → our internal StructuralParse dataclass
        4. Cache result, return
        Raises: StructuralParseError (JVM crash, malformed PDF, timeout)
        """
```

### 2.2 DeterministicExtractionService (ported V1 engine)

```python
class DeterministicExtractionService:
    """
    The V1 regex/dictionary engine, UNCHANGED in matching logic, rewired to
    consume StructuralParse.markdown / StructuralParse.kids instead of raw
    PyMuPDF word-geometry. Same section_registry, skill_registry, parsers.
    """
    def __init__(
        self,
        section_router: SectionRouter,          # maps ODL headings → canonical sections
        contact_parser: ContactParser,           # ported from V1
        experience_parser: ExperienceParser,     # ported from V1
        education_parser: EducationParser,       # ported from V1
        skills_parser: SkillsParser,              # ported from V1, uses skill_registry
    ): ...

    def extract(self, parse: StructuralParse) -> tuple[ExtractionResult, list[UnresolvedChunk]]:
        """
        Returns partial ExtractionResult (fields with provenance=DETERMINISTIC)
        PLUS a list of UnresolvedChunk for anything below confidence threshold.
        Never raises on partial failure — partial success is the expected case.
        """

@dataclass(frozen=True)
class UnresolvedChunk:
    field_name: str
    raw_text: str
    section: str | None
    attempted_confidence: float   # best guess the deterministic engine could reach
```

### 2.3 NovaFallbackService (new — the ACL around Bedrock)

```python
class NovaFallbackService:
    """
    Batches UnresolvedChunks across documents, flushes to Bedrock on a
    size/time trigger, applies tool-use constrained decoding, and NEVER
    lets a raw Bedrock response leak past this class.
    """
    def __init__(
        self,
        bedrock_client: BedrockRuntimeClient,
        batch_buffer: RedisBatchBuffer,     # accumulates UnresolvedChunks
        flush_threshold_count: int = 8,     # 5-10 range per the AWS blueprint
        flush_threshold_seconds: int = 300,
    ): ...

    async def enqueue(self, document_id: DocumentId, chunks: list[UnresolvedChunk]) -> None:
        """Adds to Redis buffer. Triggers flush if threshold hit."""

    async def flush(self) -> list[FallbackRecord]:
        """
        1. Pull accumulated chunks from Redis
        2. Build tool_config schema (see §3.2) — NOT a prompt-only JSON instruction
        3. Single batched Converse call, temperature=0
        4. Validate response against Pydantic schema — reject and mark
           accepted=False if the model still returns null or malformed
        5. Return FallbackRecord[] for merge into ExtractionResult
        6. NEVER overwrite a field the deterministic engine already resolved
           above threshold — Nova only fills true gaps
        """
```

**Why this class exists as a hard boundary:** if Bedrock changes its response envelope, or we swap Nova for Claude, or AWS deprecates an API version, exactly one class changes. Nothing in `ScoringService` or the API layer has ever seen a raw Bedrock response shape. This is Dependency Inversion applied to a vendor API, not just an internal interface.

### 2.4 AtsScoringService (new — fully deterministic, zero I/O to LLM)

```python
class AtsScoringService:
    """
    Pure function over StructuralParse. No LLM calls, ever, no exceptions
    to that rule. Runs independently of extraction success/failure —
    a resume that Nova can't parse at all can still get an ATS score,
    because ATS only needs bounding boxes, not understood field values.
    """
    def __init__(self, signal_evaluators: list[AtsSignalEvaluator]): ...

    def score(self, parse: StructuralParse) -> AtsResult:
        """
        Runs each registered AtsSignalEvaluator, aggregates weighted score.
        Each evaluator implements: evaluate(parse) -> AtsSignal
        New signals are added by registering a new evaluator — Open/Closed.
        """
```

**Signal evaluators (each a small, independently testable class):**

```python
class TwoColumnLayoutEvaluator(AtsSignalEvaluator):
    """
    Clusters paragraph-type element bounding_box[0] (x-coordinate) per page.
    If x-coordinates split into >=2 clusters separated by > gap_threshold (100pt)
    on > 30% of pages → severe penalty. Weight: 25%.
    """
    WEIGHT = 0.25
    GAP_THRESHOLD_PT = 100
    PAGE_TRIGGER_RATIO = 0.30

    def evaluate(self, parse: StructuralParse) -> AtsSignal:
        pages = group_by_page(parse.kids)
        multi_col_pages = 0
        for page_num, elements in pages.items():
            x_coords = sorted(
                e.bounding_box[0] for e in elements if e.type == "paragraph"
            )
            if self._has_multiple_clusters(x_coords):
                multi_col_pages += 1
        ratio = multi_col_pages / len(pages) if pages else 0.0
        triggered = ratio > self.PAGE_TRIGGER_RATIO
        return AtsSignal(
            name="two_column_layout",
            score=0.0 if triggered else 1.0,
            weight=self.WEIGHT,
            detail=f"{multi_col_pages}/{len(pages)} pages show multi-column clustering",
        )

    def _has_multiple_clusters(self, sorted_x: list[float]) -> bool:
        if not sorted_x:
            return False
        clusters = 1
        for i in range(1, len(sorted_x)):
            if sorted_x[i] - sorted_x[i - 1] > self.GAP_THRESHOLD_PT:
                clusters += 1
        return clusters >= 2


class HiddenTextEvaluator(AtsSignalEvaluator):
    """Instant-fail signal. Any element with hidden=True → score 0."""
    WEIGHT = 0.20

    def evaluate(self, parse: StructuralParse) -> AtsSignal:
        hidden_found = any(e.hidden for e in parse.kids)
        return AtsSignal(
            name="hidden_text",
            score=0.0 if hidden_found else 1.0,
            weight=self.WEIGHT,
            detail="Hidden text detected — ATS systems flag this as keyword stuffing"
                   if hidden_found else None,
        )


class TableAsLayoutEvaluator(AtsSignalEvaluator):
    """
    table-type elements found OUTSIDE a section canonically expected to
    contain tables (skills matrices are fine; using a table to lay out
    the whole resume is not). Weight: 15%.
    """
    WEIGHT = 0.15
    ALLOWED_SECTIONS = {"skills", "certifications"}

    def evaluate(self, parse: StructuralParse) -> AtsSignal: ...


class ParseabilityEvaluator(AtsSignalEvaluator):
    """
    extracted_chars / expected_chars_per_page. Low ratio = likely
    image-based/scanned PDF with no real text layer. Weight: 20%.
    """
    WEIGHT = 0.20
    MIN_RATIO = 0.60

    def evaluate(self, parse: StructuralParse) -> AtsSignal: ...


class ContactPresenceEvaluator(AtsSignalEvaluator):
    """
    Regex match for email AND phone within first 500 chars of markdown.
    Instant-fail if missing — an ATS that can't find contact info
    discards the resume regardless of content quality. Weight: 20%.
    """
    WEIGHT = 0.20

    def evaluate(self, parse: StructuralParse) -> AtsSignal:
        head = parse.markdown[:500]
        has_email = bool(EMAIL_RE.search(head))
        has_phone = bool(PHONE_RE.search(head))
        present = has_email and has_phone
        return AtsSignal(
            name="contact_presence",
            score=1.0 if present else 0.0,
            weight=self.WEIGHT,
            detail=None if present else "Missing email or phone in document header",
        )
```

**Weights sum to 100%** (25+20+15+20+20 = 100). Composite:
```python
ats_score = sum(signal.score * signal.weight for signal in signals.values()) * 100
```

### 2.5 ScoringService (JD match — corrected from Rev 1)

```python
class ScoringService:
    """
    Deterministic JD scoring: BM25 (fixed-IDF) + skill-graph traversal +
    knockouts as the primary path. Semantic embedding is CONDITIONAL,
    not universal — see EmbeddingTiebreaker below.
    """
    def __init__(
        self,
        skill_scorer: BM25SkillScorer,          # fixed reference-corpus IDF
        experience_scorer: ExperienceScorer,
        education_scorer: EducationScorer,
        knockout_evaluator: KnockoutEvaluator,
        embedding_tiebreaker: EmbeddingTiebreaker,  # invoked conditionally
        flag_detector: FlagDetector,
    ): ...

    def score(self, extraction: ExtractionResult, job: Job) -> ScoringResult:
        knockout = self.knockout_evaluator.evaluate(extraction, job)
        skill = self.skill_scorer.score(extraction, job)

        semantic = None
        if AMBIGUOUS_BAND[0] <= skill <= AMBIGUOUS_BAND[1]:
            semantic = self.embedding_tiebreaker.score(extraction, job)

        experience = self.experience_scorer.score(extraction, job)
        education = self.education_scorer.score(extraction, job)
        flags = self.flag_detector.detect(extraction)

        return ScoringResult(
            knockout_result=knockout,
            skill_score=skill,
            experience_score=experience,
            education_score=education,
            semantic_score=semantic,       # None if not computed — frontend treats as 0-weight
            flags=flags,
        )
```

### 2.6 Composite Score — Still Computed at Read Time (Correct in Rev 1, Unchanged)

```python
def compute_composite(result: ScoringResult, weights: ScoringWeights) -> float:
    parts = [
        (result.skill_score, weights.skills),
        (result.experience_score, weights.experience),
        (result.education_score, weights.education),
    ]
    if result.semantic_score is not None:
        parts.append((result.semantic_score, weights.semantic))
    total_weight = sum(w for _, w in parts) or 1.0
    return sum(s * w for s, w in parts) / total_weight
```

Note the normalization: if semantic wasn't computed (the common case), its weight doesn't silently zero out the composite — remaining weights renormalize. This avoids Rev 1's original scorer bug class (V1's `similarity.py` had a documented latent bug where empty keyword lists returned a phantom 100.0 score — same category of error, fixed here by explicit renormalization instead of implicit defaults).

---

## 3. LLM Fallback Design (Amazon Nova, Tool-Use Constrained Decoding)

### 3.1 Why Tool-Use, Not Prompt-Based JSON

Per AWS's own published guidance: prompting a model to "output valid JSON" degrades in accuracy as schema complexity grows, because it's still free-text generation the model *chooses* to format correctly. Tool-use / constrained decoding makes the schema a hard constraint at the decoding level — >95% reduction in structured-output errors. For a résumé field-extraction task with a fixed, well-known schema, this is not optional — it's the whole reason Nova is viable as an unattended batch fallback with no human review step.

### 3.2 Tool Schema

```python
NOVA_TOOL_CONFIG = {
    "tools": [{
        "toolSpec": {
            "name": "extract_resume_fields",
            "description": "Extract only the requested missing fields from raw resume text chunks",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "field_name": {"type": "string"},
                                "value": {"type": ["string", "null"]},
                                "confidence": {"type": "number"},
                            },
                            "required": ["id", "field_name", "value", "confidence"],
                        },
                    }
                },
                "required": ["results"],
            },
        }
    }]
}

BEDROCK_CALL = {
    "modelId": "amazon.nova-micro-v1:0",
    "toolConfig": NOVA_TOOL_CONFIG,
    "inferenceConfig": {"temperature": 0.0, "maxTokens": 2000},
}
```

### 3.3 Fallback Rules (Hard, Non-Negotiable)

1. **Never guess.** System instruction explicitly forbids inference beyond the text — `null` is a valid, expected, and frequent output.
2. **Never overwrite a resolved field.** `NovaFallbackService` only fills fields the deterministic engine marked `UNRESOLVED`.
3. **Escalate, don't retry blindly.** If Nova Micro returns `confidence < 0.5` on a field, escalate that specific chunk to Nova Lite once. If Lite also fails, the field stays `UNRESOLVED` and is surfaced as such in the UI — never silently dropped.
4. **Batch, never single-call.** `NovaFallbackService.enqueue()` never triggers an immediate Bedrock call. Flush is gated on the size/time threshold. This is enforced in code (no `flush()` call exists on `enqueue()`'s call path).

---

## 4. Skill Graph Design (Unchanged From Rev 1 — This Part Held Up)

### 4.1 DB Schema

```sql
CREATE TABLE skill_nodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    aliases     TEXT[],
    domain      VARCHAR(50),
    level       VARCHAR(20)
);

CREATE TABLE skill_edges (
    from_skill  UUID REFERENCES skill_nodes(id),
    to_skill    UUID REFERENCES skill_nodes(id),
    edge_type   VARCHAR(30),  -- "parent_of" | "synonym" | "related" | "implies"
    weight      FLOAT,
    PRIMARY KEY (from_skill, to_skill, edge_type)
);
```

### 4.2 Matching Algorithm (unchanged from V1's proven approach)

```
exact match          → 1.00
alias match           → 1.00
implies edge          → 0.75
related edge          → 0.50 * edge.weight
no match              → 0.00

skill_score = mean(matched_scores) * coverage_ratio
coverage_ratio = required_skills_matched / required_skills_total
```

This is V1's `skill_inference.py` weighting scheme verbatim — it already benchmarked at 100% F1 on the skill-matching test set. Not touching it.

---

## 5. API Contracts

### 5.1 Jobs (unchanged from Rev 1)

```
POST   /api/v2/jobs
GET    /api/v2/jobs
GET    /api/v2/jobs/{id}
PATCH  /api/v2/jobs/{id}/weights      Body: { skills, experience, education, semantic }
DELETE /api/v2/jobs/{id}
```

### 5.2 Resumes / Candidates (unchanged from Rev 1)

```
POST   /api/v2/jobs/{id}/resumes
GET    /api/v2/jobs/{id}/candidates          ?sort=&status=&min_score=&skills=
GET    /api/v2/jobs/{id}/candidates/{cid}
PATCH  /api/v2/jobs/{id}/candidates/{cid}/status
GET    /api/v2/jobs/{id}/candidates/export
```

### 5.3 ATS — New in Rev 2

```
POST   /api/v2/ats-check
       Body: multipart PDF (+ optional jd_text field, plain text, no job creation)
       Auth: optional — this route is reachable unauthenticated for job-seeker self-check,
             rate-limited by IP (see boundaries.md §4)
       Returns: {
         ats_score: number,
         signals: { [name]: { score, weight, detail } },
         flags: [{ signal_name, severity, message }],
         fix_suggestions: [{ signal_name, action }],
         jd_match_score: number | null   // only if jd_text provided
       }
       Side effects: NONE. No DB row created. No S3 retention beyond request lifecycle.

GET    /api/v2/jobs/{id}/candidates/{cid}/ats
       Returns: full AtsResult for a candidate already in a job pipeline
```

### 5.4 WebSocket (extended)

```
WS  /ws/jobs/{job_id}

Server → Client:
  { type: "candidate_ready", payload: { jd_score: ScoredCandidate, ats_score: AtsResult } }
  { type: "candidate_partial", payload: { jd_score: ScoredCandidate } }   // ATS still computing
  { type: "candidate_failed", payload: { filename, error, field } }
  { type: "processing_complete", payload: { total, succeeded, failed, nova_fallback_rate } }
```

Note `candidate_partial` — because JD scoring and ATS scoring run in parallel and may complete at different times, the frontend must be able to render whichever arrives first rather than waiting for both (this matches the "never gate visibility" design invariant in §architecture.md §3.1 step 7).

### 5.5 ScoredCandidate Response Schema (extended)

```typescript
interface ScoredCandidate {
  id: string;
  name: string | null;
  status: "active" | "shortlisted" | "rejected" | "reviewing" | "disqualified";
  scores: {
    skill: number;
    experience: number;
    education: number;
    semantic: number | null;      // null = not computed (unambiguous match, skipped)
    composite: number;
  };
  knockout: { passed: boolean; failures: Array<{ criterion: string; reason: string }> };
  flags: Array<{ type: string; detail: string; severity: "warning" | "critical" }>;
  extraction_confidence: number;
  nova_fields_used: number;        // 0 = fully deterministic extraction, transparency signal
  ats: {
    score: number;
    flags: Array<{ signal_name: string; severity: string; message: string }>;
  } | null;                        // null if ATS scoring hasn't completed yet
}
```

---

## 6. SOLID Application (Rev 2 additions in bold)

| Principle | Application |
|---|---|
| **SRP** | `StructuralParsingService` only wraps ODL. `DeterministicExtractionService` only runs regex/dict matching. **`NovaFallbackService` only talks to Bedrock.** `AtsScoringService` only does bbox math. Four narrow classes, not one god-pipeline. |
| **OCP** | **New `AtsSignalEvaluator` subclasses can be added (e.g., a 6th ATS signal) without touching `AtsScoringService`** — it iterates a registered list. Same pattern as Rev 1's scorer design, now applied to ATS too. |
| **LSP** | All `AtsSignalEvaluator` implementations return `AtsSignal` from `evaluate()` — interchangeable in the aggregation loop. |
| **ISP** | **`NovaFallbackService` exposes only `enqueue()` and `flush()` — callers never see Bedrock client internals or the batch buffer directly.** |
| **DIP** | **`ScoringService` and `AtsScoringService` have zero imports of `boto3` or Bedrock types. `NovaFallbackService` is the single injection point for the LLM dependency — swapping Nova for Claude touches one class, per HC-01.** |

---

## 7. Database Schema (Core Tables, Rev 2 additions marked)

```sql
CREATE TABLE workspaces ( ... );  -- unchanged from Rev 1
CREATE TABLE jobs ( ... );        -- unchanged from Rev 1
CREATE TABLE users ( ... );       -- unchanged from Rev 1

CREATE TABLE documents (
    id                  UUID PRIMARY KEY,
    job_id              UUID REFERENCES jobs(id) ON DELETE CASCADE,  -- NULL for /ats-check
    s3_key              VARCHAR(500),
    content_hash        CHAR(64) NOT NULL,
    structural_parse_s3_key VARCHAR(500),   -- NEW: cached ODL raw output
    extraction          JSONB,
    nova_fields_used    INT DEFAULT 0,       -- NEW: transparency + fallback-rate metric source
    embedding           vector(384),          -- NULL unless ambiguous-band tiebreak ran
    status              VARCHAR(20) DEFAULT 'uploaded',
    error_detail        TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(job_id, content_hash)
);

-- NEW in Rev 2
CREATE TABLE fallback_records (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id                 UUID REFERENCES documents(id) ON DELETE CASCADE,
    field_name                  VARCHAR(50) NOT NULL,
    raw_text_chunk               TEXT NOT NULL,
    deterministic_confidence     FLOAT NOT NULL,
    nova_model_used               VARCHAR(30) NOT NULL,
    nova_response                 JSONB,
    accepted                      BOOLEAN NOT NULL,
    created_at                    TIMESTAMPTZ DEFAULT NOW()
);

-- NEW in Rev 2
CREATE TABLE ats_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES documents(id) ON DELETE CASCADE,  -- NULL for /ats-check
    signals             JSONB NOT NULL,
    ats_score           FLOAT NOT NULL,
    flags               JSONB NOT NULL,
    fix_suggestions     JSONB NOT NULL,
    computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scorings (
    id                  UUID PRIMARY KEY,
    document_id         UUID REFERENCES documents(id) ON DELETE CASCADE,
    job_id              UUID REFERENCES jobs(id) ON DELETE CASCADE,
    knockout_result     JSONB NOT NULL,
    skill_score         FLOAT NOT NULL,
    experience_score    FLOAT NOT NULL,
    education_score     FLOAT NOT NULL,
    semantic_score       FLOAT,             -- CHANGED: nullable now, was NOT NULL in Rev 1
    skill_matches        JSONB NOT NULL,
    flags                 JSONB NOT NULL,
    candidate_status      VARCHAR(20) DEFAULT 'active',
    computed_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(document_id, job_id)
);

-- Indexes
CREATE INDEX idx_documents_job_id ON documents(job_id);
CREATE INDEX idx_documents_content_hash ON documents(content_hash);  -- NEW: dedup lookup
CREATE INDEX idx_fallback_records_document ON fallback_records(document_id);
CREATE INDEX idx_ats_results_document ON ats_results(document_id);
CREATE INDEX idx_scorings_job_id ON scorings(job_id);
CREATE INDEX idx_documents_embedding ON documents USING hnsw (embedding vector_cosine_ops);
```