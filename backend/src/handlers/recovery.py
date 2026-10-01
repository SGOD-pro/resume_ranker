"""
recovery.py — AWS Lambda periodic handler for autonomous outbox & stranded recovery
===================================================================================
Invoked periodically (e.g. EventBridge scheduled rule) to recover outbox events
and stranded jobs completely independent of browser polling.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any] = None, context: Any = None) -> Dict[str, Any]:
    """Reconcile pending outbox events and stranded jobs autonomously."""
    from src.infrastructure.repositories.files_repository import FilesRepository
    repo = FilesRepository()
    relayed_events, recovered_jobs = repo.reconcile_all_pending_outboxes()
    logger.info(
        "Independent outbox recovery complete: %d outbox events, %d stranded jobs recovered",
        relayed_events, recovered_jobs
    )
    return {"statusCode": 200, "relayed_events": relayed_events, "recovered_jobs": recovered_jobs}
