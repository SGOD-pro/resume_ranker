"""
odl_batch_worker.py — Bounded ODL batch fallback worker
========================================================
Consumes messages from ODL_BATCH_QUEUE. Runs the ODL JVM/remote parser for
complex/multi-column documents, persists updated artifacts, re-evaluates
extraction quality, and routes unresolved critical fields to NEEDS_NOVA.
"""

import logging
import os
import tempfile
import time
from typing import List

from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import StructuralParsingService
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

    job_id = message.job_id
    session_id = message.session_id
    document_ids = message.document_ids or ([message.document_id] if message.document_id else [])

    logger.info("OdlBatchWorker: Processing %d documents for job %s session %s", len(document_ids), job_id, session_id)

    for doc_id in document_ids:
        doc = docs_repo.get(job_id, doc_id)
        if not doc:
            continue

        # Idempotency guard: Only process if ODL_QUEUED or NEEDS_ODL
        if doc.status not in (DocumentStatus.ODL_QUEUED, DocumentStatus.NEEDS_ODL):
            logger.info("OdlBatchWorker: Doc %s is in state %s, skipping", doc_id, doc.status.value)
            continue

        # Conditionally transition to ODL_PARSING
        updated_doc = docs_repo.update_status_conditional(
            job_id=job_id,
            document_id=doc_id,
            new_status=DocumentStatus.ODL_PARSING,
            allowed_current_statuses=[DocumentStatus.ODL_QUEUED, DocumentStatus.NEEDS_ODL],
        )
        if not updated_doc:
            continue

        tmp_path = None
        try:
            # 1. Download PDF
            t0 = time.time()
            pdf_bytes = storage.get_resume(job_id, doc_id, s3_key=doc.s3_pdf_key)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            # 2. Run structural parse (forces ODL via fallback)
            from src.config.aws import get_settings
            settings = get_settings()
            parse_result = structural_service.parse_pdf(
                tmp_path,
                doc_id,
                settings.s3_bucket_name,
                doc.s3_pdf_key,
            )

            # 3. Deterministic markdown extraction pass
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

            # Update timings
            t_end = time.time()
            timings = {
                "structure_ms": round((t_det_0 - t0) * 1000, 2),
                "deterministic_ms": round((t_det_1 - t_det_0) * 1000, 2),
                "nova_ms": 0.0,
                "total_ms": round((t_end - t0) * 1000, 2),
            }
            fields["_timings"] = timings
            fields["_document_id"] = doc_id
            fields["extraction_quality"] = parse_result.quality_score
            fields["elements"] = parse_result.elements

            # 4. Check if Nova LLM fallback is needed for unresolved critical fields
            has_unresolved_critical = bool(unresolved_chunks) or not fields.get("skills") or not candidate_name
            enable_nova = os.environ.get("ENABLE_NOVA", "false").lower() in ("true", "1", "yes")

            if has_unresolved_critical and enable_nova:
                target_status = DocumentStatus.NEEDS_NOVA
                fallback_reason = "Unresolved critical fields after PyMuPDF + ODL; queued for Nova Lite"
                fields["unresolved_chunks"] = unresolved_chunks
            else:
                fallback_reason = None
                if identity_status in ("VERIFIED", "PLAUSIBLE") and parse_result.quality_score >= 0.70:
                    target_status = DocumentStatus.STRUCTURED_PARSED
                else:
                    target_status = DocumentStatus.REVIEW_REQUIRED

            # 5. Persist updated extraction JSON to S3
            s3_extracted_key = storage.upload_extracted_json(job_id, doc_id, fields)

            # 6. Update DynamoDB
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
            logger.info("OdlBatchWorker: Doc %s completed ODL pass -> %s", doc_id, target_status.value)

        except Exception as e:
            logger.error("OdlBatchWorker: Failed ODL parsing for doc %s: %s", doc_id, e, exc_info=True)
            try:
                docs_repo.update_status_conditional(
                    job_id=job_id,
                    document_id=doc_id,
                    new_status=DocumentStatus.REVIEW_REQUIRED,
                    allowed_current_statuses=[DocumentStatus.ODL_PARSING],
                    extra_updates={"error_reason": f"ODL parse error: {str(e)}"},
                )
            except Exception:
                pass

        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # Acknowledge / delete message from queue
    if message.receipt_handle:
        queue_adapter.delete_message(ODL_BATCH_QUEUE, message.receipt_handle)

    # Recheck fallback barrier
    check_and_progress_fallback(job_id, session_id)
