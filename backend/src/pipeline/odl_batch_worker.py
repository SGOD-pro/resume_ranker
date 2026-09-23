"""
odl_batch_worker.py — Bounded ODL batch fallback worker
========================================================
Consumes messages from ODL_BATCH_QUEUE. Runs the ODL JVM/remote parser for
complex/multi-column documents in bounded batches using parse_pdf_batch,
persists updated artifacts, re-evaluates extraction quality, and routes
unresolved critical fields to NEEDS_NOVA.
"""

import logging
import os
import tempfile
import time
from typing import Dict, List, Optional

from src.config.aws import get_settings
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    BatchDoc,
    ParseResult,
    StructuralParsingService,
)
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import ODL_BATCH_QUEUE, get_queue_adapter
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.storage.storage_service import StorageService
from src.pipeline.coordinator import check_and_progress_fallback

logger = logging.getLogger(__name__)


def process_odl_batch_message(message: QueueMessage) -> None:
    """Process a bounded batch of documents requiring ODL fallback."""
    docs_repo = DocumentsRepository()
    storage = StorageService()
    queue_adapter = get_queue_adapter()
    structural_service = StructuralParsingService()
    markdown_service = MarkdownExtractionService()
    settings = get_settings()

    job_id = message.job_id
    session_id = message.session_id
    document_ids = message.document_ids or ([message.document_id] if message.document_id else [])

    logger.info("OdlBatchWorker: Processing batch of %d documents for job %s session %s", len(document_ids), job_id, session_id)

    # 1. Load candidate documents
    valid_docs: List[DocumentItem] = []
    for doc_id in document_ids:
        doc = docs_repo.get(job_id, doc_id)
        if not doc:
            continue
        # Idempotency guard: Only process if ODL_QUEUED or NEEDS_ODL
        if doc.status not in (DocumentStatus.ODL_QUEUED, DocumentStatus.NEEDS_ODL):
            logger.info("OdlBatchWorker: Doc %s is in state %s, skipping", doc_id, doc.status.value)
            continue
        # Transition document to ODL_PARSING
        updated = docs_repo.update_status_conditional(
            job_id=job_id,
            document_id=doc_id,
            new_status=DocumentStatus.ODL_PARSING,
            allowed_current_statuses=[DocumentStatus.ODL_QUEUED, DocumentStatus.NEEDS_ODL],
        )
        if updated:
            valid_docs.append(updated)

    if not valid_docs:
        logger.info("OdlBatchWorker: No valid documents to process for message %s", message.event_id)
        if message.receipt_handle:
            queue_adapter.delete_message(ODL_BATCH_QUEUE, message.receipt_handle)
        check_and_progress_fallback(job_id, session_id)
        return

    tmp_files: Dict[str, str] = {}  # doc_id -> tmp_path
    total_bytes = 0
    t_start = time.time()
    successful_count = 0
    failed_count = 0

    try:
        # 2. Download batch PDFs to temporary files with tracking
        for doc in valid_docs:
            pdf_bytes = storage.get_resume(job_id, doc.document_id, s3_key=doc.s3_pdf_key)
            total_bytes += len(pdf_bytes)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_files[doc.document_id] = tmp.name

        # 3. Build BatchDoc descriptors
        batch_descriptors = [
            BatchDoc(
                document_id=doc.document_id,
                pdf_path=tmp_files[doc.document_id],
                s3_bucket=settings.s3_bucket_name,
                s3_key=doc.s3_pdf_key,
                save_images=False,
                force_odl=True,
            )
            for doc in valid_docs
        ]

        # 4. Invoke single batched ODL parse call
        parse_results: List[ParseResult] = structural_service.parse_pdf_batch(batch_descriptors)

        # 5. Process and attribute per-document results
        for doc, parse_result in zip(valid_docs, parse_results):
            doc_id = doc.document_id
            try:
                if parse_result.error_reason:
                    failed_count += 1
                    logger.warning("OdlBatchWorker: Document %s had error in ODL batch: %s", doc_id, parse_result.error_reason)
                    docs_repo.update_status_conditional(
                        job_id=job_id,
                        document_id=doc_id,
                        new_status=DocumentStatus.REVIEW_REQUIRED,
                        allowed_current_statuses=[DocumentStatus.ODL_PARSING],
                        extra_updates={"error_reason": f"ODL parse error: {parse_result.error_reason}"},
                    )
                    continue

                # Markdown extraction pass
                t_det_0 = time.time()
                md_result = markdown_service.extract(
                    parse_result.markdown,
                    parse_result.hyperlinks,
                    parse_result.elements,
                    pymupdf_markdown=parse_result.pymupdf_text,
                )
                t_det_1 = time.time()

                fields = md_result.get("fields", {})
                unresolved_chunks = md_result.get("unresolved_chunks", [])
                candidate_name = fields.get("name")
                identity_data = fields.get("identity") or {}
                if isinstance(identity_data, dict):
                    identity_status = identity_data.get("status", "UNRESOLVED")
                    identity_confidence = identity_data.get("confidence", 0.0)
                else:
                    identity_status = getattr(identity_data, "status", "UNRESOLVED")
                    identity_confidence = getattr(identity_data, "confidence", 0.0)
                if hasattr(identity_status, "value"):
                    identity_status = identity_status.value

                timings = {
                    "deterministic_ms": round((t_det_1 - t_det_0) * 1000, 2),
                    "nova_ms": 0.0,
                    "total_ms": round((time.time() - t_start) * 1000, 2),
                }
                fields["_timings"] = timings
                fields["_document_id"] = doc_id
                fields["extraction_quality"] = parse_result.quality_score
                fields["elements"] = parse_result.elements

                # Check if Nova LLM fallback is needed
                is_unresolved_name = (
                    not candidate_name
                    or str(candidate_name).strip() in ("", "Name needs review", "Unknown")
                    or identity_status == "UNRESOLVED"
                )
                is_missing_experience = not fields.get("experience") or len(fields.get("experience")) == 0
                has_unresolved_critical = bool(unresolved_chunks) or is_unresolved_name or is_missing_experience or not fields.get("skills")
                enable_nova = os.environ.get("ENABLE_NOVA", "true").lower() in ("true", "1", "yes")

                if has_unresolved_critical and enable_nova:
                    target_status = DocumentStatus.NEEDS_NOVA
                    reasons = []
                    if is_unresolved_name:
                        reasons.append("candidate name unresolved")
                    if is_missing_experience:
                        reasons.append("experience records not found")
                    if not fields.get("skills"):
                        reasons.append("skills not found")
                    fallback_reason = f"Unresolved critical fields ({', '.join(reasons)}) after PyMuPDF + ODL; queued for LLM fallback infill"
                    fields["unresolved_chunks"] = unresolved_chunks or [parse_result.markdown[:4000]]
                    fields["raw_text"] = parse_result.markdown[:4000]
                    fields["fallback_reason"] = fallback_reason
                else:
                    fallback_reason = None
                    if identity_status in ("VERIFIED", "PLAUSIBLE") and parse_result.quality_score >= 0.70:
                        target_status = DocumentStatus.STRUCTURED_PARSED
                    else:
                        target_status = DocumentStatus.REVIEW_REQUIRED

                # Persist extraction JSON to S3
                s3_extracted_key = storage.upload_extracted_json(job_id, doc_id, fields)

                # Update DynamoDB
                docs_repo.update_status_conditional(
                    job_id=job_id,
                    document_id=doc_id,
                    new_status=target_status,
                    allowed_current_statuses=[DocumentStatus.ODL_PARSING],
                    extra_updates={
                        "candidate_name": candidate_name or "Name needs review",
                        "identity_status": identity_status,
                        "identity_confidence": identity_confidence,
                        "extraction_quality": parse_result.quality_score,
                        "s3_extracted_key": s3_extracted_key,
                        "fallback_reason": fallback_reason,
                    },
                )
                successful_count += 1
                logger.info("OdlBatchWorker: Doc %s completed ODL pass -> %s", doc_id, target_status.value)

            except Exception as doc_exc:
                failed_count += 1
                logger.error("OdlBatchWorker: Exception processing doc %s: %s", doc_id, doc_exc, exc_info=True)
                docs_repo.update_status_conditional(
                    job_id=job_id,
                    document_id=doc_id,
                    new_status=DocumentStatus.REVIEW_REQUIRED,
                    allowed_current_statuses=[DocumentStatus.ODL_PARSING],
                    extra_updates={"error_reason": f"Post-ODL processing error: {str(doc_exc)}"},
                )

    except Exception as batch_exc:
        logger.error("OdlBatchWorker: Entire batch execution failed: %s", batch_exc, exc_info=True)
        # Update remaining docs to REVIEW_REQUIRED so they don't hang in ODL_PARSING
        for doc in valid_docs:
            try:
                docs_repo.update_status_conditional(
                    job_id=job_id,
                    document_id=doc.document_id,
                    new_status=DocumentStatus.REVIEW_REQUIRED,
                    allowed_current_statuses=[DocumentStatus.ODL_PARSING],
                    extra_updates={"error_reason": f"ODL batch failure: {str(batch_exc)}"},
                )
            except Exception:
                pass
    finally:
        # 6. Delete all temporary files
        for tmp_p in tmp_files.values():
            try:
                os.unlink(tmp_p)
            except OSError:
                pass

        duration_ms = round((time.time() - t_start) * 1000, 2)
        fallback_rate = round(successful_count / max(1, len(valid_docs)), 2)

        # Log metrics
        logger.info(
            "ODL Batch Metrics: batch_doc_count=%d, batch_total_bytes=%d, duration_ms=%.2f, "
            "successful=%d, failed=%d, fallback_rate=%.2f",
            len(valid_docs), total_bytes, duration_ms, successful_count, failed_count, fallback_rate
        )

        # 7. Acknowledge and delete message from queue
        if message.receipt_handle:
            queue_adapter.delete_message(ODL_BATCH_QUEUE, message.receipt_handle)

        # 8. Recheck fallback barrier
        check_and_progress_fallback(job_id, session_id)
