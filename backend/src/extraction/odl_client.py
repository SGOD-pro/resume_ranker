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

_lambda_client = None

def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        from src.config.aws import get_client
        _lambda_client = get_client("lambda")
    return _lambda_client


def _invoke_prod(event: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the ODL lambda via boto3 (production path).

    Raises ODLParseError for all failure modes — never leaks ClientError,
    ValueError, or any other raw exception past this boundary (R-20).
    """
    try:
        lambda_client = _get_lambda_client()
        response = lambda_client.invoke(
            FunctionName="odl-parser-lambda-prod",
            InvocationType="RequestResponse",
            LogType="Tail",
            Payload=json.dumps(event).encode("utf-8"),
        )
        
        # Log Lambda memory usage
        if "LogResult" in response:
            import base64
            import re
            log_result = base64.b64decode(response["LogResult"]).decode("utf-8")
            print("--- LAMBDA LOG ---")
            print(log_result)
            print("------------------")
            memory_match = re.search(r"Max Memory Used:\s*(\d+\s*MB)", log_result)
            if memory_match:
                print(f"ODL Lambda Max Memory Used: {memory_match.group(1)}")

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
    import uuid
    settings = get_settings()
    staging_bucket = (getattr(settings, "ODL_STAGING_BUCKET", "") or "").strip()
    staging_prefix = (getattr(settings, "ODL_STAGING_PREFIX", "") or "preprod-staging").strip("/")
    staged_key: Optional[str] = None
    target_bucket = s3_bucket
    target_key = s3_key
    s3_client = None

    try:
        if staging_bucket and staging_bucket != s3_bucket:
            from src.config.aws import get_client
            s3_client = get_client("s3")
            staged_key = f"{staging_prefix}/{uuid.uuid4().hex}/single.pdf"
            s3_client.copy_object(
                Bucket=staging_bucket,
                Key=staged_key,
                CopySource={"Bucket": s3_bucket, "Key": s3_key},
            )
            target_bucket = staging_bucket
            target_key = staged_key

        event = {
            "documents": [
                {
                    "document_id": "__single__",
                    "s3_bucket": target_bucket,
                    "s3_key": target_key,
                }
            ],
            "save_images": False,
        }

        payload = _invoke_prod(event)
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
    finally:
        if s3_client and staged_key and staging_bucket:
            try:
                s3_client.delete_object(Bucket=staging_bucket, Key=staged_key)
            except Exception as del_err:
                logger.warning("Failed cleaning staged ODL object s3://%s/%s: %s", staging_bucket, staged_key, del_err)


def parse_batch(documents: List[DocDescriptor]) -> BatchParseResult:
    """
    Parse multiple documents in ONE odl-parser-lambda invocation — a single
    JVM boot amortised across all N documents.
    """
    if not documents:
        return BatchParseResult()

    import uuid
    settings = get_settings()
    save_images = any(d.save_images for d in documents)
    staging_bucket = (getattr(settings, "ODL_STAGING_BUCKET", "") or "").strip()
    staging_prefix = (getattr(settings, "ODL_STAGING_PREFIX", "") or "preprod-staging").strip("/")
    staged_objects: List[str] = []
    s3_client = None

    batch_result = BatchParseResult()
    run_id = uuid.uuid4().hex[:12]

    try:
        doc_payloads = []
        for d in documents:
            if staging_bucket and staging_bucket != d.s3_bucket:
                if s3_client is None:
                    from src.config.aws import get_client
                    s3_client = get_client("s3")
                staged_key = f"{staging_prefix}/{run_id}/{d.document_id}.pdf"
                s3_client.copy_object(
                    Bucket=staging_bucket,
                    Key=staged_key,
                    CopySource={"Bucket": d.s3_bucket, "Key": d.s3_key},
                )
                staged_objects.append(staged_key)
                doc_payloads.append({
                    "document_id": d.document_id,
                    "s3_bucket": staging_bucket,
                    "s3_key": staged_key,
                })
            else:
                doc_payloads.append({
                    "document_id": d.document_id,
                    "s3_bucket": d.s3_bucket,
                    "s3_key": d.s3_key,
                })

        event = {
            "documents": doc_payloads,
            "save_images": save_images,
        }

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
    finally:
        if s3_client and staging_bucket:
            for sk in staged_objects:
                try:
                    s3_client.delete_object(Bucket=staging_bucket, Key=sk)
                except Exception as del_err:
                    logger.warning("Failed cleaning staged ODL batch object s3://%s/%s: %s", staging_bucket, sk, del_err)

    return batch_result
