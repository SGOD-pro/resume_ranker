# boundaries.md — Resume Ranker V2
> Strict system boundaries, service limits, and anti-corruption layers.

## 1. Lambda Boundaries
- **Lambda A** MUST NOT import `src.scoring` or `src.ats`. It only parses PDFs and pushes SQS.
- **Lambda B** MUST NOT import `opendataloader_pdf`. It only reads JSON from S3. (PyMuPDF is also banned in Lambda B).

## 2. Anti-Corruption Layers (ACLs)
| Dependency | Allowed In | Purpose |
|---|---|---|
| `fitz` (PyMuPDF) | `src/extraction/structural_parsing_service.py` | Fast-path text extraction in Lambda A. |
| `opendataloader_pdf` | `src/extraction/structural_parsing_service.py` | Slow-path layout parsing in Lambda A. |
| `boto3` (Bedrock) | `src/extraction/fallback/nova_service.py` | Isolates LLM API from extraction logic. |

## 3. Queue & DLQ Boundaries
- `DocumentQueue`: Connects API Lambda to Lambda A. Max receive count: 3. DLQ: `DocumentDLQ`.
- `ExtractQueue`: Connects Lambda A to Lambda B. Max receive count: 3. DLQ: `ExtractDLQ`.
- **S3 Payload Pattern:** SQS messages MUST only contain `document_id` and S3 keys. Never pass 50MB JSON through SQS.
