# projectrequirement.md — Resume Ranker V2
> Hard constraints and functional requirements.

## 1. Functional Requirements
- **FR-01** Processing pipeline MUST strictly follow: S3 Upload → SQS → Lambda A → SQS → Lambda B → SSE Push.
- **FR-02 (Extraction Routing):** Lambda A MUST first try PyMuPDF (`fitz`). If text quality < threshold (e.g., missing standard sections, low char count), it MUST fall back to `opendataloader-pdf` (JVM).
- **FR-03** Lambda B MUST run deterministic regex on the extracted text. Unresolved chunks MUST be batched to Amazon Nova (Bedrock) with `temperature=0` and `toolConfig`.
- **FR-04** BM25 IDF MUST come from a fixed reference corpus, not the candidate pool.
- **FR-05** ATS scoring MUST be 100% deterministic bbox math. Zero LLM calls.
- **FR-06** Caching: System MUST deduplicate by SHA256(PDF). If hash exists, return cached result.
- **FR-07** Idempotency: If Lambda retries, it MUST check if processing is already complete and skip.
- **FR-08** Dead Letter Queues (DLQ): All SQS queues MUST have a DLQ for permanently failed messages.

## 2. Hard Constraints (Non-Negotiable)
| # | Constraint |
|---|-----------|
| HC-01 | Lambda A MUST be a Docker container image (to fit JRE + ODL > 250MB). |
| HC-02 | Lambda B MUST be a ZIP package (no JVM, fast cold start). |
| HC-03 | All API contracts MUST be versioned (`/api/v2/`). |
| HC-04 | No WebSockets. SSE is the ONLY real-time mechanism. |
| HC-05 | LLM fallback MUST use tool-use constrained decoding. |
| HC-06 | PyMuPDF is ALLOWED in Lambda A as a fast-path, but NEVER in Lambda B. |
