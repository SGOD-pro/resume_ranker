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
from src.pipeline.stage1_worker import extract_job_file_from_message, process_stage1_message
from src.pipeline.stage2_worker import process_stage2_batch, _extract_job_file_id
from src.pipeline.scoring_worker import process_scoring_message

logger = logging.getLogger(__name__)


def dispatch_fast_parse(msg) -> None:
    from src.infrastructure.repositories.documents_repository import DocumentsRepository
    from src.infrastructure.repositories.files_repository import FilesRepository
    job_id, file_id, _ = extract_job_file_from_message(msg)
    if job_id and file_id:
        docs_repo = DocumentsRepository()
        if docs_repo.get(job_id, file_id):
            process_fast_parse_message(msg)
            return
        f_repo = FilesRepository()
        if f_repo.get_file(job_id, file_id):
            process_stage1_message(msg)
            return
    process_fast_parse_message(msg)


def dispatch_odl_batch(msgs) -> None:
    from src.infrastructure.repositories.files_repository import FilesRepository
    f_repo = FilesRepository()
    file_msgs = []
    doc_msgs = []
    nova_msgs = []
    for m in msgs:
        stage = getattr(m, "stage", None)
        if stage == "NOVA" or (not getattr(m, "document_ids", None) and getattr(m, "document_id", None) and getattr(m, "stage", None) != "ODL_BATCH"):
            # Check if this is a FileItem first
            jid, fid = _extract_job_file_id(m)
            if jid and fid and f_repo.get_file(jid, fid):
                file_msgs.append(m)
            else:
                nova_msgs.append(m)
            continue

        jid, fid = _extract_job_file_id(m)
        if jid and fid and f_repo.get_file(jid, fid):
            file_msgs.append(m)
        else:
            doc_msgs.append(m)

    if file_msgs:
        process_stage2_batch(file_msgs)
    for m in doc_msgs:
        process_odl_batch_message(m)
    for m in nova_msgs:
        dispatch_nova(m)


def dispatch_nova(msg) -> None:
    stage = getattr(msg, "stage", None)
    if stage == "ODL_BATCH" or getattr(msg, "document_ids", None):
        process_odl_batch_message(msg)
        return

    from src.infrastructure.repositories.files_repository import FilesRepository
    jid, fid = _extract_job_file_id(msg)
    if jid and fid:
        f_repo = FilesRepository()
        if f_repo.get_file(jid, fid):
            process_stage2_batch([msg])
            return
    process_nova_message(msg)


def dispatch_final_rank(msg) -> None:
    from src.infrastructure.repositories.files_repository import FilesRepository
    job_id = getattr(msg, "job_id", None)
    if not job_id and hasattr(msg, "body") and isinstance(msg.body, dict):
        job_id = msg.body.get("job_id")
    if job_id:
        f_repo = FilesRepository()
        if f_repo.list_files_for_job(job_id):
            process_scoring_message(msg)
            return
    process_final_rank_message(msg)


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
            dispatch_fast_parse(msg)
            processed_in_round += 1

        # 2. ODL batch queue
        odl_msgs = adapter.receive_messages(ODL_BATCH_QUEUE, max_messages=10, wait_time_seconds=1)
        if odl_msgs:
            dispatch_odl_batch(odl_msgs)
            processed_in_round += len(odl_msgs)

        # 3. Nova queue
        nova_msgs = adapter.receive_messages(NOVA_QUEUE, max_messages=10, wait_time_seconds=1)
        for msg in nova_msgs:
            dispatch_nova(msg)
            processed_in_round += 1

        # 4. Final rank queue
        rank_msgs = adapter.receive_messages(FINAL_RANK_QUEUE, max_messages=5, wait_time_seconds=1)
        for msg in rank_msgs:
            dispatch_final_rank(msg)
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
                # 1. Fast parse (multithreaded concurrent execution)
                fast_msgs = adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=10)
                if fast_msgs:
                    await asyncio.gather(*(asyncio.to_thread(dispatch_fast_parse, msg) for msg in fast_msgs))

                # 2. ODL batch
                odl_msgs = adapter.receive_messages(ODL_BATCH_QUEUE, max_messages=10)
                if odl_msgs:
                    await asyncio.to_thread(dispatch_odl_batch, odl_msgs)

                # 3. Nova (concurrent LLM requests)
                nova_msgs = adapter.receive_messages(NOVA_QUEUE, max_messages=4)
                if nova_msgs:
                    await asyncio.gather(*(asyncio.to_thread(dispatch_nova, msg) for msg in nova_msgs))

                # 4. Final rank
                rank_msgs = adapter.receive_messages(FINAL_RANK_QUEUE, max_messages=2)
                for msg in rank_msgs:
                    await asyncio.to_thread(dispatch_final_rank, msg)

                # 5. Outbox relay — periodically flush stuck PENDING outbox records across all jobs
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

                    try:
                        from src.infrastructure.repositories.files_repository import FilesRepository
                        relayed_outbox, recovered_jobs = await asyncio.to_thread(FilesRepository().reconcile_all_pending_outboxes)
                        if relayed_outbox or recovered_jobs:
                            logger.info("Independent outbox relay: %d events relayed, %d stranded jobs recovered",
                                        relayed_outbox, recovered_jobs)
                    except Exception as repo_relay_err:
                        logger.warning("FilesRepository outbox relay error: %s", repo_relay_err)

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
