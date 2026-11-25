"""
dlq.py — AWS Lambda SQS event handler for Dead-Letter Queues (DLQ)
==================================================================
Ensures terminal state accounting for poisoned or exhausted messages.
"""

import logging
from typing import Any, Dict, List

from src.config.aws import get_settings
from src.pipeline.dlq_consumers import (
    process_scoring_dlq_message,
    process_stage1_dlq_message,
    process_stage2_dlq_message,
)

logger = logging.getLogger(__name__)


def _arn_matches_urls(arn: str, urls: List[str]) -> bool:
    arn_name = (arn or "").rsplit(":", 1)[-1]
    if not arn_name:
        return False
    for u in urls:
        u_clean = (u or "").strip()
        if u_clean and u_clean.rstrip("/").rsplit("/", 1)[-1] == arn_name:
            return True
    return False


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Lambda handler invoked by SQS DLQs to ensure terminal state accounting."""
    records: List[Dict[str, Any]] = event.get("Records", [])
    logger.info("DLQ Consumer Lambda received %d poisoned messages", len(records))
    batch_item_failures: List[Dict[str, str]] = []
    settings = get_settings()

    s1_dlqs = [settings.SQS_STAGE1_DLQ_URL, settings.SQS_FAST_PARSE_DLQ_URL]
    s2_dlqs = [settings.SQS_STAGE2_DLQ_URL, settings.SQS_ODL_BATCH_DLQ_URL, settings.SQS_NOVA_DLQ_URL]
    sc_dlqs = [settings.SQS_SCORING_DLQ_URL, settings.SQS_FINAL_RANK_DLQ_URL]

    for record in records:
        msg_id = record.get("messageId", "")
        try:
            event_source_arn = record.get("eventSourceARN", "")
            arn_lower = event_source_arn.lower()
            if _arn_matches_urls(event_source_arn, s1_dlqs) or "stage1" in arn_lower or "fast-parse" in arn_lower:
                process_stage1_dlq_message(record)
            elif _arn_matches_urls(event_source_arn, s2_dlqs) or "stage2" in arn_lower or "odl" in arn_lower or "nova" in arn_lower:
                process_stage2_dlq_message(record)
            elif _arn_matches_urls(event_source_arn, sc_dlqs) or "scoring" in arn_lower or "final-rank" in arn_lower:
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
