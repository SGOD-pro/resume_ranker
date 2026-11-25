"""
stage1.py — AWS Lambda SQS event handler for Stage 1 extraction
==============================================================
Imports only extraction dependencies (PyMuPDF, extraction pipeline).
Avoids importing FastAPI, Mangum, Nova, BM25, and scoring stacks during cold start.
Implements ReportBatchItemFailures to reprocess only failed messageIds.
"""

import logging
from typing import Any, Dict, List

from src.pipeline.stage1_worker import process_stage1_message

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Lambda handler invoked by Stage 1 SQS Queue.
    
    Returns batchItemFailures with originating SQS messageId values.
    """
    records: List[Dict[str, Any]] = event.get("Records", [])
    logger.info("Stage 1 Lambda received %d records", len(records))
    batch_item_failures: List[Dict[str, str]] = []

    for record in records:
        msg_id = record.get("messageId", "")
        try:
            ok = process_stage1_message(record)
            if ok is False:
                logger.warning("Stage 1 record processing unsuccessful for message %s", msg_id)
                if msg_id:
                    batch_item_failures.append({"itemIdentifier": msg_id})
        except Exception as e:
            logger.error("Stage 1 record processing error for message %s: %s", msg_id, e, exc_info=True)
            if msg_id:
                batch_item_failures.append({"itemIdentifier": msg_id})
            else:
                raise

    return {
        "statusCode": 200,
        "processed": len(records) - len(batch_item_failures),
        "batchItemFailures": batch_item_failures,
    }
