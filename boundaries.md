# Resume Ranker V2 — System Boundaries & Anti-Corruption Layers

> **Strict System & Service Boundaries, Anti-Corruption Layers (ACL), Rate Limits, Retention Policies, and Failure Blast Radii.** *Rev 2 — Hybrid Architecture.*

---

## 1. Service Boundaries

```text
┌─────────────────────────────────────────────────────────────┐
│                    API BOUNDARY (FastAPI)                     │
│  /api/v2/* — JWT-authenticated, rate-limited                 │
│  /api/v2/ats-check — unauthenticated, IP-rate-limited        │
│  /ws/* — WebSocket, JWT-authenticated                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
│  EXTRACTION     │ │  SCORING    │ │  ATS ENGINE  │
│  CONTEXT        │ │  CONTEXT    │ │  CONTEXT     │
│                 │ │             │ │              │
│  Structural-    │ │  Scoring-   │ │  AtsResult   │
│  ParsingService │ │  Service    │ │  (standalone)│
│                 │ │             │ │              │
│  Deterministic- │ │  Knockout-  │ │  No Job      │
│  ExtractionSvc  │ │  Evaluator  │ │  dependency  │
│                 │ │             │ │              │
│  NovaFallback-  │ │             │ │              │
│  Service        │ │             │ │              │
└────────┬────────┘ └──────┬──────┘ └──────┬───────┘
         │                 │               │
         └─────────────────┼───────────────┘
                           │
              ┌────────────▼────────────┐
              │    SHARED KERNEL        │
              │  SkillGraph (DB)        │
              │  SectionRegistry        │
              │  DomainRegistry         │
              │  IDF Table (file)       │
              └─────────────────────────┘
```

---

## 2. Anti-Corruption Layers (ACL)

Each external dependency is wrapped in exactly one class. Nothing else in the codebase imports the vendor SDK.

| External Dependency | ACL Class | What It Wraps | What Leaks If Broken |
| :--- | :--- | :--- | :--- |
| **`opendataloader-pdf`** | `StructuralParsingService` | JVM process, ODL JSON schema | `OdlElement` dataclass shape |
| **`boto3` (Bedrock)** | `NovaFallbackService` | Bedrock Converse API, tool-use schema | `FallbackRecord` dataclass shape |
| **`sentence-transformers`** | `EmbeddingTiebreaker` | Model loading, inference | `np.ndarray` (normalized vector) |
| **`PostgreSQL`** | `*Repository` classes | SQL queries, `pgvector` ops | Pydantic models only |
| **`Redis`** | `RedisBatchBuffer`, `SkillGraphCache` | Redis connection & serialization | None (cache is transparent) |

> [!IMPORTANT]
> **Enforcement Rule:** If any class outside the designated Anti-Corruption Layer imports a vendor SDK directly, CI build checks will fail immediately. This is strictly enforced via `pyproject.toml` import restrictions.

---

## 3. Context Boundaries

| Context | Knows About | Does NOT Know About |
| :--- | :--- | :--- |
| **Extraction** | ODL output, regex, Nova fallback, skill registry | Job, JD, scoring weights, ATS |
| **Scoring** | `ExtractionResult`, Job, weights, BM25, skill graph | PDF, ODL, Nova, bounding boxes (`bbox`) |
| **ATS** | `StructuralParse` (`bbox`, hidden text flag, markdown) | `ExtractionResult`, Job, Nova, JD scoring |
| **Job** | Job config, weights, knockout criteria | Documents, raw extraction, scoring engines |

> [!WARNING]
> **Critical Boundary Constraint:** ATS Context has **zero dependency** on Job or Scoring contexts. This decoupling makes `/api/v2/ats-check` executable without instantiating or persisting a `Job`. If ATS ever imports from Scoring, the standalone ATS checker will break.

---

## 4. Rate Limits & Quotas

| Resource | Limit | Enforcement Layer |
| :--- | :--- | :--- |
| **Authenticated API** | 100 req/min per user | API Gateway |
| **`/ats-check` (Unauthenticated)** | 5 req/hour per IP | Redis Token Bucket |
| **File Upload Size** | 10 MB per file | FastAPI Middleware |
| **Batch Upload** | 50 files per job | API Validation |
| **Nova Batch Size** | 10 documents per Bedrock call | `NovaFallbackService` Config |
| **WebSocket Connections** | 50 per job | Connection Registry |
| **Active Jobs per Workspace** | 10 (Pro), Unlimited (Team) | Database Constraint |

---

## 5. Data Retention Boundaries

| Data Type | Retention Period | Deletion Trigger |
| :--- | :--- | :--- |
| **Resume PDFs (S3)** | 90 days | Job deletion or S3 TTL policy |
| **ODL Cached JSON (S3)** | 30 days | S3 Lifecycle TTL |
| **Extraction Results (Postgres)** | 90 days | Job deletion cascade |
| **Fallback Records (Postgres)** | 90 days | Document deletion cascade |
| **ATS Results (Postgres)** | 90 days | Document deletion cascade |
| **`/ats-check` Requests** | 0 (Ephemeral) | N/A — response served strictly in-memory |
| **Structured Logs (CloudWatch)** | 30 days | CloudWatch Log Group retention |

---

## 6. Failure Boundaries & Blast Radii

| Failure Mode | Blast Radius | Fallback / Degradation Behavior |
| :--- | :--- | :--- |
| **ODL JVM Crash** | Extraction blocked for target document | Document marked `FAILED`, recruiter notified, no automatic retry |
| **Nova API Timeout** | Unresolved fields stay unpopulated | Document still receives JD score based on partial deterministic extraction |
| **Nova Returns Malformed JSON** | Target field stays unresolved | `FallbackRecord.accepted = False` logged, field marked `unresolved` |
| **Bedrock Service Down** | All LLM fallback paths blocked | Deterministic extraction continues; CloudWatch alarm triggers on Nova fallback rate |
| **Embedding Model Fails** | Semantic similarity score = `null` | Composite score renormalizes dynamically without semantic weight |
| **PostgreSQL Down** | Entire platform unavailable | Health check fails, API Gateway returns `HTTP 503` |
| **Redis Down** | Batching buffer & cache unavailable | Nova fallback degrades to per-document calls (HC-10 alert fires, system continues) |
