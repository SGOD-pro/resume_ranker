import json
import logging
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import boto3
from botocore.exceptions import ClientError

from src.config.aws import get_settings

logger = logging.getLogger(__name__)


class ODLParseError(Exception):
    """Unified exception for any failure in the ODL parsing pipeline."""
    pass


@dataclass
class ODLParseResult:
    markdown: str
    elements: list[Dict[str, Any]]
    image_s3_keys: List[str] = field(default_factory=list)


@dataclass
class DocDescriptor:
    """Input descriptor for a single document in a batch parse call."""
    document_id: str
    s3_bucket: str
    s3_key: str
    save_images: bool = False


@dataclass
class BatchParseResult:
    """
    Per-document result attribution for a batch ODL call.

    ADR-09 / ADR-10: batch exceptions (e.g. corrupt PDF) MUST NOT surface as a
    single opaque error — each document must be independently attributed to either
    ``results`` (success) or ``failed`` (ODLParseError).  Callers never see a raw
    batch-level exception.
    """
    results: Dict[str, ODLParseResult] = field(default_factory=dict)
    # Maps document_id -> ODLParseError for any doc that failed
    failed: Dict[str, ODLParseError] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _import_lambda_handler():
    """Import odl/main.py lambda_handler for the local bypass path."""
    try:
        from odl.main import lambda_handler
        return lambda_handler
    except ImportError:
        import os
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
        if project_root not in sys.path:
            sys.path.append(project_root)
        from odl.main import lambda_handler
        return lambda_handler


def _invoke_local(event: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the ODL lambda handler in-process (local bypass).

    Raises ODLParseError for all failure modes — never leaks ImportError,
    ValueError, or any other raw exception past this boundary (R-20).
    """
    try:
        lambda_handler = _import_lambda_handler()
        response = lambda_handler(event, None)
        if isinstance(response, dict) and "statusCode" in response:
            if response["statusCode"] != 200:
                raise ODLParseError(
                    f"ODL returned {response['statusCode']}: {response.get('body')}"
                )
            body = response.get("body", "{}")
            return json.loads(body) if isinstance(body, str) else body
        return response
    except ODLParseError:
        raise
    except Exception as exc:
        raise ODLParseError(f"Local ODL bypass error: {exc}") from exc


def _invoke_prod(event: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the ODL lambda via boto3 (production path).

    Raises ODLParseError for all failure modes — never leaks ClientError,
    ValueError, or any other raw exception past this boundary (R-20).
    """
    try:
        lambda_client = boto3.client("lambda")
        response = lambda_client.invoke(
            FunctionName="odl-parser-lambda",
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode("utf-8"),
        )
        payload_bytes = response["Payload"].read()
        response_dict = json.loads(payload_bytes)

        if "FunctionError" in response:
            raise ODLParseError(f"ODL Lambda FunctionError: {response_dict}")

        if "statusCode" in response_dict:
            if response_dict["statusCode"] != 200:
                raise ODLParseError(
                    f"ODL returned {response_dict['statusCode']}: {response_dict.get('body')}"
                )
            body = response_dict.get("body", "{}")
            return json.loads(body) if isinstance(body, str) else body

        return response_dict
    except ODLParseError:
        raise
    except ClientError as exc:
        raise ODLParseError(f"ODL Lambda ClientError: {exc}") from exc
    except Exception as exc:
        raise ODLParseError(f"ODL Lambda invoke error: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse(s3_bucket: str, s3_key: str) -> ODLParseResult:
    """
    Parse a single document using ODL.

    Used by:
    - The standalone /ats-check path (single-file, synchronous, user-facing)
    - Any one-off single-document call that must NOT wait on a batch window.

    Per R-20: wraps both the local-bypass and boto3.invoke paths; callers only
    ever see ODLParseError — never ImportError, ClientError, or subprocess errors.
    """
    settings = get_settings()
    # Single-doc uses the OLD single-document event shape for backward compat
    event = {
        "documents": [
            {
                "document_id": "__single__",
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
            }
        ],
        "save_images": False,
    }

    try:
        if settings.environment == "local":
            payload = _invoke_local(event)
        else:
            payload = _invoke_prod(event)

        # New batch response shape: {"results": [...], "failed": [...]}
        results = payload.get("results", [])
        if not results:
            raise ValueError("ODL response contained no results")

        doc = results[0]
        return ODLParseResult(
            markdown=doc.get("markdown", ""),
            elements=doc.get("elements", []),
            image_s3_keys=doc.get("image_s3_keys", []),
        )

    except Exception as e:
        logger.error("ODL Parse (single) failed: %s", e, exc_info=True)
        raise ODLParseError(f"ODL parsing failed: {e}") from e


def parse_batch(documents: List[DocDescriptor]) -> BatchParseResult:
    """
    Parse multiple documents in ONE odl-parser-lambda invocation — a single
    JVM boot amortised across all N documents.

    ADR-10 / R-21: All quality-gate-failed documents in the batch pipeline MUST
    use this method, not ``parse()`` (except /ats-check — see R-21).

    Partial-failure contract (ADR-09 / ADR-10):
    - If the ODL lambda raises a whole-batch exception (e.g. the invoke itself
      failed), every document is attributed to ``BatchParseResult.failed``.
    - If the lambda returns normally but lists some doc_ids in ``"failed"``,
      those are mapped to per-document ODLParseError entries in ``.failed``.
    - Documents that produced valid ``.md`` / ``.json`` output are in ``.results``.
    - No document silently disappears — either results or failed, always.
    """
    if not documents:
        return BatchParseResult()

    settings = get_settings()
    save_images = any(d.save_images for d in documents)

    event = {
        "documents": [
            {
                "document_id": d.document_id,
                "s3_bucket": d.s3_bucket,
                "s3_key": d.s3_key,
            }
            for d in documents
        ],
        "save_images": save_images,
    }

    batch_result = BatchParseResult()

    try:
        if settings.environment == "local":
            payload = _invoke_local(event)
        else:
            payload = _invoke_prod(event)

        # Map successful results
        for item in payload.get("results", []):
            doc_id = item.get("document_id")
            if doc_id:
                batch_result.results[doc_id] = ODLParseResult(
                    markdown=item.get("markdown", ""),
                    elements=item.get("elements", []),
                    image_s3_keys=item.get("image_s3_keys", []),
                )

        # Map per-document failures returned by the lambda
        for failed_doc_id in payload.get("failed", []):
            batch_result.failed[failed_doc_id] = ODLParseError(
                f"ODL convert() failed for document '{failed_doc_id}' "
                "(corrupt PDF or parse error — see Lambda logs)"
            )

    except Exception as e:
        # Whole-batch invoke failure: attribute to every document
        logger.error("ODL parse_batch failed for entire batch: %s", e, exc_info=True)
        for d in documents:
            batch_result.failed[d.document_id] = ODLParseError(
                f"ODL batch invoke failed: {e}"
            )

    return batch_result
