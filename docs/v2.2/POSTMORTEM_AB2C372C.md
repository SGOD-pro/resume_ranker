# Postmortem: Warm Concurrency-4 Run (Job ab2c372c-f7be-42b4-a63e-a123d9b4b804)

**Incident Date:** 2026-09-25  
**Deployment Stack:** `resume-ranker-dev-isolated` (AWS region: `ap-south-1`)  
**Source Baseline SHA:** `95ab909a5998ab7dd0025bc416a3c2fb777e6fc1`  
**Artifact Referenced:** `scripts/real_aws_gate_results.json`  

---

## 1. Executive Summary

During Phase 1.5 Gate 3 verification testing on real AWS infrastructure, the test harness recorded a stall on the warm concurrency-4 run:
- **Job ID:** `ab2c372c-f7be-42b4-a63e-a123d9b4b804`
- **Total Run Duration Recorded in Harness:** 173,360 ms (timed out at poll 120 / ~150 seconds)
- **Status at Timeout:** `PROCESSING`
- **Remaining Counter:** `1`
- **Usable Count:** `19` (expected: 20)

Subsequent CloudWatch and DynamoDB item inspection revealed that the job **did reach terminal `DONE` with `usable_files=20` and `remaining=0`** at `15:50:10Z` (total pipeline duration 158 seconds), but did so approximately 8 seconds after the test harness poll ceiling expired.

The raw failure artifact `scripts/real_aws_gate_results.json` has been preserved without alteration as the historical record.

---

## 2. Timeline and Trace Analysis

| Timestamp (UTC) | Component | Action / Event |
|---|---|---|
| **15:47:32Z** | Client / Presigned POST | Concurrency-4 batch upload begins for 20 golden PDFs. |
| **15:47:48Z** | API Gateway | POST `/api/v2/jobs/{id}/analyze` triggered. Status transitions to `PROCESSING`. |
| **15:48:15Z** | Stage 1 Worker | PyMuPDF fast-path completes 15 clean documents -> transitioned directly to `S2_DONE`. 5 documents tagged `needs_fallback=True` -> transitioned to `S1_DONE` and enqueued to Stage 2. |
| **15:48:30Z - 15:49:10Z** | Stage 2 Worker | 4 fallback documents evaluate Bedrock / heuristic infill. 4 files reach `JOB_LLM_CAP_REACHED` and complete with `low_confidence_extraction=True`. |
| **15:49:25Z** | Stage 2 Worker | Outstanding file `f95a98cd` (`scratch_resumes/sarah_chen.pdf`) attempts ODL extraction. An S3 `HeadObject` call returns 403 Forbidden due to an un-normalized S3 key prefix in the worker environment. |
| **15:49:40Z** | Stage 2 Worker | After S3 retry backoff, the worker catches the error, isolates the failure, and falls back to deterministic heuristic markdown extraction. |
| **15:50:02Z** | Test Harness | Test script poll timeout reached (poll 120, ~150s). Script records `terminalStatus=PROCESSING`, `remaining=1`, `usable=19`. |
| **15:50:10Z** | Stage 2 Worker | File `f95a98cd` finishes extraction, uploads stage2 JSON, and transitions to `S2_DONE`. `job.remaining` decrements from `1` to `0`. |
| **15:50:12Z** | Final Rank Worker | Scoring barrier triggered (`remaining == 0 and analyze_requested == True`). Final results written to `jobs/{id}/results.json`. Job status -> `DONE`. |

---

## 3. Root Cause Analysis

Two independent contributing factors caused the 8-second delay that breached the test harness polling timeout:

1. **Unbatched Single-Document Fallback Contention:**
   - Under Phase 1.5, each fallback document was processed individually rather than in bounded microbatches.
   - When multiple fallback documents arrived concurrently, SQS delivery concurrency created lock-step contention over DynamoDB conditional updates on `job.remaining`.

2. **Un-isolated S3 403 HeadObject Exception:**
   - Document `f95a98cd` encountered an intermittent `HeadObject` permission delay on raw PDF download before falling back to regex infill.
   - Because the worker did not utilize bounded microbatching with immediate tail flush and partial failure isolation, the retry penalty was borne entirely on the critical path of that single file.

---

## 4. Phase 1.6 Permanent Correctness Repairs

The following architectural fixes implemented in Phase 1.6 resolve this latency tail:

1. **Real Bounded ODL Microbatching (`process_stage2_batch`):**
   - Batches up to 20 document descriptors into a single invocation.
   - Implements **partial failure isolation**: if any document encounters an ODL or S3 error, other documents in the microbatch proceed immediately without delay.
   - Reliable tail flush: executes immediately without waiting for a buffer timeout.

2. **Worker Lease Claims (`claim_file`):**
   - Workers acquire a 120-second lease before beginning processing. Duplicate SQS deliveries or retries are rejected immediately, eliminating duplicate compute and DynamoDB contention.

3. **Atomic Per-Job LLM Reservations (`reserve_llm_slot`):**
   - Reservations are tracked atomically in DynamoDB, eliminating racing read-then-write checks.

4. **Durable Outbox Pattern (`record_outbox_event` & `reconcile_outbox`):**
   - Guarantees that any queued dispatch (Stage 2 or Final Scoring) is persisted to DynamoDB first and retried on every status poll, preventing stranded jobs even in the presence of SQS transient failures.
