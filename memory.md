# memory.md — Resume Ranker V2
> Context window and state tracking.

## 1. Project State
- **Architecture:** Rev 3 (2-Lambda Split, Tiered Extraction, SSE only).
- **Active Phase:** Phase 1 (Restore V1 flow on `/api/v2/`).

## 2. Key Architectural Truths (DO NOT VIOLATE)
1. **No WebSockets:** SSE is the only real-time mechanism.
2. **2 Lambdas:** Lambda A (Docker, JVM/PyMuPDF, ODL) -> SQS -> Lambda B (ZIP, Python, FastAPI).
3. **Tiered Extraction:** PyMuPDF first. If quality < 90%, use ODL. 
4. **State:** DynamoDB holds Job state. S3 holds raw JSON. SSE reads DynamoDB.
5. **LLM Config:** Amazon Nova Micro via Bedrock. `temperature=0`. Used ONLY for extraction gaps.
6. **Frontend:** Zustand is the source of truth for candidate lists. Weight changes compute locally.

## 3. E2E Test Mandate
The `e2e-api-test.ts` script is the source of truth for business logic. It tests 6 JD roles across 25 PDFs. The application is NOT considered working until this script runs green in the browser console without 404s or missing data.