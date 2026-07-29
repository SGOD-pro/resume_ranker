# memory.md — Resume Ranker V2
> Context window and state tracking for future sessions.

## 1. Project State
- **Architecture Version:** Rev 4 (Fresh Build from V1).
- **Active Phase:** Phase 2 (Local Async Decoupling).
- **Completed Phases:** Phase 1 (V2 Route Foundation & V1 Migration) gate was passed successfully via frontend E2E and code verification.
- **Bridge File:** `mamori.md` contains the exact V1 API, Frontend, and Extraction flow. Read it first.

## 2. Key Architectural Truths (DO NOT VIOLATE)
1. **Local-First:** Do not write SQS push logic until Phase 4. Phase 2 uses FastAPI `BackgroundTasks` to simulate async processing locally.
2. **No WebSockets:** SSE is the only real-time mechanism.
3. **Tiered Extraction:** PyMuPDF first. If *pre-extraction structural quality* < 0.90, use ODL. 
4. **Database:** DynamoDB with strict GSIs. No Postgres. No table scans for filtering.
5. **No Auth:** Endpoints are open.
6. **LLM Config:** Amazon Nova Micro via Bedrock. `temperature=0`. Used ONLY for extraction field infill, never for scoring or ATS.
7. **Frontend:** Zustand is the source of truth for candidate lists. Weight changes compute locally.
8. **ODL Standalone & Local-Cloud Split:** ODL is a standalone cloud Lambda (`odl-parser-lambda`). Called via `boto3`. In local dev, S3/DB are LocalStack, but Lambda/Bedrock calls hit real AWS.

## 3. Known V1 Pitfalls (Fixed in V2)
- PyMuPDF scrambling 2-column layouts -> Fixed by pre-extraction structural quality gate routing to ODL.
- Dynamic BM25 IDF -> Fixed by fixed reference IDF table.
- Infinite spinner on local dev -> Fixed by FastAPI `BackgroundTasks` updating DynamoDB, while SSE polls DB.