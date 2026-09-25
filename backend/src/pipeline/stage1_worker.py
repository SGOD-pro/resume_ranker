"""
stage1_worker.py — Fast PyMuPDF structural parsing worker (Stage 1)
===================================================================
Triggered by S3 s3:ObjectCreated notification on jobs/{job_id}/raw/{file_id}.pdf.
- Pure in-memory parsing using PyMuPDF (fitz) — NO /tmp usage.
- Evaluates layout quality (column clustering, character density, reading order).
- Extracts fields via deterministic regex/layout parsers.
- If clean and high-quality: saves extracted JSON to stage2/ and marks S2_DONE (terminal).
- If fallback needed (multi-column or missing critical fields): saves stage1 JSON and marks S1_DONE.
  If analyze_requested is already True, immediately enqueues to Stage 2.
- On error/corrupt PDF: marks S1_FAILED (terminal).
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

import fitz

from src.config.aws import get_settings
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.structural_parsing_service import (
    QUALITY_THRESHOLD,
    pymupdf_layout_quality,
    pymupdf_layout_quality_signals,
)
from src.infrastructure.models.file import FileStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import (
    ODL_BATCH_QUEUE,
    get_queue_adapter,
)
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.storage.storage_service import StorageService

logger = logging.getLogger(__name__)


from urllib.parse import unquote_plus


def parse_s3_key_for_job_and_file(s3_key: str) -> Optional[Tuple[str, str]]:
    """Parse jobs/{job_id}/raw/{file_id}.pdf -> (job_id, file_id)."""
    s3_key = unquote_plus(s3_key)
    parts = s3_key.split("/")
    if len(parts) >= 4 and parts[0] == "jobs" and parts[2] == "raw":
        job_id = parts[1]
        filename = parts[3]
        file_id = filename.removesuffix(".pdf")
        return job_id, file_id
    return None


def extract_job_file_from_message(message: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (job_id, file_id, s3_key) from either:
    1. S3 Event Notification wrapped in SQS message
    2. Direct QueueMessage or JSON dict
    """
    body = message.body if hasattr(message, "body") else message
    if isinstance(body, dict) and "body" in body:
        body = body["body"]

    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            pass

    if isinstance(body, dict):
        # Case 1: S3 event notification
        if "Records" in body and isinstance(body["Records"], list):
            for record in body["Records"]:
                s3_info = record.get("s3", {})
                obj_key = s3_info.get("object", {}).get("key")
                if obj_key:
                    obj_key = unquote_plus(obj_key)
                    parsed = parse_s3_key_for_job_and_file(obj_key)
                    if parsed:
                        return parsed[0], parsed[1], obj_key

        # Case 2: S3 event inside SNS message body
        if "Message" in body and isinstance(body["Message"], str):
            try:
                sns_inner = json.loads(body["Message"])
                if "Records" in sns_inner and isinstance(sns_inner["Records"], list):
                    for record in sns_inner["Records"]:
                        obj_key = record.get("s3", {}).get("object", {}).get("key")
                        if obj_key:
                            obj_key = unquote_plus(obj_key)
                            parsed = parse_s3_key_for_job_and_file(obj_key)
                            if parsed:
                                return parsed[0], parsed[1], obj_key
            except Exception:
                pass

        # Case 3: Direct QueueMessage dict
        job_id = body.get("job_id")
        file_id = body.get("document_id") or body.get("file_id")
        s3_key = body.get("s3_key") or (f"jobs/{job_id}/raw/{file_id}.pdf" if job_id and file_id else None)
        if job_id and file_id:
            return job_id, file_id, s3_key

    # Case 4: QueueMessage dataclass object
    if hasattr(message, "job_id") and hasattr(message, "document_id"):
        job_id = message.job_id
        file_id = message.document_id
        s3_key = getattr(message, "s3_key", None) or f"jobs/{job_id}/raw/{file_id}.pdf"
        return job_id, file_id, s3_key

    return None, None, None


