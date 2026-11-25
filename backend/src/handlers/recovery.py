"""
recovery.py — AWS Lambda periodic handler for autonomous outbox & stranded recovery
===================================================================================
Invoked periodically (EventBridge / Scheduler or unified dispatcher) to recover
pending outbox events from both outbox schemas and stranded jobs.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def handler(event: Dict[str, Any] = None, context: Any = None) -> Dict[str, Any]:
    """Reconcile pending outbox events and stranded jobs autonomously."""
    from src.infrastructure.queue.outbox import relay_pending_outbox
    from src.infrastructure.repositories.files_repository import FilesRepository

    repo = FilesRepository()
    relayed_events, recovered_jobs = repo.reconcile_all_pending_outboxes()
    relayed_upload_outbox = relay_pending_outbox()
    total_relayed = relayed_events + relayed_upload_outbox
    logger.info(
        "Independent outbox recovery complete: %d outbox events (%d upload relay), %d stranded jobs recovered",
        total_relayed,
        relayed_upload_outbox,
        recovered_jobs,
    )
    return {
        "statusCode": 200,
        "relayed_events": total_relayed,
        "recovered_jobs": recovered_jobs,
    }
