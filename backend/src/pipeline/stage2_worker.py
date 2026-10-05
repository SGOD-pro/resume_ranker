"""
stage2_worker.py — Fallback extraction worker (Stage 2: ODL & Nova LLM)
======================================================================
Triggered by messages from STAGE2_QUEUE / ODL_BATCH_QUEUE after Analyze request.
Implements Phase 1.6 Concurrency, Durability & Batching Requirements:
- Worker lease claims before processing to prevent duplicate executions.
- Real bounded ODL microbatching: up to 20 documents per actual ODL invocation.
- Resource budgets: bounded document count and byte limits per microbatch.
- Reliable tail flushing: executes immediately for smaller batches; no indefinite wait.
- Partial failure isolation: successful documents are retained; only unresolved fail.
- Atomic per-job LLM budget reservation before Bedrock calls.
- Typed retryable throttling: propagates NovaThrottlingError as RetryableThrottlingError to SQS.
- Bias-free field merging: never selects fields merely because string is longer; preserves candidate identity.
- Atomic terminal accounting via DynamoDB TransactWriteItems.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from botocore.exceptions import ClientError

from src.config.aws import get_settings
from src.extraction.fallback.nova_service import (
    NovaProviderError,
    NovaQuotaExceededError,
    NovaService,
    NovaThrottlingError,
)
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.odl_client import DocDescriptor, ODLParseError, parse_batch
from src.infrastructure.models.file import FileStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.storage.storage_service import StorageService

logger = logging.getLogger(__name__)

LLM_FALLBACK_MAX_PER_JOB = 5
MAX_ODL_MICROBATCH_SIZE = 20
MAX_ODL_BYTE_BUDGET = 20 * 1024 * 1024  # 20 MB max per ODL batch


class RetryableThrottlingError(Exception):
    """Raised on Bedrock / AWS throttling so SQS retries via backoff."""
    pass


def merge_extracted_fields(
    base_fields: Dict[str, Any],
    fallback_fields: Dict[str, Any],
    source_name: str,
) -> Dict[str, Any]:
    """Merge fallback fields into base fields without string-length bias.
    
    Principles (Phase 1.6 / B.7):
    - Do NOT select extracted fields merely because their string is longer.
    - Preserve validated candidate identity from deterministic stage 1.
    - Combine skills without dropping existing detected skills.
    - Fill null/empty experience and education from fallback.
    """
    merged = dict(base_fields)

    # 1. Candidate Name: Preserve base name if already resolved with confidence
    base_name = (base_fields.get("name") or "").strip()
    fallback_name = (fallback_fields.get("name") or "").strip()
    if not base_name and fallback_name:
        merged["name"] = fallback_name
        logger.info("Merged %s candidate name: %s", source_name, fallback_name)

    # 2. Skills: Merge distinct skills
    base_skills = base_fields.get("skills") or []
    fallback_skills = fallback_fields.get("skills") or []
    if isinstance(base_skills, str):
        base_skills = [s.strip() for s in base_skills.split(",") if s.strip()]
    if isinstance(fallback_skills, str):
        fallback_skills = [s.strip() for s in fallback_skills.split(",") if s.strip()]
    combined_skills = list(dict.fromkeys(list(base_skills) + list(fallback_skills)))
    if combined_skills:
        merged["skills"] = combined_skills

    # 3. Experience: Fill if base has no structured experience
    if not base_fields.get("experience") and fallback_fields.get("experience"):
        merged["experience"] = fallback_fields["experience"]

    # 4. Education: Fill if base has no education
    if not base_fields.get("education") and fallback_fields.get("education"):
        merged["education"] = fallback_fields["education"]

    # 5. Contact fields: Fill if missing
    for contact_key in ("email", "phone", "linkedin", "github"):
        if not base_fields.get(contact_key) and fallback_fields.get(contact_key):
            merged[contact_key] = fallback_fields[contact_key]

    return merged


def _extract_job_file_id(message: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract (job_id, file_id) from message object or dict."""
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

    return job_id, file_id


