# project overview and business value. Rev 4.

## 1. What Is This
Resume Ranker V2 is a candidate screening platform that ranks PDF resumes against a job description. V2 fixes V1's 72/100 extraction ceiling by introducing a smart, tiered extraction routing pipeline. 

Because high-quality PDF parsing (`opendataloader-pdf`) requires a JVM and is heavy, V2 uses a "fast-path" approach: it tries V1's PyMuPDF first. If a pre-extraction structural heuristic detects layout scrambling (e.g., multi-column), it falls back to the JVM. Once clean text is extracted, it runs deterministic regex, only invoking an LLM (Amazon Nova) for the ~10% of fields the regex misses.

## 2. The Big Picture (System Flow)
1. **Receive Resume:** Client uploads directly to S3 via presigned URLs or to API, recording file metadata and outbox event in DynamoDB.
2. **Read Resume (Stage 1 Fast Parse):** In memory PyMuPDF extraction. Calculates structural layout quality. If quality is clean, transitions directly to S2_DONE. If layout is scrambled, routes to Stage 2.
3. **Understand Resume (Stage 2 Fallback):** Bounded microbatches call shared external OpenDataLoader parser (`odl-parser-lambda-prod`). Missing critical fields invoke Amazon Bedrock Nova Micro infill with provenance tracking.
4. **Score Resume (Scoring):** Atomic barrier triggers once remaining files reach zero. Runs deterministic JD Match (fixed BM25 reference corpus) and ATS layout geometry. Persists results to S3 and DynamoDB.
5. **Show Result:** Browser polls status or receives SSE progress updates. Results render in Zustand with instant client side weight recalculation.
6. **Self Healing Recovery:** Transactional DynamoDB outbox pattern and EventBridge periodic recovery ensure zero stranded records or dropped files.

## 3. Core Value Proposition
1. **Speed & Cost:** PyMuPDF fast path handles clean resumes in milliseconds. ODL handles layout scrambling. Nova handles field infill. No unnecessary compute.
2. **Measured AWS Performance:** Clean path scales from 2.49s (1 resume) to 52.14s (100 resumes). Mixed fallback path scales from 3.13s (1 resume) to 71.13s (100 resumes). Peak Lambda memory observed at 288 MB of 1024 MB.
3. **Explainability:** 100% deterministic ATS scoring and match math. No black box LLM scoring decisions.
4. **Standalone Engine:** Zero in app authentication or user accounts (ADR-07). External reverse proxy provides edge security in production.
5. **Durable Serverless Architecture:** Consolidated Python Lambda dispatcher routing API Gateway v2, SQS stage queues, DLQs, and recovery events with separate event source mappings.

## 4. Why V2 Exists (Honest V1 Post-Mortem)
V1's extraction was capped at 72/100 because PyMuPDF scrambled multi-column layouts, feeding garbage text to correct regex parsers. V1 also computed BM25 IDF dynamically per pool, meaning a candidate's score changed depending on who else applied. V2 fixes the root cause via structural fallback routing and fixes scoring determinism via a fixed reference IDF table.
