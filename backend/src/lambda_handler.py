"""
lambda_handler.py — AWS Lambda unified entry points with ReportBatchItemFailures
==============================================================================
Provides backwards-compatible entrypoints for all Lambda functions:
- handler: API Gateway HTTP API v2 via Mangum
- stage1_handler: SQS event source for Stage 1 (PyMuPDF triggered by S3)
- stage2_handler: SQS event source for Stage 2 (ODL & Nova fallback)
- scoring_handler: SQS event source for Scoring / Final Rank
- dlq_handler: SQS event source for Dead-Letter Queues (DLQ)
- recovery_handler: EventBridge scheduled rule for autonomous outbox recovery

Each handler delegates to its isolated module in src.handlers to eliminate
cross-tier cold starts and dependency leakage, and returns batchItemFailures
for resilient SQS partial-batch retries.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any], context: Any) -> Any:
    """Mangum translates API Gateway HTTP API events <-> ASGI (FastAPI)."""
    from src.handlers.api import handler as api_handler
    return api_handler(event, context)


def stage1_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Stage 1 SQS event source handler with ReportBatchItemFailures."""
    from src.handlers.stage1 import handler as s1_handler
    return s1_handler(event, context)


def stage2_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Stage 2 SQS event source handler with ReportBatchItemFailures."""
    from src.handlers.stage2 import handler as s2_handler
    return s2_handler(event, context)


def scoring_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Scoring SQS event source handler with ReportBatchItemFailures."""
    from src.handlers.scoring import handler as score_handler
    return score_handler(event, context)


def dlq_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """DLQ consumer handler with ReportBatchItemFailures."""
    from src.handlers.dlq import handler as d_handler
    return d_handler(event, context)


def recovery_handler(event: Dict[str, Any] = None, context: Any = None) -> Dict[str, Any]:
    """Autonomous outbox recovery handler."""
    from src.handlers.recovery import handler as rec_handler
    return rec_handler(event, context)
