"""
worker_runner.py — Multi-stage queue dispatcher and worker runner
==================================================================
Supports both deterministic synchronous queue draining (for testing and local dev)
and asynchronous background polling loops for continuous queue processing.
"""

import asyncio
import logging
from typing import Optional

from src.infrastructure.queue.queue_manager import (
    FAST_PARSE_QUEUE,
    FINAL_RANK_QUEUE,
    NOVA_QUEUE,
    ODL_BATCH_QUEUE,
    get_queue_adapter,
)
from src.pipeline.fast_parse_worker import process_fast_parse_message
from src.pipeline.final_rank_worker import process_final_rank_message
from src.pipeline.nova_queue_worker import process_nova_message
from src.pipeline.odl_batch_worker import process_odl_batch_message

logger = logging.getLogger(__name__)


def drain_all_queues_sync(max_rounds: int = 50) -> int:
    """Synchronously drain all pending messages across all pipeline queues.

    Useful in tests and local development to run end-to-end workflows deterministically.
    Returns total messages processed.
    """
    adapter = get_queue_adapter()
    total_processed = 0
    consecutive_empty = 0

    for _ in range(max_rounds):
        processed_in_round = 0

        # 1. Fast parse queue
        fast_msgs = adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=10, wait_time_seconds=1)
        for msg in fast_msgs:
            process_fast_parse_message(msg)
            processed_in_round += 1

        # 2. ODL batch queue
        odl_msgs = adapter.receive_messages(ODL_BATCH_QUEUE, max_messages=5, wait_time_seconds=1)
        for msg in odl_msgs:
            process_odl_batch_message(msg)
            processed_in_round += 1

        # 3. Nova queue
        nova_msgs = adapter.receive_messages(NOVA_QUEUE, max_messages=5, wait_time_seconds=1)
        for msg in nova_msgs:
            process_nova_message(msg)
            processed_in_round += 1

        # 4. Final rank queue
        rank_msgs = adapter.receive_messages(FINAL_RANK_QUEUE, max_messages=5, wait_time_seconds=1)
        for msg in rank_msgs:
            process_final_rank_message(msg)
            processed_in_round += 1

        total_processed += processed_in_round
        if processed_in_round == 0:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            import time
            time.sleep(1)
        else:
            consecutive_empty = 0

    return total_processed


class BackgroundWorkerDaemon:
    """Async background worker daemon that continuously polls queues."""

    def __init__(self, poll_interval: float = 0.5) -> None:
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def _loop(self) -> None:
        adapter = get_queue_adapter()
        logger.info("BackgroundWorkerDaemon started")
        last_relay = 0.0
        _RELAY_INTERVAL = 30.0  # relay stuck outbox records every 30s

        while self._running:
            try:
                # 1. Fast parse
                fast_msgs = adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=4)
                for msg in fast_msgs:
                    await asyncio.to_thread(process_fast_parse_message, msg)

                # 2. ODL batch
                odl_msgs = adapter.receive_messages(ODL_BATCH_QUEUE, max_messages=2)
                for msg in odl_msgs:
                    await asyncio.to_thread(process_odl_batch_message, msg)

                # 3. Nova
                nova_msgs = adapter.receive_messages(NOVA_QUEUE, max_messages=2)
                for msg in nova_msgs:
                    await asyncio.to_thread(process_nova_message, msg)

                # 4. Final rank
                rank_msgs = adapter.receive_messages(FINAL_RANK_QUEUE, max_messages=2)
                for msg in rank_msgs:
                    await asyncio.to_thread(process_final_rank_message, msg)

                # 5. Outbox relay — periodically flush stuck PENDING outbox records
                import time as _time
                now = _time.monotonic()
                if now - last_relay >= _RELAY_INTERVAL:
                    last_relay = now
                    try:
                        from src.infrastructure.queue.outbox import relay_pending_outbox
                        relayed = await asyncio.to_thread(relay_pending_outbox)
                        if relayed:
                            logger.info("Outbox relay: re-dispatched %d stuck records", relayed)
                    except Exception as relay_err:
                        logger.warning("Outbox relay error: %s", relay_err)

            except Exception as e:
                logger.error("BackgroundWorkerDaemon iteration error: %s", e)

            await asyncio.sleep(self._poll_interval)


    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                self._task = None


_daemon_instance: Optional[BackgroundWorkerDaemon] = None


def get_worker_daemon() -> BackgroundWorkerDaemon:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = BackgroundWorkerDaemon()
    return _daemon_instance
