"""
sqs_adapter.py — AWS SQS QueueAdapter implementation
====================================================
Uses boto3 SQS client to interact with real AWS SQS queues and DLQs.
All messages contain JSON-serialized QueueMessage structures.
"""

import logging
from typing import Dict, List, Optional

from src.config.aws import get_client, get_settings
from src.infrastructure.queue.base import QueueAdapter
from src.infrastructure.queue.message import QueueMessage

logger = logging.getLogger(__name__)


class SqsQueueAdapter(QueueAdapter):
    """Production AWS SQS adapter."""

    def __init__(self) -> None:
        self._client = get_client("sqs")
        self._settings = get_settings()
        self._queue_urls: Dict[str, str] = {
            "fast_parse_queue": self._settings.SQS_FAST_PARSE_QUEUE_URL,
            "fast_parse_dlq": self._settings.SQS_FAST_PARSE_DLQ_URL,
            "odl_batch_queue": self._settings.SQS_ODL_BATCH_QUEUE_URL,
            "odl_batch_dlq": self._settings.SQS_ODL_BATCH_DLQ_URL,
            "nova_queue": self._settings.SQS_NOVA_QUEUE_URL,
            "nova_dlq": self._settings.SQS_NOVA_DLQ_URL,
            "final_rank_queue": self._settings.SQS_FINAL_RANK_QUEUE_URL,
            "final_rank_dlq": self._settings.SQS_FINAL_RANK_DLQ_URL,
        }

    def _get_url(self, queue_name: str) -> str:
        url = self._queue_urls.get(queue_name)
        if not url:
            # Fall back to queue_name directly if it's already a full URL or ARN
            if queue_name.startswith("http://") or queue_name.startswith("https://"):
                return queue_name
            raise ValueError(f"Queue URL not configured for queue: {queue_name}")
        return url

    def send_message(self, queue_name: str, message: QueueMessage, delay_seconds: int = 0) -> str:
        url = self._get_url(queue_name)
        kwargs = {
            "QueueUrl": url,
            "MessageBody": message.to_json(),
        }
        if delay_seconds > 0:
            kwargs["DelaySeconds"] = delay_seconds

        resp = self._client.send_message(**kwargs)
        msg_id = resp.get("MessageId", message.event_id)
        logger.debug("SQS sent message %s to %s (id: %s)", message.event_id, queue_name, msg_id)
        return msg_id

    def send_batch(self, queue_name: str, messages: List[QueueMessage]) -> List[str]:
        if not messages:
            return []
        url = self._get_url(queue_name)
        entries = [
            {
                "Id": m.event_id[:80],
                "MessageBody": m.to_json(),
            }
            for m in messages
        ]
        resp = self._client.send_message_batch(QueueUrl=url, Entries=entries)
        successful = [s["Id"] for s in resp.get("Successful", [])]
        if resp.get("Failed"):
            logger.error("SQS batch send partial failure on %s: %s", queue_name, resp.get("Failed"))
        return successful

    def receive_messages(
        self,
        queue_name: str,
        max_messages: int = 10,
        wait_time_seconds: int = 0,
    ) -> List[QueueMessage]:
        url = self._get_url(queue_name)
        resp = self._client.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=wait_time_seconds,
        )
        raw_msgs = resp.get("Messages", [])
        results: List[QueueMessage] = []
        for rm in raw_msgs:
            try:
                raw_body = rm["Body"]
                import json
                try:
                    parsed = json.loads(raw_body)
                    if isinstance(parsed, dict) and parsed.get("Type") == "Notification" and "Message" in parsed:
                        raw_body = parsed["Message"]
                except Exception:
                    pass
                msg = QueueMessage.from_json(raw_body, receipt_handle=rm["ReceiptHandle"])
                results.append(msg)
            except Exception as e:
                logger.error("Failed to deserialize SQS message body: %s", e)
        return results

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        url = self._get_url(queue_name)
        self._client.delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)

    def send_to_dlq(self, queue_name: str, message: QueueMessage, error_reason: str) -> None:
        dlq_name = f"{queue_name.replace('_queue', '')}_dlq"
        message.error_reason = error_reason
        self.send_message(dlq_name, message)
        if message.receipt_handle:
            self.delete_message(queue_name, message.receipt_handle)
        logger.warning("Routed message %s from %s to DLQ %s: %s", message.event_id, queue_name, dlq_name, error_reason)

    def get_queue_depth(self, queue_name: str) -> int:
        url = self._get_url(queue_name)
        resp = self._client.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )
        attrs = resp.get("Attributes", {})
        return int(attrs.get("ApproximateNumberOfMessages", 0))

    def purge(self, queue_name: str) -> None:
        url = self._get_url(queue_name)
        self._client.purge_queue(QueueUrl=url)

    def clear_all(self) -> None:
        """Purge all configured queues (useful in test teardown)."""
        for url in self._queue_urls.values():
            if url:
                try:
                    self._client.purge_queue(QueueUrl=url)
                except Exception:
                    pass
