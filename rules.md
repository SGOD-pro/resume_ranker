# Resume Ranker V2 — Engineering Rules & Standards

> **Coding Standards, Architectural Boundaries, Testing Mandates, and CI/CD Enforcement Rules.** *Rev 2 — Hybrid Architecture.*

---

## 1. Architecture Rules

- **`R-01`**: **No God-Classes.** Maximum 300 lines per file. Maximum 5 public methods per class.
- **`R-02`**: **Anti-Corruption Isolation.** Every external dependency **MUST** be wrapped in exactly one ACL class. No vendor SDK imports outside the ACL layer.
- **`R-03`**: **Dependency Inversion.** Services depend on abstractions (`Protocols` / `ABCs`), never concrete implementations. Dependency injection is wired at application startup.
- **`R-04`**: **Read-Time Composite Scores.** Composite scores are **NEVER** persisted. They are computed on-the-fly at read time from immutable component scores.
- **`R-05`**: **Batched LLM Processing.** LLM calls are **NEVER** single-document in batch mode. Batching is strictly enforced in `NovaFallbackService.enqueue()` (flush calls on enqueue path prohibited).
- **`R-06`**: **ATS Decoupling.** ATS scoring **NEVER** imports from Extraction, Scoring, or Job contexts.
- **`R-07`**: **Fixed BM25 IDF.** BM25 IDF is **NEVER** computed from the active candidate pool. Fixed reference corpus only.

---

## 2. Data Rules

- **`R-08`**: **Strict Pydantic Models.** All persisted data models **MUST** be Pydantic `BaseModel` subclasses. No raw `dict` returns from repository methods.
- **`R-09`**: **Field Provenance & Confidence.** Every extraction field **MUST** carry a confidence score and provenance tag. No bare values allowed.
- **`R-10`**: **Database-Level Deduplication.** Content hash deduplication is enforced at the database level (`UNIQUE(job_id, content_hash)`), not merely in application logic.
- **`R-11`**: **PII Redaction.** Personally Identifiable Information (email, phone) **MUST** be redacted in logs using the `REDACTED` placeholder.
- **`R-12`**: **Explicit Column Selection.** No `SELECT *` in repository queries. Explicit column lists only.

---

## 3. API Rules

- **`R-13`**: **API Versioning.** All REST endpoints must be versioned under `/api/v2/`. No exceptions.
- **`R-14`**: **Strict Signatures.** All request and response bodies must be validated by Pydantic models. No `dict` or `Any` type annotations in controller signatures.
- **`R-15`**: **RFC 7807 Error Formatting.** Error responses follow RFC 7807 (*Problem Details for HTTP APIs*).
- **`R-16`**: **Typed WebSockets.** WebSocket messages are strictly typed: `{ "type": "...", "payload": ... }`. Untyped JSON strings are prohibited.
- **`R-17`**: **Cursor Pagination.** Pagination must be cursor-based for list results exceeding 50 items. Offset pagination is prohibited.

---

## 4. LLM Rules (Non-Negotiable)

- **`R-18`**: **Constrained Decoding.** LLM fallback uses Bedrock tool-use constrained decoding. Prompt-based JSON formatting instructions are prohibited.
- **`R-19`**: **Zero Temperature.** LLM sampling temperature is `0.0`. Always. No exceptions.
- **`R-20`**: **Deterministic Shielding.** The LLM **NEVER** overwrites a field that the deterministic engine resolved above its confidence threshold.
- **`R-21`**: **Strict Schema Validation.** LLM responses are validated against Pydantic schemas. Malformed responses are rejected immediately without infinite retries.
- **`R-22`**: **Fallback Monitoring.** LLM fallback rate is a monitored metric. CloudWatch alarm triggers at `> 20%`.

---

## 5. Testing Rules

- **`R-23`**: **ACL Integration Testing.** Every ACL class has integration tests against real dependencies (`opendataloader-pdf`, Bedrock, `pgvector`).
- **`R-24`**: **Scorer Property Tests.** Every scoring algorithm has unit tests with property-based assertions (monotonicity, determinism).
- **`R-25`**: **Golden-File Snapshots.** Golden-file snapshot tests run against ODL output across 20 benchmark resumes to catch ODL parser version drift.
- **`R-26`**: **Benchmark Regression Testing.** Regression tests run against the V1 benchmark corpus (3,856 resumes). MRR and NDCG metrics must not regress.
- **`R-27`**: **ATS Determinism Assertions.** ATS scoring tests assert strict determinism: identical input $\rightarrow$ identical output across 100 iterations.
- **`R-28`**: **Boundary Mocking.** No test mocks an entire context. Mocks are applied strictly at the ACL boundary, never inside service internals.

---

## 6. CI/CD Rules

- **`R-29`**: PR cannot merge if `ruff check` or `mypy --strict` fails.
- **`R-30`**: PR cannot merge if code test coverage drops below 80% on changed files.
- **`R-31`**: PR cannot merge if the import-restriction verification script fails (vendor SDK detected outside ACL).
- **`R-32`**: PR cannot merge if any test in the `regression/` suite fails.
- **`R-33`**: Production deployment requires manual approval. No automated deployment from `main`.

---

## 7. Linting & Static Analysis Configuration

```toml
# pyproject.toml (excerpt)
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "PL"]
ignore = ["PLR0913"]  # allow many arguments in dataclass constructors

[tool.mypy]
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
markers = [
    "regression: marks tests as regression tests (deselect with '-m \"not regression\"')",
    "golden: marks tests as golden-file snapshot tests",
]
```

---

## 8. Import Restrictions (CI-Enforced)

```python
# scripts/check_imports.py
RESTRICTED_IMPORTS = {
    "opendataloader_pdf": ["src.extraction.structural_parsing_service"],
    "boto3": ["src.extraction.nova_fallback_service", "src.infra.s3_client"],
    "anthropic": ["src.extraction.nova_fallback_service"],  # if swappable
    "sentence_transformers": ["src.ranking.embedding_tiebreaker"],
    "fitz": [],  # PyMuPDF — completely banned in V2
}

def check() -> int:
    """Fail CI if any restricted import appears outside its allowed module."""
    ...
```
