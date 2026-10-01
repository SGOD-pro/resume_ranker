"""
scoring.py — AWS Lambda SQS event handler for Scoring / Final Rank
==================================================================
Imports only scoring and ranking dependencies.
Implements ReportBatchItemFailures.
"""

import logging
from typing import Any, Dict, List

from src.pipeline.scoring_worker import process_scoring_message

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Lambda handler invoked by Scoring SQS Queue."""
    records: List[Dict[str, Any]] = event.get("Records", [])
    logger.info("Scoring Lambda received %d records", len(records))
    batch_item_failures: List[Dict[str, str]] = []

    for record in records:
        msg_id = record.get("messageId", "")
        try:
            process_scoring_message(record)
        except Exception as e:
            logger.error("Scoring record processing error for message %s: %s", msg_id, e, exc_info=True)
            if msg_id:
                batch_item_failures.append({"itemIdentifier": msg_id})
            else:
                raise

    return {
        "statusCode": 200,
        "processed": len(records) - len(batch_item_failures),
        "batchItemFailures": batch_item_failures,
    }
