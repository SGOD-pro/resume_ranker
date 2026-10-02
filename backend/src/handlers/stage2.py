"""
stage2.py — AWS Lambda SQS event handler for Stage 2 fallback (ODL & Nova)
========================================================================
Imports only fallback dependencies.
Implements ReportBatchItemFailures.
"""

import logging
from typing import Any, Dict, List

from src.pipeline.stage2_worker import process_stage2_batch

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Lambda handler invoked by Stage 2 SQS Queue."""
    records: List[Dict[str, Any]] = event.get("Records", [])
    logger.info("Stage 2 Lambda received %d records", len(records))
    if not records:
        return {"statusCode": 200, "processed": 0, "batchItemFailures": []}

    try:
        res = process_stage2_batch(records)
        failed_items = res.get("failed_items", [])
        batch_item_failures = [{"itemIdentifier": it} for it in failed_items if it]
        return {
            "statusCode": 200,
            "processed": res.get("processed", len(records)),
            "batchItemFailures": batch_item_failures,
        }
    except Exception as e:
        logger.error("Stage 2 batch processing error: %s", e, exc_info=True)
        batch_item_failures = [
            {"itemIdentifier": r.get("messageId", "")}
            for r in records
            if r.get("messageId")
        ]
        if not batch_item_failures:
            raise
        return {
            "statusCode": 200,
            "processed": 0,
            "batchItemFailures": batch_item_failures,
        }

