"""
queue_manager.py — Centralized Queue Manager and Factory
=========================================================
Provides singleton queue adapter instance, named queue constants, and high-level enqueue helpers.
"""

import logging
from typing import List, Optional

from src.config.aws import get_settings
from src.infrastructure.queue.base import QueueAdapter
from src.infrastructure.queue.local_adapter import LocalQueueAdapter
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.sqs_adapter import SqsQueueAdapter

logger = logging.getLogger(__name__)

# Logical Queue Names
FAST_PARSE_QUEUE = "fast_parse_queue"
ODL_BATCH_QUEUE = "odl_batch_queue"
NOVA_QUEUE = "nova_queue"
FINAL_RANK_QUEUE = "final_rank_queue"

# Global adapter instance
_adapter_instance: Optional[QueueAdapter] = None


def get_queue_adapter() -> QueueAdapter:
    """Return the configured QueueAdapter (SQS in production, Local in dev/test)."""
    global _adapter_instance
    if _adapter_instance is None:
        settings = get_settings()
        from src.config.aws import is_running_in_lambda
        if is_running_in_lambda() or settings.USE_REAL_SQS:
            logger.info("Initializing SqsQueueAdapter (USE_REAL_SQS=True or running in Lambda)")
            _adapter_instance = SqsQueueAdapter()
        else:
            logger.info("Initializing LocalQueueAdapter (in-memory)")
            _adapter_instance = LocalQueueAdapter()
    return _adapter_instance


def set_queue_adapter(adapter: Optional[QueueAdapter]) -> None:
    """Override the active queue adapter (primarily for test fixtures)."""
    global _adapter_instance
    _adapter_instance = adapter


def enqueue_fast_parse(
    job_id: str,
    session_id: str,
    document_id: str,
    org_id: str,
    job_version: int,
    s3_key: str,
    content_hash: str,
    attempt_number: int = 1,
) -> str:
    """Enqueue a single document for fast parsing (via SNS Topic pub/sub if configured, or direct SQS)."""
    settings = get_settings()
    msg = QueueMessage(
        job_id=job_id,
        session_id=session_id,
        document_id=document_id,
        org_id=org_id,
        job_version=job_version,
        s3_key=s3_key,
        content_hash=content_hash,
        stage="FAST_PARSE",
        attempt_number=attempt_number,
    )
    adapter = get_queue_adapter()
    if settings.USE_REAL_SQS and settings.SNS_EVENTS_TOPIC_ARN and not isinstance(adapter, LocalQueueAdapter):
        try:
            from src.config.aws import get_client
            sns_client = get_client("sns")
            resp = sns_client.publish(
                TopicArn=settings.SNS_EVENTS_TOPIC_ARN,
                Message=msg.to_json(),
                MessageAttributes={
                    "stage": {"DataType": "String", "StringValue": "FAST_PARSE"},
                    "job_id": {"DataType": "String", "StringValue": job_id},
                },
            )
            msg_id = resp.get("MessageId", msg.event_id)
            logger.info("Published FAST_PARSE event to SNS topic %s (id: %s)", settings.SNS_EVENTS_TOPIC_ARN, msg_id)
            return msg_id
        except Exception as e:
            logger.warning("SNS publish failed, falling back to direct SQS send: %s", e)

    return adapter.send_message(FAST_PARSE_QUEUE, msg)


def enqueue_odl_batch(
    job_id: str,
    session_id: str,
    document_ids: List[str],
    org_id: str,
    job_version: int,
    attempt_number: int = 1,
) -> str:
    """Enqueue a bounded batch of documents for ODL fallback parsing."""
    adapter = get_queue_adapter()
    msg = QueueMessage(
        job_id=job_id,
        session_id=session_id,
        document_ids=document_ids,
        org_id=org_id,
        job_version=job_version,
        stage="ODL_BATCH",
        attempt_number=attempt_number,
    )
    return adapter.send_message(ODL_BATCH_QUEUE, msg)


def enqueue_nova(
    job_id: str,
    session_id: str,
    document_id: str,
    org_id: str,
    job_version: int,
    s3_key: Optional[str] = None,
    attempt_number: int = 1,
) -> str:
    """Enqueue a document with unresolved critical fields for Nova Lite fallback."""
    adapter = get_queue_adapter()
    msg = QueueMessage(
        job_id=job_id,
        session_id=session_id,
        document_id=document_id,
        org_id=org_id,
        job_version=job_version,
        s3_key=s3_key,
        stage="NOVA",
        attempt_number=attempt_number,
    )
    return adapter.send_message(NOVA_QUEUE, msg)


def enqueue_final_rank(
    job_id: str,
    session_id: str,
    org_id: str,
    job_version: int,
    attempt_number: int = 1,
) -> str:
    """Enqueue final ranking run for the pinned job_version."""
    adapter = get_queue_adapter()
    msg = QueueMessage(
        job_id=job_id,
        session_id=session_id,
        org_id=org_id,
        job_version=job_version,
        stage="FINAL_RANK",
        attempt_number=attempt_number,
    )
    return adapter.send_message(FINAL_RANK_QUEUE, msg)
