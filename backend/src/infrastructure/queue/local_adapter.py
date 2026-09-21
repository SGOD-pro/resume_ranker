"""
local_adapter.py — In-memory deterministic QueueAdapter for local development & testing
=======================================================================================
Implements FIFO queue behavior, message visibility tracking, receipt handles, and DLQ routing
without requiring AWS or LocalStack. Thread-safe and fully inspectable in unit/integration tests.
"""

import logging
import threading
import uuid
from collections import defaultdict, deque
from typing import Dict, List, Optional

from src.infrastructure.queue.base import QueueAdapter
from src.infrastructure.queue.message import QueueMessage

logger = logging.getLogger(__name__)


class LocalQueueAdapter(QueueAdapter):
    """In-memory deterministic queue adapter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # queue_name -> deque of QueueMessage
        self._queues: Dict[str, deque[QueueMessage]] = defaultdict(deque)
        # queue_name -> list of QueueMessage in DLQ
        self._dlqs: Dict[str, List[QueueMessage]] = defaultdict(list)
        # receipt_handle -> (queue_name, QueueMessage)
        self._inflight: Dict[str, tuple[str, QueueMessage]] = {}

    def send_message(self, queue_name: str, message: QueueMessage, delay_seconds: int = 0) -> str:
        with self._lock:
            msg_copy = QueueMessage.from_json(message.to_json())
            self._queues[queue_name].append(msg_copy)
            logger.debug("Enqueued message %s to local queue %s (depth=%d)", msg_copy.event_id, queue_name, len(self._queues[queue_name]))
            return msg_copy.event_id

    def send_batch(self, queue_name: str, messages: List[QueueMessage]) -> List[str]:
        ids: List[str] = []
        with self._lock:
            for m in messages:
                msg_copy = QueueMessage.from_json(m.to_json())
                self._queues[queue_name].append(msg_copy)
                ids.append(msg_copy.event_id)
        return ids

    def receive_messages(
        self,
        queue_name: str,
        max_messages: int = 10,
        wait_time_seconds: int = 0,
    ) -> List[QueueMessage]:
        results: List[QueueMessage] = []
        with self._lock:
            q = self._queues[queue_name]
            count = 0
            while q and count < max_messages:
                msg = q.popleft()
                handle = f"rh_{uuid.uuid4().hex[:12]}"
                msg.receipt_handle = handle
                self._inflight[handle] = (queue_name, msg)
                results.append(msg)
                count += 1
        return results

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        with self._lock:
            if receipt_handle in self._inflight:
                del self._inflight[receipt_handle]
                logger.debug("Acknowledged and deleted message %s from %s", receipt_handle, queue_name)

    def send_to_dlq(self, queue_name: str, message: QueueMessage, error_reason: str) -> None:
        with self._lock:
            msg_copy = QueueMessage.from_json(message.to_json())
            msg_copy.error_reason = error_reason
            if msg_copy.receipt_handle and msg_copy.receipt_handle in self._inflight:
                del self._inflight[msg_copy.receipt_handle]
            self._dlqs[queue_name].append(msg_copy)
            logger.warning("Routed message %s to DLQ for %s (reason: %s)", msg_copy.event_id, queue_name, error_reason)

    def get_queue_depth(self, queue_name: str) -> int:
        with self._lock:
            return len(self._queues[queue_name])

    def get_dlq_messages(self, queue_name: str) -> List[QueueMessage]:
        with self._lock:
            return list(self._dlqs[queue_name])

    def purge(self, queue_name: str) -> None:
        with self._lock:
            self._queues[queue_name].clear()
            self._dlqs[queue_name].clear()

    def clear_all(self) -> None:
        """Clear all queues, DLQs, and inflight messages."""
        with self._lock:
            self._queues.clear()
            self._dlqs.clear()
            self._inflight.clear()
