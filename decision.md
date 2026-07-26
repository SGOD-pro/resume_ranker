# decision.md — Resume Ranker V2
> Architecture Decision Records.

## ADR-08: 2-Lambda Split (JVM vs Python)
**Status:** Accepted
**Context:** `opendataloader-pdf` requires a JVM. Lambda deployment limits (250MB unzipped) make bundling JRE + Python deps impossible in a single ZIP.
**Decision:** Split backend into Lambda A (Docker image with JRE + ODL) and Lambda B (Python ZIP with FastAPI + Scoring). SQS connects them.

## ADR-09: SSE over WebSockets
**Status:** Accepted
**Context:** Lambda is stateless. WebSockets require connection mapping, adding massive complexity.
**Decision:** Use FastAPI `StreamingResponse` (SSE). Client opens stream; Lambda B polls DynamoDB for state.

## ADR-10: Tiered Extraction Routing (PyMuPDF -> ODL)
**Status:** Accepted
**Context:** ODL is slow and heavy. Running it on every resume is a waste of compute for simple 1-column PDFs.
**Decision:** Lambda A runs PyMuPDF first. If heuristic quality < 90%, it falls back to ODL.
**Consequences:** Requires a quality-check heuristic. Saves significant compute time on easy resumes.
