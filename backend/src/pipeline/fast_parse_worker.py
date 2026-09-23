"""
fast_parse_worker.py — Fast PyMuPDF structural parsing & identity resolution worker
==================================================================================
Consumes messages from FAST_PARSE_QUEUE. Runs only the cheap first layer:
- Download PDF from S3
- PyMuPDF structural/text extraction
- Candidate identity/name resolution using CandidateIdentityResolver
- Section extraction and layout quality diagnostics
- Routes complex/multi-column layouts to NEEDS_ODL; clean layouts to STRUCTURED_PARSED or REVIEW_REQUIRED
- Saves extracted JSON durably to S3 and updates DynamoDB DocumentItem
- Never marks a candidate finally scored here
"""

import logging
import tempfile
import time
from typing import Any, Dict

import fitz

from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    QUALITY_THRESHOLD,
    pymupdf_layout_quality,
)
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import FAST_PARSE_QUEUE, get_queue_adapter
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.storage.storage_service import StorageService
from src.pipeline.coordinator import check_and_progress_session

logger = logging.getLogger(__name__)


def process_fast_parse_message(message: QueueMessage) -> None:
    """Execute fast-pass extraction for one queue message."""
    docs_repo = DocumentsRepository()
    storage = StorageService()
    queue_adapter = get_queue_adapter()

    job_id = message.job_id
    session_id = message.session_id
    doc_id = message.document_id

    if not doc_id:
        logger.error("FastParseWorker: message missing document_id: %s", message.event_id)
        if message.receipt_handle:
            queue_adapter.delete_message(FAST_PARSE_QUEUE, message.receipt_handle)
        return

    doc = docs_repo.get(job_id, doc_id)
    if not doc:
        logger.warning("FastParseWorker: Document %s not found in DynamoDB", doc_id)
        if message.receipt_handle:
            queue_adapter.delete_message(FAST_PARSE_QUEUE, message.receipt_handle)
        return

    # Idempotency guard: If already processed past fast-parse, ack and return
    if doc.status.is_terminal_fast_parse():
        logger.info("FastParseWorker: Document %s already in terminal state %s, skipping", doc_id, doc.status.value)
        if message.receipt_handle:
            queue_adapter.delete_message(FAST_PARSE_QUEUE, message.receipt_handle)
        check_and_progress_session(job_id, session_id)
        return

    # Conditionally transition to FAST_PARSING
    updated_doc = docs_repo.update_status_conditional(
        job_id=job_id,
        document_id=doc_id,
        new_status=DocumentStatus.FAST_PARSING,
        allowed_current_statuses=[
            DocumentStatus.UPLOAD_INITIALIZED,
            DocumentStatus.UPLOADED,
            DocumentStatus.FAST_PARSE_QUEUED,
            DocumentStatus.PENDING,
            DocumentStatus.PARSING,
        ],
    )
    if not updated_doc:
        logger.info("FastParseWorker: Document %s status conflict, skipping message %s", doc_id, message.event_id)
        if message.receipt_handle:
            queue_adapter.delete_message(FAST_PARSE_QUEUE, message.receipt_handle)
        return

    tmp_path = None
    try:
        # 1. Download PDF from S3
        t_dl_0 = time.time()
        pdf_bytes = storage.get_resume(job_id, doc_id, s3_key=doc.s3_pdf_key)
        t_dl_1 = time.time()
        dl_ms = round((t_dl_1 - t_dl_0) * 1000, 2)

        # 2. SHA-256 hash calculation & duplicate detection in background worker
        import hashlib
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        existing = docs_repo.find_by_hash(job_id, file_hash)
        if existing and existing.document_id != doc_id:
            logger.info("FastParseWorker: Doc %s duplicate of %s (hash %s)", doc_id, existing.document_id, file_hash)
            docs_repo.update_status_conditional(
                job_id=job_id,
                document_id=doc_id,
                new_status=DocumentStatus.REJECTED_DUPLICATE,
                allowed_current_statuses=[DocumentStatus.FAST_PARSING],
                extra_updates={
                    "content_hash": file_hash,
                    "error_reason": f"Duplicate of '{existing.filename}' (SHA-256 match)",
                },
            )
            return

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        # 3. PyMuPDF inspection & layout quality calculation
        t_struct_0 = time.time()
        try:
            pdf_doc = fitz.open(tmp_path)
            page_count = len(pdf_doc)
            if page_count == 0:
                raise ValueError("Corrupt PDF: 0 pages")
        except Exception as open_err:
            logger.warning("FastParseWorker: Failed to open PDF %s: %s", doc_id, open_err)
            docs_repo.update_status_conditional(
                job_id=job_id,
                document_id=doc_id,
                new_status=DocumentStatus.FAILED,
                allowed_current_statuses=[DocumentStatus.FAST_PARSING],
                extra_updates={
                    "content_hash": file_hash,
                    "error_reason": "Corrupt or unreadable PDF structure",
                },
            )
            return

        from src.config.aws import get_settings
        settings = get_settings()
        if page_count > settings.MAX_PAGE_COUNT:
            pdf_doc.close()
            logger.warning("FastParseWorker: Doc %s page count %d > %d", doc_id, page_count, settings.MAX_PAGE_COUNT)
            docs_repo.update_status_conditional(
                job_id=job_id,
                document_id=doc_id,
                new_status=DocumentStatus.FAILED,
                allowed_current_statuses=[DocumentStatus.FAST_PARSING],
                extra_updates={
                    "content_hash": file_hash,
                    "page_count": page_count,
                    "error_reason": f"Document exceeds {settings.MAX_PAGE_COUNT} page limit ({page_count} pages)",
                },
            )
            return

        scores = [pymupdf_layout_quality(page) for page in pdf_doc]
        quality_score = round(sum(scores) / len(scores), 2) if scores else 0.0

        # Extract PyMuPDF text & basic blocks
        pymupdf_text_lines = []
        for page in pdf_doc:
            pymupdf_text_lines.append(page.get_text())
        pdf_doc.close()
        full_pymupdf_text = "\n".join(pymupdf_text_lines)
        t_struct_1 = time.time()
        struct_ms = round((t_struct_1 - t_struct_0) * 1000, 2)


        # 3. Deterministic extraction pass
        t_det_0 = time.time()
        markdown_service = MarkdownExtractionService()
        md_result = markdown_service.extract(
            markdown_text=full_pymupdf_text,
            hyperlinks=[],
            elements=[],
            pymupdf_markdown=full_pymupdf_text,
        )
        t_det_1 = time.time()
        det_ms = round((t_det_1 - t_det_0) * 1000, 2)

        fields = md_result.get("fields", {})
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
            "download_ms": dl_ms,
            "structure_ms": struct_ms,
            "deterministic_ms": det_ms,
            "nova_ms": 0.0,
            "total_ms": round(dl_ms + struct_ms + det_ms, 2),
        }
        fields["_timings"] = timings
        fields["_document_id"] = doc_id
        fields["extraction_quality"] = quality_score

        # 4. Check whether deeper ODL extraction or LLM infill is needed
        needs_odl = quality_score < QUALITY_THRESHOLD

        is_unresolved_name = (
            not candidate_name
            or str(candidate_name).strip() in ("", "Name needs review", "Unknown")
            or identity_status == "UNRESOLVED"
        )
        is_missing_experience = not fields.get("experience") or len(fields.get("experience")) == 0

        if needs_odl:
            fallback_reason = f"PyMuPDF layout quality ({quality_score:.2f} < {QUALITY_THRESHOLD}) indicates complex/multi-column layout"
            fields["fallback_reason"] = fallback_reason
            fields["unresolved_chunks"] = [full_pymupdf_text[:4000]]
            fields["raw_text"] = full_pymupdf_text[:4000]
            target_status = DocumentStatus.NEEDS_ODL
        elif is_unresolved_name or is_missing_experience:
            reasons = []
            if is_unresolved_name:
                reasons.append("candidate name unresolved")
            if is_missing_experience:
                reasons.append("experience records not found")
            fallback_reason = f"Deterministic parse missed critical fields ({', '.join(reasons)}); queued for LLM fallback infill"
            fields["fallback_reason"] = fallback_reason
            fields["unresolved_chunks"] = [full_pymupdf_text[:4000]]
            fields["raw_text"] = full_pymupdf_text[:4000]
            target_status = DocumentStatus.NEEDS_NOVA
        else:
            fallback_reason = None
            if identity_status in ("VERIFIED", "PLAUSIBLE") and quality_score >= 0.70:
                target_status = DocumentStatus.STRUCTURED_PARSED
            else:
                target_status = DocumentStatus.REVIEW_REQUIRED

        # 5. Persist extracted JSON to S3
        s3_extracted_key = storage.upload_extracted_json(job_id, doc_id, fields)

        # 6. Update DocumentItem in DynamoDB
        docs_repo.update_status_conditional(
            job_id=job_id,
            document_id=doc_id,
            new_status=target_status,
            allowed_current_statuses=[DocumentStatus.FAST_PARSING],
            extra_updates={
                "candidate_name": candidate_name or "Name needs review",
                "identity_status": identity_status,
                "identity_confidence": identity_confidence,
                "extraction_quality": quality_score,
                "page_count": page_count,
                "content_hash": file_hash,
                "s3_extracted_key": s3_extracted_key,
                "fallback_reason": fallback_reason,
            },

        )
        logger.info(
            "FastParseWorker: Processed %s -> status %s (quality=%.2f, name=%s)",
            doc.filename, target_status.value, quality_score, candidate_name,
        )

    except Exception as e:
        logger.error("FastParseWorker: Extraction failed for doc %s: %s", doc_id, e, exc_info=True)
        try:
            docs_repo.update_status_conditional(
                job_id=job_id,
                document_id=doc_id,
                new_status=DocumentStatus.FAILED,
                allowed_current_statuses=[DocumentStatus.FAST_PARSING],
                extra_updates={"error_reason": str(e)},
            )
        except Exception:
            pass

    finally:
        if tmp_path:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # Acknowledge / delete message from queue
        if message.receipt_handle:
            queue_adapter.delete_message(FAST_PARSE_QUEUE, message.receipt_handle)

        # Check barrier progression
        check_and_progress_session(job_id, session_id)
