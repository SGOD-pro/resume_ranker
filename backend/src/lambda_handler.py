"""
lambda_handler.py — Unified AWS Lambda event dispatcher
=======================================================
Routes all triggers for the consolidated environment Lambda function:
- HTTP API Gateway v2 / REST v1 requests -> FastAPI via Mangum
- SQS batches -> Stage 1, Stage 2, Scoring, or DLQ handlers (strictly via trusted eventSourceARN)
- EventBridge / Scheduler events -> Durable outbox & stranded job reconciliation

All target handler imports are deferred (lazy) inside route branches so API
cold starts do not load heavy extraction or scoring stacks, and worker cold starts
do not load FastAPI/Mangum unless needed.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Apply configured LOG_LEVEL on Lambda root logger (runtime defaults to WARNING)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)


def _extract_queue_name(url_or_arn: str) -> str:
    """Return final queue name segment from an SQS queue URL or ARN."""
    val = (url_or_arn or "").strip()
    if not val:
        return ""
    if val.startswith("arn:aws:sqs:"):
        return val.rsplit(":", 1)[-1]
    return val.rstrip("/").rsplit("/", 1)[-1]


def _resolve_sqs_route(event_source_arn: str, settings: Any) -> Optional[str]:
    """Resolve SQS route ('stage1'|'stage2'|'scoring'|'dlq') strictly via trusted ARN and config."""
    arn = (event_source_arn or "").strip()
    if not arn.startswith("arn:aws:sqs:"):
        return None
    incoming_name = arn.rsplit(":", 1)[-1]
    if not incoming_name:
        return None

    route_candidates = {
        "stage1": [
            getattr(settings, "SQS_STAGE1_QUEUE_ARN", ""),
            getattr(settings, "SQS_STAGE1_QUEUE_URL", ""),
            getattr(settings, "SQS_FAST_PARSE_QUEUE_URL", ""),
        ],
        "stage2": [
            getattr(settings, "SQS_STAGE2_QUEUE_ARN", ""),
            getattr(settings, "SQS_STAGE2_QUEUE_URL", ""),
            getattr(settings, "SQS_ODL_BATCH_QUEUE_URL", ""),
            getattr(settings, "SQS_NOVA_QUEUE_URL", ""),
        ],
        "scoring": [
            getattr(settings, "SQS_SCORING_QUEUE_ARN", ""),
            getattr(settings, "SQS_SCORING_QUEUE_URL", ""),
            getattr(settings, "SQS_FINAL_RANK_QUEUE_URL", ""),
        ],
        "dlq": [
            getattr(settings, "SQS_STAGE1_DLQ_ARN", ""),
            getattr(settings, "SQS_STAGE2_DLQ_ARN", ""),
            getattr(settings, "SQS_SCORING_DLQ_ARN", ""),
            getattr(settings, "SQS_STAGE1_DLQ_URL", ""),
            getattr(settings, "SQS_STAGE2_DLQ_URL", ""),
            getattr(settings, "SQS_SCORING_DLQ_URL", ""),
            getattr(settings, "SQS_FAST_PARSE_DLQ_URL", ""),
            getattr(settings, "SQS_ODL_BATCH_DLQ_URL", ""),
            getattr(settings, "SQS_NOVA_DLQ_URL", ""),
            getattr(settings, "SQS_FINAL_RANK_DLQ_URL", ""),
        ],
    }

    for route_name, configured_refs in route_candidates.items():
        for ref in configured_refs:
            ref_clean = (ref or "").strip()
            if not ref_clean:
                continue
            if ref_clean.startswith("arn:aws:sqs:") and ref_clean == arn:
                return route_name
            if not ref_clean.startswith("arn:") and _extract_queue_name(ref_clean) == incoming_name:
                return route_name
    return None


def _is_http_event(event: Dict[str, Any]) -> bool:
    if "rawPath" in event or "httpMethod" in event:
        return True
    req_ctx = event.get("requestContext")
    if isinstance(req_ctx, dict) and ("http" in req_ctx or "httpMethod" in req_ctx):
        return True
    return False


def _is_scheduled_event(event: Dict[str, Any]) -> bool:
    source = str(event.get("source", "")).lower()
    detail_type = str(event.get("detail-type", "")).lower()
    action = str(event.get("action", "")).lower()
    if source in ("aws.events", "aws.scheduler") and (
        "scheduled event" in detail_type or source == "aws.scheduler" or action == "reconcile_outbox"
    ):
        return True
    return action == "reconcile_outbox"


def _dispatch_sqs(records: List[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    if not records:
        return {"statusCode": 200, "processed": 0, "batchItemFailures": []}

    from src.config.aws import get_settings
    settings = get_settings()

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    batch_item_failures: List[Dict[str, str]] = []

    for rec in records:
        if not isinstance(rec, dict):
            raise ValueError("Unsupported event source: invalid SQS record payload")
        event_source = rec.get("eventSource", "")
        arn = rec.get("eventSourceARN", "")
        if event_source != "aws:sqs" and not str(arn).startswith("arn:aws:sqs:"):
            raise ValueError(f"Unsupported event source in Records: {event_source or 'unknown'}")

        route = _resolve_sqs_route(arn, settings)
        if not route:
            logger.error("UnifiedHandler: rejecting untrusted or unconfigured SQS ARN: %s", arn)
            msg_id = rec.get("messageId")
            if msg_id:
                batch_item_failures.append({"itemIdentifier": msg_id})
            else:
                raise ValueError(f"Untrusted SQS eventSourceARN without messageId: {arn}")
            continue
        grouped.setdefault(route, []).append(rec)

    processed_total = 0
    for route, route_records in grouped.items():
        sub_event = {"Records": route_records}
        if route == "stage1":
            from src.handlers.stage1 import handler as target_handler
        elif route == "stage2":
            from src.handlers.stage2 import handler as target_handler
        elif route == "scoring":
            from src.handlers.scoring import handler as target_handler
        elif route == "dlq":
            from src.handlers.dlq import handler as target_handler
        else:
            continue

        res = target_handler(sub_event, context)
        if isinstance(res, dict):
            processed_total += int(res.get("processed", 0) or 0)
            for fail in res.get("batchItemFailures", []) or []:
                if fail and fail not in batch_item_failures:
                    batch_item_failures.append(fail)

    return {
        "statusCode": 200,
        "processed": processed_total,
        "batchItemFailures": batch_item_failures,
    }


def handler(event: Dict[str, Any], context: Any = None) -> Any:
    """Unified AWS Lambda entrypoint routing API Gateway, SQS, and Scheduler events."""
    _configure_logging()
    if not isinstance(event, dict):
        raise ValueError("Unsupported event source: payload must be a dict")

    if "Records" in event and isinstance(event["Records"], list):
        return _dispatch_sqs(event["Records"], context)

    if _is_http_event(event):
        from src.handlers.api import handler as api_handler
        return api_handler(event, context)

    if _is_scheduled_event(event):
        from src.handlers.recovery import handler as rec_handler
        return rec_handler(event, context)

    logger.error("UnifiedHandler: Unsupported event source with top-level keys %s", list(event.keys()))
    raise ValueError("Unsupported event source")


def stage1_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Backwards-compatible Stage 1 SQS event source handler."""
    from src.handlers.stage1 import handler as s1_handler
    return s1_handler(event, context)


def stage2_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Backwards-compatible Stage 2 SQS event source handler."""
    from src.handlers.stage2 import handler as s2_handler
    return s2_handler(event, context)


def scoring_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Backwards-compatible Scoring SQS event source handler."""
    from src.handlers.scoring import handler as score_handler
    return score_handler(event, context)


def dlq_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Backwards-compatible DLQ consumer handler."""
    from src.handlers.dlq import handler as d_handler
    return d_handler(event, context)


def recovery_handler(event: Dict[str, Any] = None, context: Any = None) -> Dict[str, Any]:
    """Backwards-compatible autonomous outbox recovery handler."""
    from src.handlers.recovery import handler as rec_handler
    return rec_handler(event, context)