def process_stage1_message(message: Any) -> bool:
    """Process a single Stage 1 fast-parse message."""
    files_repo = FilesRepository()
    jobs_repo = JobsRepository()
    storage = StorageService()

    job_id, file_id, s3_key = extract_job_file_from_message(message)
    if not job_id or not file_id:
        logger.error("Stage1Worker: could not extract job_id and file_id from message")
        return False

    file_item = files_repo.get_file(job_id, file_id)
    if not file_item:
        logger.warning("Stage1Worker: file item %s/%s not found in DynamoDB", job_id, file_id)
        # Still attempt to process or transition if job exists
        file_item_status = None
    else:
        file_item_status = file_item.status

    # Idempotency check: if already terminal, skip
    if file_item and file_item.is_terminal:
        logger.info("Stage1Worker: file %s/%s already terminal (%s), skipping", job_id, file_id, file_item.status)
        return True

    # Mark non-terminal S1_PROCESSING
    files_repo.update_file_non_terminal(job_id, file_id, FileStatus.S1_PROCESSING)

    s3_raw_key = s3_key or f"jobs/{job_id}/raw/{file_id}.pdf"

    try:
        # Download PDF bytes directly into memory (NO /tmp)
        pdf_bytes = storage.get_resume(job_id, file_id, s3_key=s3_raw_key)

        # PyMuPDF fast parse directly from in-memory stream
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_texts = []
        page_signals = []
        for page in doc:
            page_texts.append(page.get_text())
            try:
                sig = pymupdf_layout_quality_signals(page)
                page_signals.append(sig)
            except Exception:
                pass
        doc.close()
        raw_text = "\n\n".join(page_texts)

        # Layout quality check
        min_quality = min((p["score"] for p in page_signals), default=1.0) if page_signals else 1.0
        is_clean = min_quality >= QUALITY_THRESHOLD
        min_ro = min((p["reading_order"] for p in page_signals), default=1.0) if page_signals else 1.0
        looks_tabular = any(p.get("not_table_heavy") == 0.0 for p in page_signals)

        # Deterministic regex field extraction
        extractor = MarkdownExtractionService()
        extracted = extractor.extract(raw_text, pymupdf_markdown=raw_text)
        fields = extracted.get("fields", {})
        candidate_name = fields.get("name") or "Candidate"
        unresolved = extracted.get("unresolved_chunks", [])

        # Fallback decision (Amendment 3: extraction quality != candidate match score)
        needs_fallback = (min_quality < QUALITY_THRESHOLD) or bool(unresolved)

        stage1_payload = {
            "fields": fields,
            "quality": {
                "score": min_quality,
                "is_clean": is_clean,
                "reading_order_score": min_ro,
                "looks_tabular": looks_tabular,
            },
            "unresolved_chunks": unresolved,
            "needs_fallback": needs_fallback,
        }

        # Upload Stage 1 JSON
        s3_stage1_key = storage.upload_stage1_json(job_id, file_id, stage1_payload)

        if not needs_fallback:
            # Clean layout: fast-path directly satisfies extraction!
            # Upload final structured JSON to stage2 key
            s3_stage2_key = storage.upload_stage2_json(job_id, file_id, fields)
            # Idempotently transition to S2_DONE (terminal, decrements job.remaining)
            files_repo.transition_file_terminal(
                job_id=job_id,
                file_id=file_id,
                terminal_status=FileStatus.S2_DONE.value,
                candidate_name=candidate_name,
                s3_extracted_key=s3_stage2_key,
            )
            logger.info("Stage1Worker: %s/%s clean fast-path -> S2_DONE (quality %.2f)", job_id, file_id, min_quality)
        else:
            # Needs Stage 2 fallback (ODL / Nova)
            files_repo.update_file_non_terminal(
                job_id=job_id,
                file_id=file_id,
                status=FileStatus.S1_DONE,
                s3_stage1_key=s3_stage1_key,
                needs_fallback=True,
                candidate_name=candidate_name,
            )
            logger.info("Stage1Worker: %s/%s needs fallback -> S1_DONE (quality %.2f, unresolved: %d)",
                        job_id, file_id, min_quality, len(unresolved))

            # If recruiter already requested analysis, immediately route to Stage 2
            job = jobs_repo.get(job_id)
            if job and job.analyze_requested:
                # Only if this file is in analyze_file_ids (or list is empty/all)
                if not job.analyze_file_ids or file_id in job.analyze_file_ids:
                    adapter = get_queue_adapter()
                    msg = QueueMessage(
                        job_id=job_id,
                        session_id=job_id,
                        document_id=file_id,
                        org_id="org_default",
                        job_version=job.job_version,
                        s3_key=s3_raw_key,
                        stage="ODL_BATCH",
                    )
                    adapter.send_message(ODL_BATCH_QUEUE, msg)
                    logger.info("Stage1Worker: Job %s analyze_requested=True -> immediately enqueued %s to Stage 2", job_id, file_id)

        return True

    except Exception as exc:
        logger.error("Stage1Worker: extraction failed for %s/%s: %s", job_id, file_id, exc, exc_info=True)
        # Idempotently transition to S1_FAILED (terminal, decrements job.remaining)
        files_repo.transition_file_terminal(
            job_id=job_id,
            file_id=file_id,
            terminal_status=FileStatus.S1_FAILED.value,
            error_message=str(exc),
        )
        return False
