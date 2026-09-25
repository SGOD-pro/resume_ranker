"""
stage2_worker.py — Fallback extraction worker (Stage 2: ODL & Nova LLM)
======================================================================
Triggered by messages from STAGE2_QUEUE / ODL_BATCH_QUEUE after Analyze request.
- Reads intermediate Stage 1 JSON from S3.
- If multi-column or low-quality layout: calls ODL Lambda parser.
- If critical fields missing: calls Bedrock Nova fallback, subject to:
    - LLM_FALLBACK_MAX_PER_JOB (max 5 per job)
    - Bedrock throttling is RETRYABLE via SQS backoff (raises exception to let SQS retry)
- Saves final extracted JSON to jobs/{job_id}/stage2/{file_id}.json.
- Idempotently transitions file to S2_DONE (terminal, decrements job.remaining).
- On fatal failure: marks S2_FAILED (terminal, decrements job.remaining).
"""

import json
import logging
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from src.config.aws import get_settings
from src.extraction.fallback.nova_service import NovaService
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.odl_client import DocDescriptor, ODLParseError, parse_batch
from src.infrastructure.models.file import FileStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.storage.storage_service import StorageService

logger = logging.getLogger(__name__)

LLM_FALLBACK_MAX_PER_JOB = 5


class RetryableThrottlingError(Exception):
    """Raised on Bedrock / AWS throttling so SQS retries via backoff."""
    pass


