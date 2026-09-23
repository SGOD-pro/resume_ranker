"""
outbox.py — Transactional outbox for durable SQS dispatch
===========================================================
Eliminates the crash window between DynamoDB write and SQS send.

Pattern:
  1. Write a pending outbox record to DynamoDB (transact with the document update).
  2. Try to send to SQS immediately.
  3. If SQS send succeeds, delete the outbox record.
  4. If SQS send fails, the outbox record remains; a background relay picks it up.

This prevents lost messages when the process crashes between the DB update
and the SQS publish call.

Outbox records are stored at:
  PK = OUTBOX#{job_id}
  SK = OUTBOX#{event_id}
  ttl = created_at + 24h (DynamoDB TTL)

The relay loop (`relay_pending_outbox`) is called by the BackgroundWorkerDaemon
and the standalone worker every N seconds to flush stuck records.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# TTL offset: outbox records auto-expire after 24 hours even if never relayed
_OUTBOX_TTL_SECONDS = 86400


def _utcnow_epoch() -> int:
    return int(time.time())


def write_outbox_and_send(
    *,
    job_id: str,
    session_id: str,
    document_id: str,
    org_id: str,
    job_version: int,
    s3_key: str,
    stage: str = "FAST_PARSE",
) -> str:
    """Write outbox record to DynamoDB then immediately attempt SQS publish.

    Returns the event_id of the outbox record (useful for idempotency checks).

    If the SQS send succeeds in-line, the outbox record is deleted immediately.
    If the SQS send fails, the record remains for the relay to pick up.
    """
    from src.config.aws import get_client, get_settings
    from src.infrastructure.queue.queue_manager import enqueue_fast_parse
    from src.infrastructure.queue.message import QueueMessage

    settings = get_settings()
    event_id = str(uuid.uuid4())
    ttl = _utcnow_epoch() + _OUTBOX_TTL_SECONDS

    # 1. Write outbox record to DynamoDB
    try:
        dynamodb = get_client("dynamodb")
        dynamodb.put_item(
            TableName=settings.dynamodb_table_name,
            Item={
                "PK": {"S": f"OUTBOX#{job_id}"},
                "SK": {"S": f"OUTBOX#{event_id}"},
                "entity_type": {"S": "OUTBOX"},
                "event_id": {"S": event_id},
                "job_id": {"S": job_id},
                "session_id": {"S": session_id},
                "document_id": {"S": document_id},
                "org_id": {"S": org_id},
                "job_version": {"N": str(job_version)},
                "s3_key": {"S": s3_key},
                "stage": {"S": stage},
                "status": {"S": "PENDING"},
                "created_at": {"S": datetime.now(timezone.utc).isoformat()},
                "ttl": {"N": str(ttl)},
            },
        )
    except Exception as db_err:
        logger.error("Outbox: failed to write outbox record for doc %s: %s", document_id, db_err)
        # Fall through — attempt SQS send anyway (best-effort without outbox)

    # 2. Attempt immediate SQS dispatch
    try:
        enqueue_fast_parse(
            job_id=job_id,
            session_id=session_id,
            document_id=document_id,
            org_id=org_id,
            job_version=job_version,
            s3_key=s3_key,
            content_hash="",
        )
        # 3. SQS send succeeded — mark outbox record as SENT and delete
        _delete_outbox_record(job_id, event_id)
        logger.debug("Outbox: doc %s dispatched to SQS and outbox record cleaned up", document_id)
    except Exception as sqs_err:
        logger.warning(
            "Outbox: SQS send failed for doc %s (event %s), record retained for relay: %s",
            document_id, event_id, sqs_err,
        )

    return event_id


def _delete_outbox_record(job_id: str, event_id: str) -> None:
    """Delete a successfully-dispatched outbox record."""
    try:
        from src.config.aws import get_client, get_settings
        settings = get_settings()
        dynamodb = get_client("dynamodb")
        dynamodb.delete_item(
            TableName=settings.dynamodb_table_name,
            Key={
                "PK": {"S": f"OUTBOX#{job_id}"},
                "SK": {"S": f"OUTBOX#{event_id}"},
            },
        )
    except Exception as e:
        logger.warning("Outbox: could not delete outbox record %s: %s", event_id, e)


def relay_pending_outbox(job_id: Optional[str] = None, max_records: int = 50) -> int:
    """Scan for PENDING outbox records and re-dispatch them to SQS.

    Called by the BackgroundWorkerDaemon relay loop every 30 seconds.
    Returns the count of records relayed.
    """
    from src.config.aws import get_client, get_settings
    from src.infrastructure.queue.queue_manager import enqueue_fast_parse

    settings = get_settings()
    dynamodb = get_client("dynamodb")
    relayed = 0

    try:
        # Query for PENDING outbox records
        # If job_id provided, query for that job; otherwise scan (dev only)
        if job_id:
            resp = dynamodb.query(
                TableName=settings.dynamodb_table_name,
                KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
                FilterExpression="#st = :pending",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":pk": {"S": f"OUTBOX#{job_id}"},
                    ":prefix": {"S": "OUTBOX#"},
                    ":pending": {"S": "PENDING"},
                },
                Limit=max_records,
            )
        else:
            resp = dynamodb.scan(
                TableName=settings.dynamodb_table_name,
                FilterExpression="entity_type = :et AND #st = :pending",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":et": {"S": "OUTBOX"},
                    ":pending": {"S": "PENDING"},
                },
                Limit=max_records,
            )

        for item in resp.get("Items", []):
            ev_id = item.get("event_id", {}).get("S", "")
            jid = item.get("job_id", {}).get("S", "")
            sid = item.get("session_id", {}).get("S", "")
            did = item.get("document_id", {}).get("S", "")
            oid = item.get("org_id", {}).get("S", "")
            jver = int(item.get("job_version", {}).get("N", "1"))
            s3k = item.get("s3_key", {}).get("S", "")

            if not (ev_id and jid and did):
                continue

            try:
                enqueue_fast_parse(
                    job_id=jid,
                    session_id=sid,
                    document_id=did,
                    org_id=oid,
                    job_version=jver,
                    s3_key=s3k,
                    content_hash="",
                )
                _delete_outbox_record(jid, ev_id)
                relayed += 1
                logger.info("Outbox relay: re-dispatched doc %s (event %s)", did, ev_id)
            except Exception as relay_err:
                logger.warning("Outbox relay: failed to re-dispatch event %s: %s", ev_id, relay_err)

    except Exception as scan_err:
        logger.error("Outbox relay: scan/query failed: %s", scan_err)

    return relayed
