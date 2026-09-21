"""
nova_queue_worker.py — Bedrock Nova Lite LLM fallback worker
============================================================
Consumes messages from NOVA_QUEUE. Infill missing critical fields only.
Preserves source provenance, enforces circuit-breaker / timeout behavior,
and marks unresolved documents as REVIEW_REQUIRED, never fabricated.
"""

import logging
import time

from src.extraction.fallback.nova_service import NovaService
from src.infrastructure.models.document import DocumentStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import NOVA_QUEUE, get_queue_adapter
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.storage.storage_service import StorageService
from src.pipeline.coordinator import check_and_progress_fallback

logger = logging.getLogger(__name__)


def process_nova_message(message: QueueMessage) -> None:
    """Execute Nova Lite fallback for one queue message."""
    docs_repo = DocumentsRepository()
    storage = StorageService()
    queue_adapter = get_queue_adapter()
    nova_service = NovaService()

    job_id = message.job_id
    session_id = message.session_id
    doc_id = message.document_id

    if not doc_id:
        if message.receipt_handle:
            queue_adapter.delete_message(NOVA_QUEUE, message.receipt_handle)
        return

    doc = docs_repo.get(job_id, doc_id)
    if not doc or doc.status not in (DocumentStatus.NOVA_QUEUED, DocumentStatus.NEEDS_NOVA):
        if message.receipt_handle:
            queue_adapter.delete_message(NOVA_QUEUE, message.receipt_handle)
        return

    updated_doc = docs_repo.update_status_conditional(
        job_id=job_id,
        document_id=doc_id,
        new_status=DocumentStatus.NOVA_PARSING,
        allowed_current_statuses=[DocumentStatus.NOVA_QUEUED, DocumentStatus.NEEDS_NOVA],
    )
    if not updated_doc:
        if message.receipt_handle:
            queue_adapter.delete_message(NOVA_QUEUE, message.receipt_handle)
        return

    try:
        # Load extracted JSON from S3
        fields = storage.get_extracted_json(job_id, doc_id)
        unresolved_chunks = fields.get("unresolved_chunks", [])

        t0 = time.time()
        if unresolved_chunks:
            fields = nova_service.resolve_chunks(unresolved_chunks, fields)
        t1 = time.time()
        nova_ms = round((t1 - t0) * 1000, 2)

        if "_timings" in fields:
            fields["_timings"]["nova_ms"] = nova_ms
            fields["_timings"]["total_ms"] = round(fields["_timings"].get("total_ms", 0.0) + nova_ms, 2)

        candidate_name = fields.get("name")
        identity_status = fields.get("identity_status", "PROVISIONAL")
        extraction_quality = fields.get("extraction_quality", 0.80)

        # Status: If confidence is still weak, remain REVIEW_REQUIRED
        if candidate_name and candidate_name != "Name needs review" and fields.get("skills"):
            target_status = DocumentStatus.STRUCTURED_PARSED
        else:
            target_status = DocumentStatus.REVIEW_REQUIRED

        # Save to S3
        storage.upload_extracted_json(job_id, doc_id, fields)

        # Update DynamoDB
        docs_repo.update_status_conditional(
            job_id=job_id,
            document_id=doc_id,
            new_status=target_status,
            allowed_current_statuses=[DocumentStatus.NOVA_PARSING],
            extra_updates={
                "candidate_name": candidate_name or "Name needs review",
                "identity_status": identity_status,
                "extraction_quality": extraction_quality,
            },
        )
        logger.info("NovaQueueWorker: Completed Nova infill for %s -> %s", doc_id, target_status.value)

    except Exception as e:
        logger.error("NovaQueueWorker: Error during Nova infill for %s: %s", doc_id, e, exc_info=True)
        try:
            docs_repo.update_status_conditional(
                job_id=job_id,
                document_id=doc_id,
                new_status=DocumentStatus.REVIEW_REQUIRED,
                allowed_current_statuses=[DocumentStatus.NOVA_PARSING],
                extra_updates={"error_reason": f"Nova fallback error: {str(e)}"},
            )
        except Exception:
            pass

    finally:
        if message.receipt_handle:
            queue_adapter.delete_message(NOVA_QUEUE, message.receipt_handle)

        check_and_progress_fallback(job_id, session_id)