def process_stage2_message(message: Any) -> bool:
    """Process a single Stage 2 fallback message."""
    files_repo = FilesRepository()
    jobs_repo = JobsRepository()
    storage = StorageService()

    # Extract job_id and file_id
    job_id = getattr(message, "job_id", None)
    file_id = getattr(message, "document_id", None) or getattr(message, "file_id", None)

    if not job_id or not file_id:
        body = message.body if hasattr(message, "body") else message
        if isinstance(body, dict) and "body" in body:
            body = body["body"]
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                pass
        if isinstance(body, dict):
            job_id = body.get("job_id")
            file_id = body.get("document_id") or body.get("file_id")

    if not job_id or not file_id:
        logger.error("Stage2Worker: invalid message, missing job_id or file_id")
        return False

    file_item = files_repo.get_file(job_id, file_id)
    if file_item and file_item.is_terminal:
        logger.info("Stage2Worker: file %s/%s already terminal (%s), skipping", job_id, file_id, file_item.status)
        return True

    # Mark non-terminal S2_PROCESSING
    files_repo.update_file_non_terminal(job_id, file_id, FileStatus.S2_PROCESSING)

    try:
        # Load Stage 1 JSON from S3
        stage1_data = storage.get_stage1_json(job_id, file_id)
        fields = stage1_data.get("fields", {})
        quality = stage1_data.get("quality", {})
        unresolved = stage1_data.get("unresolved_chunks", [])
        raw_s3_key = file_item.s3_raw_key if file_item else f"jobs/{job_id}/raw/{file_id}.pdf"

        # Step 1: ODL Layout Fallback if quality is low
        if quality.get("score", 1.0) < 0.90 or quality.get("looks_tabular", False):
            try:
                doc_desc = DocDescriptor(
                    document_id=file_id,
                    s3_bucket=storage._bucket,
                    s3_key=raw_s3_key,
                )
                batch_res = parse_batch([doc_desc])
                if file_id in batch_res.results:
                    odl_res = batch_res.results[file_id]
                    odl_extracted = MarkdownExtractionService().extract(odl_res.markdown)
                    # Merge ODL extracted fields if better
                    odl_fields = odl_extracted.get("fields", {})
                    for k, v in odl_fields.items():
                        if v and (not fields.get(k) or len(str(v)) > len(str(fields.get(k, "")))):
                            fields[k] = v
                    unresolved = odl_extracted.get("unresolved_chunks", [])
                    logger.info("Stage2Worker: ODL parse succeeded for %s/%s", job_id, file_id)
            except Exception as odl_err:
                logger.warning("Stage2Worker: ODL fallback skipped/failed for %s/%s: %s", job_id, file_id, odl_err)

        # Step 2: Nova LLM Fallback if critical fields missing
        has_name = bool(fields.get("name"))
        has_skills = bool(fields.get("skills"))
        has_exp = bool(fields.get("experience"))
        low_confidence = False
        fallback_reason = None

        if not (has_name and (has_skills or has_exp)):
            # Check LLM budget per job
            all_files = files_repo.list_files_for_job(job_id)
            llm_used_count = sum(1 for f in all_files if f.needs_fallback and f.status == FileStatus.S2_DONE and not f.low_confidence_extraction)

            if llm_used_count >= LLM_FALLBACK_MAX_PER_JOB:
                logger.warning("Stage2Worker: Job %s hit LLM_FALLBACK_MAX_PER_JOB (%d), skipping LLM for %s",
                               job_id, LLM_FALLBACK_MAX_PER_JOB, file_id)
                low_confidence = True
                fallback_reason = "JOB_LLM_CAP_REACHED"
            elif not files_repo.check_and_increment_daily_llm_cap():
                logger.warning("Stage2Worker: Global daily LLM cap reached, skipping LLM for %s/%s", job_id, file_id)
                low_confidence = True
                fallback_reason = "GLOBAL_DAILY_LLM_CAP_REACHED"
            else:
                logger.info("Stage2Worker: Invoking Nova LLM fallback for %s/%s (job LLM count: %d/%d)",
                            job_id, file_id, llm_used_count, LLM_FALLBACK_MAX_PER_JOB)
                try:
                    nova = NovaService()
                    # Reconstruct text chunk for Nova
                    chunks = unresolved if unresolved else [json.dumps(fields)]
                    nova_fields = nova.resolve_chunks(chunks, existing_fields=fields)
                    for k, v in nova_fields.items():
                        if v and not fields.get(k):
                            fields[k] = v
                    logger.info("Stage2Worker: Nova completed fallback for %s/%s", job_id, file_id)
                except ClientError as ce:
                    error_code = ce.response.get("Error", {}).get("Code", "")
                    if error_code in ("ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException"):
                        logger.warning("Stage2Worker: Bedrock throttled for %s/%s (retryable): %s", job_id, file_id, ce)
                        # Re-raise so SQS message will back off and retry up to maxReceiveCount
                        raise RetryableThrottlingError(f"Bedrock throttled: {ce}") from ce
                    else:
                        logger.warning("Stage2Worker: Nova ClientError for %s/%s: %s", job_id, file_id, ce)
                        low_confidence = True
                        fallback_reason = f"NOVA_CLIENT_ERROR: {error_code}"
                except Exception as ne:
                    logger.warning("Stage2Worker: Nova fallback failed for %s/%s: %s", job_id, file_id, ne)
                    low_confidence = True
                    fallback_reason = f"NOVA_EXCEPTION: {str(ne)[:80]}"

        # Propagate low confidence flag into stage2 payload
        fields["low_confidence_extraction"] = low_confidence
        if fallback_reason:
            fields["fallback_reason"] = fallback_reason

        # Upload final structured JSON to stage2/
        s3_stage2_key = storage.upload_stage2_json(job_id, file_id, fields)

        # Idempotently transition to S2_DONE (terminal, decrements job.remaining)
        candidate_name = fields.get("name") or "Candidate"
        files_repo.transition_file_terminal(
            job_id=job_id,
            file_id=file_id,
            terminal_status=FileStatus.S2_DONE.value,
            candidate_name=candidate_name,
            s3_extracted_key=s3_stage2_key,
            low_confidence_extraction=low_confidence,
            fallback_reason=fallback_reason,
        )
        logger.info("Stage2Worker: completed fallback for %s/%s -> S2_DONE (low_conf=%s)",
                    job_id, file_id, low_confidence)
        return True

    except RetryableThrottlingError:
        # Re-raise to trigger SQS retry
        raise
    except Exception as exc:
        logger.error("Stage2Worker: unrecoverable failure for %s/%s: %s", job_id, file_id, exc, exc_info=True)
        # Idempotently transition to S2_FAILED (terminal, decrements job.remaining)
        files_repo.transition_file_terminal(
            job_id=job_id,
            file_id=file_id,
            terminal_status=FileStatus.S2_FAILED.value,
            error_message=str(exc),
        )
        return False
