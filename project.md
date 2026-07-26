# project.md — Resume Ranker V2
> High-level project overview and business value.

## 1. What Is This
Resume Ranker V2 is a candidate screening platform that ranks PDF resumes against a job description. V2 fixes V1's extraction ceiling by introducing a smart, tiered extraction routing pipeline. 

Because high-quality PDF parsing (`opendataloader-pdf`) requires a JVM and is slow, V2 uses a "fast-path" approach: it tries V1's PyMuPDF first. If extraction quality is poor, it falls back to the JVM. Once clean text is extracted, it runs deterministic regex/dictionaries, only invoking an LLM (Amazon Nova) for the ~10% of fields the regex misses.

## 2. The Big Picture (System Flow)
1. **Receive Resume:** Client uploads to API Lambda -> S3 + DynamoDB (Pending) + SQS.
2. **Read Resume (Lambda A):** Worker pulls from SQS. Tries PyMuPDF. If quality < 90%, uses `opendataloader-pdf` (JVM). Saves Structured JSON to S3 -> SQS.
3. **Understand Resume (Lambda B):** Worker pulls JSON. Runs Regex. If fields missing, batches to Nova LLM. 
4. **Score Resume (Lambda B):** Runs JD Match (BM25) and ATS (Geometry) in parallel. Saves to DB.
5. **Show Result:** SSE pushes completion to frontend. Frontend renders results and computes weight changes instantly.

## 3. Core Value Proposition
1. **Speed & Cost:** PyMuPDF fast-path handles 80% of resumes. LLM handles 10% of fields. No unnecessary compute.
2. **Explainability:** 100% deterministic ATS scoring with bbox overlays. No black-box LLM scoring.
3. **Client-Side Recomputation:** Weight adjustments compute locally in Zustand (< 50ms). Zero backend calls.