def _extract_msg_id(msg: Any, fallback: str) -> str:
    """Extract originating SQS messageId or receiptHandle, supporting dicts and models."""
    if isinstance(msg, dict):
        return (
            msg.get("messageId")
            or msg.get("message_id")
            or msg.get("receiptHandle")
            or msg.get("receipt_handle")
            or fallback
        )
    return (
        getattr(msg, "message_id", None)
        or getattr(msg, "messageId", None)
        or getattr(msg, "receipt_handle", None)
        or getattr(msg, "event_id", None)
        or fallback
    )


def process_stage2_batch(messages: List[Any]) -> Dict[str, Any]:
    """Process a bounded batch of Stage 2 fallback messages with real ODL microbatching.
    
    Supports SQS multi-record payloads and single-record invocations.
    Returns summary dict with processed count, succeeded, and failed item identifiers.
    """
    if not messages:
        return {"processed": 0, "succeeded": 0, "failed_items": []}

    files_repo = FilesRepository()
    storage = StorageService()
    worker_id = f"stage2-{uuid.uuid4().hex[:8]}"

    # Step 1: Parse and validate candidates, acquire worker lease claims
    eligible_docs = []  # list of dicts with file context
    failed_items = []
    throttled_items = []

    for msg in messages:
        job_id, file_id = _extract_job_file_id(msg)
        msg_id = _extract_msg_id(msg, file_id or "")

        if not job_id or not file_id:
            logger.error("Stage2Worker: invalid message without job_id/file_id: %s", msg)
            if msg_id:
                failed_items.append(msg_id)
            continue

        file_item = files_repo.get_file(job_id, file_id)
        if not file_item:
            from src.infrastructure.repositories.documents_repository import DocumentsRepository
            from src.infrastructure.models.file import FileItem
            docs_repo = DocumentsRepository()
            doc = docs_repo.get(job_id, file_id)
            if doc:
                file_item = FileItem(
                    job_id=job_id,
                    file_id=file_id,
                    filename=doc.filename,
                    file_size=doc.file_size,
                    status=FileStatus.S1_DONE,
                    s3_raw_key=doc.s3_pdf_key or f"jobs/{job_id}/raw/{file_id}.pdf",
                )
                files_repo.create_files(job_id, [file_item])
                logger.info("Stage2Worker: Materialized FileItem from DocumentItem for %s/%s", job_id, file_id)
            else:
                logger.error("Stage2Worker: Neither FileItem nor DocumentItem found for %s/%s", job_id, file_id)
                failed_items.append(msg_id)
                continue

        if file_item and file_item.is_terminal:
            logger.info("Stage2Worker: file %s/%s already terminal (%s), skipping", job_id, file_id, file_item.status)
            continue

        # Claim file with lease
        claimed = files_repo.claim_file(
            job_id=job_id,
            file_id=file_id,
            worker_id=worker_id,
            lease_seconds=180,
            processing_status=FileStatus.S2_PROCESSING.value,
        )
        if not claimed:
            latest = files_repo.get_file(job_id, file_id)
            if latest and latest.is_terminal:
                logger.info("Stage2Worker: file %s/%s already terminal (%s), skipping", job_id, file_id, latest.status)
                continue
            logger.warning("Stage2Worker: file %s/%s could not be claimed by %s (active lease exists), reporting failed for retry",
                           job_id, file_id, worker_id)
            failed_items.append(msg_id)
            continue

        try:
            stage1_data = storage.get_stage1_json(job_id, file_id)
        except Exception as e:
            try:
                extracted = storage.get_extracted_json(job_id, file_id)
                stage1_data = {
                    "fields": extracted,
                    "quality": {"layout_quality": extracted.get("extraction_quality", 0.8)},
                    "unresolved_chunks": extracted.get("unresolved_chunks", []),
                    "file_size": file_item.file_size if file_item else 0,
                }
            except Exception:
                logger.error("Stage2Worker: failed to load Stage 1 JSON for %s/%s: %s", job_id, file_id, e)
                files_repo.transition_file_terminal(
                    job_id=job_id,
                    file_id=file_id,
                    terminal_status=FileStatus.S2_FAILED.value,
                    error_message=f"Missing stage1 artifact: {e}",
                )
                continue

        raw_s3_key = (file_item.s3_raw_key if file_item and file_item.s3_raw_key else None) or f"jobs/{job_id}/raw/{file_id}.pdf"
        file_size = getattr(file_item, "file_size", 0) or stage1_data.get("file_size", 0)
        # Register document into durable ODL collector
        try:
            files_repo.add_to_odl_collector(job_id, file_id, raw_s3_key, file_size)
        except Exception as coll_err:
            logger.warning("Stage2Worker: Failed to buffer to ODL collector for %s/%s: %s", job_id, file_id, coll_err)

        eligible_docs.append({
            "job_id": job_id,
            "file_id": file_id,
            "msg_id": msg_id,
            "raw_s3_key": raw_s3_key,
            "stage1_data": stage1_data,
            "fields": stage1_data.get("fields", {}),
            "quality": stage1_data.get("quality", {}),
            "unresolved": stage1_data.get("unresolved_chunks", []),
            "file_size": file_size,
        })

    # Assemble any previously buffered documents from the durable collector across separate invocations
    discovered_job_ids = {d["job_id"] for d in eligible_docs}
    for jid in discovered_job_ids:
        try:
            buffered = files_repo.get_odl_collector_items(jid)
            for b_item in buffered:
                b_fid = b_item["file_id"]
                if not any(d["file_id"] == b_fid for d in eligible_docs):
                    b_file = files_repo.get_file(jid, b_fid)
                    if b_file and not b_file.is_terminal:
                        try:
                            b_s1 = storage.get_stage1_json(jid, b_fid)
                            eligible_docs.append({
                                "job_id": jid,
                                "file_id": b_fid,
                                "msg_id": b_fid,
                                "raw_s3_key": b_item.get("s3_key") or b_file.s3_raw_key,
                                "stage1_data": b_s1,
                                "fields": b_s1.get("fields", {}),
                                "quality": b_s1.get("quality", {}),
                                "unresolved": b_s1.get("unresolved_chunks", []),
                                "file_size": b_item.get("file_size", 0),
                            })
                        except Exception as b_err:
                            logger.warning("Stage2Worker: Could not load stage1 for buffered doc %s: %s", b_fid, b_err)
        except Exception as coll_err:
            logger.warning("Stage2Worker: Failed to query ODL collector for job %s: %s", jid, coll_err)

    if not eligible_docs:
        return {"processed": 0, "succeeded": 0, "failed_items": []}

    # Step 2: Separate documents needing ODL vs documents that can proceed directly to Nova/Done
    odl_candidates = []
    for doc in eligible_docs:
        q = doc["quality"]
        if q.get("score", 1.0) < 0.90 or q.get("looks_tabular", False):
            odl_candidates.append(doc)

    # Step 3: Execute real bounded ODL microbatches (up to 20 documents AND 20 MB budget)
    if odl_candidates:
        logger.info(
            "Stage2Worker: %d/%d documents require ODL fallback. Microbatching up to %d documents and %d bytes per call...",
            len(odl_candidates), len(eligible_docs), MAX_ODL_MICROBATCH_SIZE, MAX_ODL_BYTE_BUDGET
        )

        # Partition into microbatches enforcing BOTH max 20 documents AND max 20 MB cumulative payload
        microbatches: List[List[Dict[str, Any]]] = []
        current_chunk: List[Dict[str, Any]] = []
        current_bytes = 0

        for doc in odl_candidates:
            doc_size = doc.get("file_size") or 0
            if doc_size <= 0:
                # Require verified size before dispatch: retry HeadObject up to 3 times
                for attempt in range(3):
                    try:
                        head = storage._client.head_object(Bucket=storage._bucket, Key=doc["raw_s3_key"])
                        doc_size = int(head.get("ContentLength", 0))
                        if doc_size > 0:
                            break
                    except Exception as h_err:
                        if attempt == 2:
                            logger.error("Stage2Worker: HeadObject failed for %s/%s after 3 attempts: %s",
                                         doc["job_id"], doc["file_id"], h_err)
                        time.sleep(0.05 * (attempt + 1))

            if doc_size <= 0:
                # Size could not be verified; do NOT fail open with 0 bytes!
                logger.warning("Stage2Worker: Size unverified for %s/%s; retrying message via SQS",
                               doc["job_id"], doc["file_id"])
                if doc.get("msg_id"):
                    failed_items.append(doc["msg_id"])
                continue

            doc["file_size"] = doc_size

            # Explicitly handle individually oversized documents
            if doc_size > MAX_ODL_BYTE_BUDGET:
                logger.warning(
                    "Stage2Worker: Document %s/%s size %d bytes exceeds MAX_ODL_BYTE_BUDGET %d; bypassing ODL to Nova fallback",
                    doc["job_id"], doc["file_id"], doc_size, MAX_ODL_BYTE_BUDGET
                )
                doc["fallback_reason"] = "EXCEEDS_ODL_BYTE_BUDGET"
                continue

            if current_chunk and (
                len(current_chunk) >= MAX_ODL_MICROBATCH_SIZE
                or (current_bytes + doc_size > MAX_ODL_BYTE_BUDGET)
            ):
                microbatches.append(current_chunk)
                current_chunk = [doc]
                current_bytes = doc_size
            else:
                current_chunk.append(doc)
                current_bytes += doc_size

        if current_chunk:
            microbatches.append(current_chunk)

        for batch_idx, chunk in enumerate(microbatches):
            descriptors = [
                DocDescriptor(
                    document_id=d["file_id"],
                    s3_bucket=storage._bucket,
                    s3_key=d["raw_s3_key"],
                )
                for d in chunk
            ]
            batch_bytes = sum(d.get("file_size", 0) for d in chunk)
            logger.info(
                "|ODL-PARSER| [Job: %s] Processing batch of %d files (total %d bytes, microbatch %d/%d)",
                chunk[0]["job_id"], len(descriptors), batch_bytes, batch_idx + 1, len(microbatches)
            )

            try:
                batch_res = parse_batch(descriptors)

                # Process results with partial failure isolation
                for d in chunk:
                    fid = d["file_id"]
                    if fid in batch_res.results:
                        odl_res = batch_res.results[fid]
                        try:
                            odl_extracted = MarkdownExtractionService().extract(odl_res.markdown)
                            odl_fields = odl_extracted.get("fields", {})
                            d["fields"] = merge_extracted_fields(d["fields"], odl_fields, "ODL")
                            d["unresolved"] = odl_extracted.get("unresolved_chunks", [])
                            logger.info("|ODL-PARSER| [Job: %s, File: %s] ODL extraction succeeded for candidate='%s'", d["job_id"], fid, d["fields"].get("name"))
                        except Exception as parse_e:
                            logger.warning(
                                "Stage2Worker: Markdown extraction error on ODL result for %s/%s: %s",
                                d["job_id"], fid, parse_e
                            )
                    elif fid in batch_res.failed:
                        odl_err = batch_res.failed[fid]
                        logger.warning(
                            "Stage2Worker: ODL parse failed for %s/%s (isolated): %s",
                            d["job_id"], fid, odl_err
                        )
                        # Retain document for subsequent Nova fallback or error handling
            except Exception as odl_batch_exc:
                logger.error("Stage2Worker: ODL parse_batch invocation failed: %s", odl_batch_exc)
            finally:
                for d in chunk:
                    try:
                        files_repo.remove_from_odl_collector(d["job_id"], [d["file_id"]])
                    except Exception as coll_err:
                        logger.warning("Stage2Worker: Failed to remove from ODL collector: %s", coll_err)

    # Step 4: Per-document LLM fallback with atomic per-job reservation
    succeeded_count = 0

    for doc in eligible_docs:
        job_id = doc["job_id"]
        file_id = doc["file_id"]
        fields = doc["fields"]
        unresolved = doc["unresolved"]

        has_name = bool(fields.get("name")) and str(fields.get("name")).strip().lower() not in ("candidate", "unknown", "")
        has_skills = bool(fields.get("skills"))
        has_exp = bool(fields.get("experience")) and len(fields.get("experience")) > 0
        low_confidence = False
        fallback_reason = None

        if not (has_name and has_exp and has_skills):
            # Atomically reserve per-job LLM budget slot
            allowed, cap_reason = files_repo.reserve_llm_slot(
                job_id=job_id,
                file_id=file_id,
                attempt_id=worker_id,
                max_per_job=LLM_FALLBACK_MAX_PER_JOB,
            )

            if not allowed:
                logger.warning("Stage2Worker: LLM fallback slot denied for %s/%s: %s", job_id, file_id, cap_reason)
                low_confidence = True
                fallback_reason = cap_reason
            else:
                logger.info(
                    "|LLM| [Job: %s, File: %s] Triggering Nova fallback for missing/unresolved fields (has_name=%s, has_exp=%s, has_skills=%s)",
                    job_id, file_id, has_name, has_exp, has_skills
                )
                try:
                    nova = NovaService()
                    raw_resume_text = doc.get("stage1_data", {}).get("raw_text")
                    chunks = unresolved if unresolved else ([raw_resume_text] if raw_resume_text else [json.dumps(fields)])
                    nova_fields = nova.resolve_chunks(chunks, existing_fields=fields)
                    doc["fields"] = merge_extracted_fields(fields, nova_fields, "Nova")
                    fields = doc["fields"]
                    logger.info("|LLM| [Job: %s, File: %s] Nova fallback completed successfully. Resolved candidate='%s'",
                                job_id, file_id, fields.get("name"))
                except NovaThrottlingError as nte:
                    logger.warning("Stage2Worker: Nova throttled for %s/%s (retryable): %s", job_id, file_id, nte)
                    if doc.get("msg_id"):
                        failed_items.append(doc["msg_id"])
                        throttled_items.append(doc["msg_id"])
                    try:
                        files_repo.update_file_non_terminal(job_id, file_id, FileStatus.S1_DONE)
                    except Exception:
                        pass
                    continue
                except NovaQuotaExceededError as qe:
                    logger.warning("Stage2Worker: Nova quota exceeded for %s/%s: %s", job_id, file_id, qe)
                    low_confidence = True
                    fallback_reason = "NOVA_QUOTA_EXCEEDED"
                except ClientError as ce:
                    error_code = ce.response.get("Error", {}).get("Code", "")
                    if error_code in ("ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException"):
                        logger.warning("Stage2Worker: Bedrock throttled for %s/%s (retryable): %s", job_id, file_id, ce)
                        if doc.get("msg_id"):
                            failed_items.append(doc["msg_id"])
                            throttled_items.append(doc["msg_id"])
                        try:
                            files_repo.update_file_non_terminal(job_id, file_id, FileStatus.S1_DONE)
                        except Exception:
                            pass
                        continue
                    else:
                        logger.warning("Stage2Worker: Nova ClientError for %s/%s: %s", job_id, file_id, ce)
                        low_confidence = True
                        fallback_reason = f"NOVA_CLIENT_ERROR: {error_code}"
                except Exception as ne:
                    logger.warning("Stage2Worker: Nova fallback error for %s/%s: %s", job_id, file_id, ne)
                    low_confidence = True
                    fallback_reason = f"NOVA_EXCEPTION: {str(ne)[:80]}"

        if doc.get("msg_id") and doc["msg_id"] in failed_items:
            # Skip terminal transition for retryable failures; SQS will redrive this message
            continue


        # Propagate low-confidence flag and fallback reason
        fields["low_confidence_extraction"] = low_confidence
        if fallback_reason:
            fields["fallback_reason"] = fallback_reason

        fields["document_id"] = file_id
        fields["file_id"] = file_id
        fields["job_id"] = job_id

        # Upload final structured JSON to stage2/
        try:
            s3_stage2_key = storage.upload_stage2_json(job_id, file_id, fields)
            candidate_name = fields.get("name") or "Candidate"

            # Atomically transition to S2_DONE (terminal, decrements job.remaining)
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
            succeeded_count += 1
        except Exception as term_exc:
            logger.error("Stage2Worker: failure completing %s/%s: %s", job_id, file_id, term_exc, exc_info=True)
            files_repo.transition_file_terminal(
                job_id=job_id,
                file_id=file_id,
                terminal_status=FileStatus.S2_FAILED.value,
                error_message=str(term_exc),
            )

    # Always ensure processed documents are removed from ODL buffer
    for doc in eligible_docs:
        try:
            files_repo.remove_from_odl_collector(doc["job_id"], [doc["file_id"]])
        except Exception:
            pass

    return {
        "processed": len(eligible_docs),
        "succeeded": succeeded_count,
        "failed_items": failed_items,
        "throttled_items": throttled_items,
    }


def process_stage2_message(message: Any) -> bool:
    """Process a single Stage 2 fallback message (backward compatibility)."""
    res = process_stage2_batch([message])
    if res.get("throttled_items"):
        raise RetryableThrottlingError(f"Bedrock Nova throttled for {res['throttled_items']}")
    return res["succeeded"] > 0 or res["processed"] == 0
