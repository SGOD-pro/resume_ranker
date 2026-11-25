"""
worker.py — Standalone pipeline worker process
===============================================
Run this as a separate process from the API server to consume SQS queues
durably. This MUST NOT run inside the uvicorn/API process in production.

Usage:
    uv run python worker.py

Environment variables:
    USE_REAL_SQS        = true   (required in production)
    AWS_PROFILE         = aws    (or set standard AWS env vars)
    AWS_DEFAULT_REGION  = ap-south-1

The worker polls all pipeline queues in a round-robin loop with bounded
concurrency per stage. Each stage is separated so a slow ODL parse never
starves fast-parse workers.

Crash recovery:
    SQS visibility timeout ensures messages reappear if the worker crashes
    before deleting them. Each worker function must be idempotent.

Health:
    The worker logs a heartbeat every 60 seconds so your process supervisor
    (systemd, ECS, Kubernetes) can detect hangs.
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

# Ensure backend src is importable when run directly from the backend/ directory
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("worker")


def _require_real_sqs() -> None:
    """Fail loudly if USE_REAL_SQS is not set — no silent fallback in production."""
    use_real = os.environ.get("USE_REAL_SQS", "").lower()
    if use_real not in ("true", "1", "yes"):
        logger.critical(
            "FATAL: USE_REAL_SQS must be 'true' to run the standalone worker. "
            "Set USE_REAL_SQS=true in your environment and configure SQS queue URLs."
        )
        sys.exit(1)

    from src.config.aws import get_settings
    settings = get_settings()
    missing = []
    if not settings.SQS_FAST_PARSE_URL:
        missing.append("SQS_FAST_PARSE_URL")
    if not settings.SQS_ODL_BATCH_URL:
        missing.append("SQS_ODL_BATCH_URL")
    if not settings.SQS_NOVA_URL:
        missing.append("SQS_NOVA_URL")
    if not settings.SQS_FINAL_RANK_URL:
        missing.append("SQS_FINAL_RANK_URL")
    if missing:
        logger.critical("FATAL: Missing required SQS URL environment variables: %s", ", ".join(missing))
        sys.exit(1)


_SHUTDOWN = False


def _handle_signal(signum, frame):
    global _SHUTDOWN
    logger.info("Signal %s received — initiating graceful shutdown", signum)
    _SHUTDOWN = True


def run_worker_loop(
    poll_interval: float = 0.5,
    heartbeat_interval: float = 60.0,
    fast_parse_concurrency: int = 4,
    odl_concurrency: int = 2,
    nova_concurrency: int = 2,
    rank_concurrency: int = 2,
) -> None:
    """Main polling loop. Runs until SIGTERM/SIGINT."""
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

    adapter = get_queue_adapter()
    logger.info("Worker daemon started. Queue adapter: %s", type(adapter).__name__)

    last_heartbeat = time.time()
    last_relay = time.time()
    _RELAY_INTERVAL = 30.0
    total_processed = 0

    while not _SHUTDOWN:
        processed_in_round = 0

        # 1. Fast parse — highest priority
        try:
            msgs = adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=fast_parse_concurrency, wait_time_seconds=1)
            for msg in msgs:
                if _SHUTDOWN:
                    break
                process_fast_parse_message(msg)
                processed_in_round += 1
        except Exception as e:
            logger.error("Error in fast_parse_worker iteration: %s", e)

        # 2. ODL batch
        try:
            msgs = adapter.receive_messages(ODL_BATCH_QUEUE, max_messages=odl_concurrency, wait_time_seconds=1)
            for msg in msgs:
                if _SHUTDOWN:
                    break
                process_odl_batch_message(msg)
                processed_in_round += 1
        except Exception as e:
            logger.error("Error in odl_batch_worker iteration: %s", e)

        # 3. Nova
        try:
            msgs = adapter.receive_messages(NOVA_QUEUE, max_messages=nova_concurrency, wait_time_seconds=1)
            for msg in msgs:
                if _SHUTDOWN:
                    break
                process_nova_message(msg)
                processed_in_round += 1
        except Exception as e:
            logger.error("Error in nova_queue_worker iteration: %s", e)

        # 4. Final rank
        try:
            msgs = adapter.receive_messages(FINAL_RANK_QUEUE, max_messages=rank_concurrency, wait_time_seconds=1)
            for msg in msgs:
                if _SHUTDOWN:
                    break
                process_final_rank_message(msg)
                processed_in_round += 1
        except Exception as e:
            logger.error("Error in final_rank_worker iteration: %s", e)

        # 5. Outbox relay — flush stuck PENDING records every 30s
        now = time.time()
        if now - last_relay >= _RELAY_INTERVAL:
            last_relay = now
            try:
                from src.infrastructure.queue.outbox import relay_pending_outbox
                relayed = relay_pending_outbox()
                if relayed:
                    logger.info("Outbox relay: re-dispatched %d stuck records", relayed)
            except Exception as relay_err:
                logger.warning("Outbox relay error: %s", relay_err)

        total_processed += processed_in_round

        now = time.time()
        if now - last_heartbeat >= heartbeat_interval:
            logger.info(
                "Worker heartbeat — total_processed=%d, uptime=%.0fs",
                total_processed,
                now - start_time,
            )
            last_heartbeat = now

        if processed_in_round == 0:
            time.sleep(poll_interval)

    logger.info("Worker shutdown complete. Total messages processed: %d", total_processed)



if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _require_real_sqs()

    start_time = time.time()
    logger.info("━" * 60)
    logger.info("Resume Ranker — Pipeline Worker Process")
    logger.info("━" * 60)

    run_worker_loop()
