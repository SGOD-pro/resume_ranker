"""
lambda_handler.py — AWS Lambda entry points for API and SQS Workers
===================================================================
Provides entrypoints for:
- handler: API Gateway HTTP API v2 via Mangum
- stage1_handler: SQS event source for Stage 1 (PyMuPDF triggered by S3)
- stage2_handler: SQS event source for Stage 2 (ODL & Nova fallback)
- scoring_handler: SQS event source for Scoring / Final Rank
- dlq_handler: SQS event source for Dead-Letter Queues (DLQ)
"""

import json
import logging
from typing import Any, Dict

from mangum import Mangum

from src.main import app
from src.pipeline.dlq_consumers import (
    process_scoring_dlq_message,
    process_stage1_dlq_message,
    process_stage2_dlq_message,
)
from src.pipeline.scoring_worker import process_scoring_message
from src.pipeline.stage1_worker import process_stage1_message
from src.pipeline.stage2_worker import process_stage2_message

logger = logging.getLogger(__name__)

# Mangum translates API Gateway HTTP API events ↔ ASGI (FastAPI)
handler = Mangum(app, lifespan="off")


def stage1_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler invoked by Stage 1 SQS Queue (s3:ObjectCreated)."""
    records = event.get("Records", [])
    logger.info("Stage 1 Lambda received %d records", len(records))
    for record in records:
        try:
            process_stage1_message(record)
        except Exception as e:
            logger.error("Stage 1 record processing error: %s", e, exc_info=True)
            raise
    return {"statusCode": 200, "processed": len(records)}


def stage2_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler invoked by Stage 2 SQS Queue (Fallback processing)."""
    records = event.get("Records", [])
    logger.info("Stage 2 Lambda received %d records", len(records))
    for record in records:
        try:
            process_stage2_message(record)
        except Exception as e:
            logger.error("Stage 2 record processing error: %s", e, exc_info=True)
            # Re-raise to trigger SQS retry with backoff
            raise
    return {"statusCode": 200, "processed": len(records)}


def scoring_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler invoked by Scoring SQS Queue."""
    records = event.get("Records", [])
    logger.info("Scoring Lambda received %d records", len(records))
    for record in records:
        try:
            process_scoring_message(record)
        except Exception as e:
            logger.error("Scoring record processing error: %s", e, exc_info=True)
            raise
    return {"statusCode": 200, "processed": len(records)}


def dlq_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler invoked by SQS DLQs to ensure terminal state accounting."""
    records = event.get("Records", [])
    logger.info("DLQ Consumer Lambda received %d poisoned messages", len(records))
    for record in records:
        event_source_arn = record.get("eventSourceARN", "")
        if "stage1" in event_source_arn.lower() or "fast-parse" in event_source_arn.lower():
            process_stage1_dlq_message(record)
        elif "stage2" in event_source_arn.lower() or "odl" in event_source_arn.lower() or "nova" in event_source_arn.lower():
            process_stage2_dlq_message(record)
        elif "scoring" in event_source_arn.lower() or "final-rank" in event_source_arn.lower():
            process_scoring_dlq_message(record)
        else:
            # Fallback inspection of body
            body_str = record.get("body", "")
            if "raw/" in body_str:
                process_stage1_dlq_message(record)
            else:
                process_stage2_dlq_message(record)
    return {"statusCode": 200, "processed": len(records)}
