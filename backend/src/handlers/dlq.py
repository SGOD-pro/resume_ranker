"""
dlq.py — AWS Lambda SQS event handler for Dead-Letter Queues (DLQ)
==================================================================
Ensures terminal state accounting for poisoned or exhausted messages.
"""

import logging
from typing import Any, Dict, List

from src.pipeline.dlq_consumers import (
    process_scoring_dlq_message,
    process_stage1_dlq_message,
    process_stage2_dlq_message,
)

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Lambda handler invoked by SQS DLQs to ensure terminal state accounting."""
    records: List[Dict[str, Any]] = event.get("Records", [])
    logger.info("DLQ Consumer Lambda received %d poisoned messages", len(records))
    batch_item_failures: List[Dict[str, str]] = []

    for record in records:
        msg_id = record.get("messageId", "")
        try:
            event_source_arn = record.get("eventSourceARN", "")
            if "stage1" in event_source_arn.lower() or "fast-parse" in event_source_arn.lower():
                process_stage1_dlq_message(record)
            elif "stage2" in event_source_arn.lower() or "odl" in event_source_arn.lower() or "nova" in event_source_arn.lower():
                process_stage2_dlq_message(record)
            elif "scoring" in event_source_arn.lower() or "final-rank" in event_source_arn.lower():
                process_scoring_dlq_message(record)
            else:
                body_str = record.get("body", "")
                if "raw/" in body_str:
                    process_stage1_dlq_message(record)
        except Exception as e:
            logger.error("DLQ message processing failed for %s: %s", msg_id, e, exc_info=True)
            if msg_id:
                batch_item_failures.append({"itemIdentifier": msg_id})

    return {
        "statusCode": 200,
        "processed": len(records) - len(batch_item_failures),
        "batchItemFailures": batch_item_failures,
    }
