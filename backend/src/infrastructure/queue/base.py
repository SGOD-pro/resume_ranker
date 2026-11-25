"""
base.py — QueueAdapter abstract interface
=========================================
Defines the contract for queue operations across Local (in-memory) and AWS SQS implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.infrastructure.queue.message import QueueMessage


class QueueAdapter(ABC):
    """Abstract interface for message queue operations."""

    @abstractmethod
    def send_message(self, queue_name: str, message: QueueMessage, delay_seconds: int = 0) -> str:
        """Send a single message to the queue. Returns message ID."""
        pass

    @abstractmethod
    def send_batch(self, queue_name: str, messages: List[QueueMessage]) -> List[str]:
        """Send a batch of messages to the queue. Returns list of message IDs."""
        pass

    @abstractmethod
    def receive_messages(
        self,
        queue_name: str,
        max_messages: int = 10,
        wait_time_seconds: int = 0,
    ) -> List[QueueMessage]:
        """Receive up to max_messages from the queue."""
        pass

    @abstractmethod
    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        """Delete an acknowledged message from the queue."""
        pass

    @abstractmethod
    def send_to_dlq(self, queue_name: str, message: QueueMessage, error_reason: str) -> None:
        """Route a failed message to the corresponding Dead Letter Queue."""
        pass

    @abstractmethod
    def get_queue_depth(self, queue_name: str) -> int:
        """Return the number of messages currently pending in the queue."""
        pass

    @abstractmethod
    def purge(self, queue_name: str) -> None:
        """Purge all messages from a queue (useful in test teardown)."""
        pass
