# architecture.md — Resume Ranker V2
> System architecture, tech stack, and data flow.

## 1. Architecture Overview
The system decouples heavy JVM-based PDF parsing from fast Python-based evaluation to optimize AWS Lambda performance and cost.

```text
Client (React)
   │
   ├─ POST /api/v2/jobs/{id}/resumes ──> API Gateway ──> Lambda B (FastAPI)
   │                                                    │─ Checks SHA256 Cache in DynamoDB
   │                                                    │─ Saves PDF to S3
   │                                                    │─ Pushes to SQS (DocumentQueue)
   │                                                    └─ Returns 202 Accepted
   │
   ├─ GET /api/v2/jobs/{id}/extract (SSE) <───────────── Lambda B (Reads DynamoDB Job State)
   │
SQS (DocumentQueue)
   │
   ▼
Lambda A (Docker Image: Python 3.12 + JRE 17 + opendataloader-pdf + PyMuPDF)
   │─ Downloads PDF from S3
   │─ Step 1: Try PyMuPDF. Calculate Quality Score.
   │─ Step 2: If Quality < 90%, run opendataloader-pdf (JVM).
   │─ Saves StructuralParse JSON to S3
   │─ Pushes to SQS (ExtractQueue)
   │
SQS (ExtractQueue) ──> [DLQ if fails 3x]
   │
   ▼
Lambda B (ZIP: FastAPI / SQS Consumer)
   │─ Reads StructuralParse from S3
   │─ Runs Deterministic Regex -> UnresolvedChunks
   │─ Batches Chunks -> Amazon Nova LLM (Bedrock)
   │─ Runs JD Scoring (BM25, Fixed IDF) & ATS Scoring (Bbox math) in parallel
   │─ Saves Results to S3/DynamoDB
   └─ Updates Job State in DynamoDB (SSE reads this)
```

## 2. Why No Step Functions?
The workflow is linear: Upload -> Parse -> Extract -> Done. SQS queues with DLQs are simpler, cheaper, and require less orchestration overhead than AWS Step Functions. Keep it simple.