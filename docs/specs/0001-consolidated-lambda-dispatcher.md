# 0001 · Consolidated Lambda Dispatcher and Preprod Deployment

**Status**: In Progress
**Date**: 2026-11-25
**Branch**: `v2.1`
**Constraints**: `HC-01`, `ADR-07`, `HC-03`, `HC-04`, `ADR-08`

## Summary

This specification defines the architecture for consolidating Resume Ranker's five per environment Python Lambda functions into one unified Python Lambda function per environment (`resume-ranking-api` for production, `resume-ranker-preprod` for pre-production), while keeping `odl-parser-lambda-prod` unchanged as the shared Java container dependency.

## Architecture Decisions

### 1. Minimum Two Python Function Topology

1. **`resume-ranker-preprod`** (`infra/template.preprod.yaml`): One unified Python 3.13 Lambda function handling HTTP API Gateway v2 requests (via Mangum), Stage 1 SQS batches, Stage 2 SQS batches, Scoring SQS batches, Dead Letter Queue recovery batches, and scheduled outbox reconciliation.
2. **`resume-ranking-api`**: Existing production Python Lambda function, kept untouched until production cutover is authorized.
3. **`odl-parser-lambda-prod`**: Existing shared 3008 MB Java 21 OCI container image (`HC-04`), kept unchanged.

### 2. Trusted Event Routing (`src.lambda_handler.handler`)

All events enter `src.lambda_handler.handler(event, context)`:

1. **HTTP API Gateway v2 / REST v1**: Events containing `requestContext.http`, `rawPath`, or `httpMethod` lazy import and invoke `src.handlers.api.handler`.
2. **Scheduled Events**: Events with `source` equal to `aws.events` or `aws.scheduler` (and `detail-type` matching `Scheduled Event` or explicit scheduler trigger) lazy import and invoke `src.handlers.recovery.handler`.
3. **Amazon SQS**: Events with `Records` where `eventSource == "aws:sqs"` resolve the target handler strictly by comparing each record's `eventSourceARN` against the configured SQS queue URLs and ARNs in `AWSSettings`:
   * `SQS_STAGE1_QUEUE_URL` / `SQS_FAST_PARSE_QUEUE_URL` -> `src.handlers.stage1.handler`
   * `SQS_STAGE2_QUEUE_URL` / `SQS_ODL_BATCH_QUEUE_URL` / `SQS_NOVA_QUEUE_URL` -> `src.handlers.stage2.handler`
   * `SQS_SCORING_QUEUE_URL` / `SQS_FINAL_RANK_QUEUE_URL` -> `src.handlers.scoring.handler`
   * Configured DLQ URLs (`SQS_STAGE1_DLQ_URL`, `SQS_STAGE2_DLQ_URL`, `SQS_SCORING_DLQ_URL`) -> `src.handlers.dlq.handler`
4. **Fail Closed on Untrusted or Unknown Sources**: Message payload attributes (`body.stage`, embedded ARNs) are never trusted for routing. Unrecognized SQS ARNs return all `messageId` entries in `batchItemFailures` without executing any worker. Non matching non SQS payloads raise `ValueError`.

### 3. Account Concurrency Budget and Tradeoffs

The target AWS account (`445567096027`, region `ap-south-1`) currently enforces `ConcurrentExecutions = 10`. With one unified function per environment:

* **Shared Attributes**: All handlers share one timeout (`180s`), one memory limit (`1024 MB`), one IAM execution role (scoped strictly to preprod bucket, preprod table, preprod queues, Bedrock Nova inference, and ODL Lambda invoke), and the account unreserved concurrency pool.
* **Per Queue Concurrency Caps (`ScalingConfig.MaximumConcurrency`)**:
  * `Stage1Queue`: `BatchSize = 10`, `MaximumConcurrency = 3`
  * `Stage2Queue`: `BatchSize = 5`, `MaximumConcurrency = 2`
  * `ScoringQueue`: `BatchSize = 1`, `MaximumConcurrency = 2` (AWS minimum allowed value)
  * `Stage1DLQ`, `Stage2DLQ`, `ScoringDLQ`: `BatchSize = 10`, `MaximumConcurrency = 2`
* **API Starvation Prevention**: Normal Stage 1 + Stage 2 + ODL execution uses at most 5 to 7 slots, leaving headroom for interactive HTTP API requests and Scoring. Function level reserved concurrency is never set to `0`.
* **Emergency Stage 2 Kill Switch**: Disabling the `Stage2Queue` event source mapping (plus application level `DISABLE_STAGE2_FALLBACK`) halts Bedrock Nova and ODL spend without blocking API requests, Stage 1 ingestion, Scoring, or DLQ recovery.
* **SQS Visibility Timeouts**: Every preprod queue uses `VisibilityTimeout >= 300s` (`Stage1Queue: 360s`, `Stage2Queue: 600s`, `ScoringQueue: 360s`, DLQs: `300s`) so messages never become visible while a `180s` Lambda invocation is still running.

### 4. Preprod Isolation With Shared ODL

`odl-parser-lambda-prod` restricts S3 access via its existing IAM role (`odl-parser-ODLParserFunctionRole-A0r4nrUaiYMg`) to `pdf-test-bucket-09`, `kre-documents-prod`, and `resume-ranker-prod-storage`. To keep `odl-parser-lambda-prod` unmodified while preventing preprod from ever accessing `resume-ranker-prod-storage`, `odl_client.py` supports an `ODL_STAGING_BUCKET` setting (`pdf-test-bucket-09` with prefix `preprod-staging/` in preprod). Preprod copies only the target PDF to `preprod-staging/`, invokes ODL on that bucket, and deletes the temporary copy in a `finally` block.
