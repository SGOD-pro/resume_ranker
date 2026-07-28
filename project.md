# project overview and business value. Rev 4.

## 1. What Is This
Resume Ranker V2 is a candidate screening platform that ranks PDF resumes against a job description. V2 fixes V1's 72/100 extraction ceiling by introducing a smart, tiered extraction routing pipeline. 

Because high-quality PDF parsing (`opendataloader-pdf`) requires a JVM and is heavy, V2 uses a "fast-path" approach: it tries V1's PyMuPDF first. If a pre-extraction structural heuristic detects layout scrambling (e.g., multi-column), it falls back to the JVM. Once clean text is extracted, it runs deterministic regex, only invoking an LLM (Amazon Nova) for the ~10% of fields the regex misses.

## 2. The Big Picture (System Flow)
1. **Receive Resume:** Client uploads to API -> S3 + DynamoDB (Pending) + Background Task (Local) or SQS (Prod).
2. **Read Resume (Worker):** Tries PyMuPDF. Calculates structural quality. If quality < 0.90, uses `opendataloader-pdf` (JVM). Saves Structured JSON.
3. **Understand Resume:** Runs Regex. If fields missing, batches to Nova LLM. 
4. **Score Resume:** Runs JD Match (BM25 fixed IDF) and ATS (Geometry) in parallel. Saves to DB.
5. **Show Result:** SSE pushes completion to frontend. Frontend renders results and computes weight changes instantly.

## 3. Core Value Proposition
1. **Speed & Cost:** PyMuPDF fast-path handles 80% of resumes. LLM handles 10% of fields. No unnecessary compute.
2. **Explainability:** 100% deterministic ATS scoring with bbox overlays. No black-box LLM scoring.
3. **Local-First:** The entire V2 pipeline can be developed and tested locally using FastAPI `BackgroundTasks` without AWS infrastructure.
4. **Scalable Data Access:** DynamoDB GSIs allow efficient score-range and skill-presence filtering without expensive table scans.

## 4. Why V2 Exists (Honest V1 Post-Mortem)
V1's extraction was capped at 72/100 because PyMuPDF scrambled multi-column layouts, feeding garbage text to correct regex parsers. V1 also computed BM25 IDF dynamically per pool, meaning a candidate's score changed depending on who else applied. V2 fixes the root cause via structural fallback routing and fixes scoring determinism via a fixed reference IDF table.
