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

import concurrent.futures
import json
import logging
import os
import time
import uuid
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
    STAGE2_FALLBACK_QUEUE,
    get_queue_adapter,
)
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.storage.storage_service import StorageService

logger = logging.getLogger(__name__)

from urllib.parse import unquote_plus

_process_pool: Optional[concurrent.futures.ProcessPoolExecutor] = None


def _parse_pdf_in_process(pdf_bytes: bytes) -> Dict[str, Any]:
    """Parse PDF bytes sequentially using PyMuPDF within a single isolated process.

    Official PyMuPDF documentation forbids concurrent multithreaded use.
    Executing parsing in isolated worker processes ensures memory safety and avoids crashes.
    """
    import fitz
    from src.extraction.structural_parsing_service import pymupdf_layout_quality_signals

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts = []
    page_signals = []
    hyperlinks = []
    first_page_visual_header = []

    try:
        for idx, page in enumerate(doc):
            page_text = page.get_text()
            page_texts.append(page_text)

            # Collect link URIs
            for link in page.get_links():
                if "uri" in link:
                    hyperlinks.append({"uri": link["uri"]})

            # Extract bounded first-page header geometry / font evidence for identity resolution
            if idx == 0:
                try:
                    blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_SEARCH).get("blocks", [])
                    for b in blocks[:8]:
                        if b.get("type") == 0:
                            for line in b.get("lines", [])[:4]:
                                for span in line.get("spans", [])[:3]:
                                    span_text = span.get("text", "").strip()
                                    if span_text and len(span_text) < 80:
                                        first_page_visual_header.append({
                                            "text": span_text,
                                            "page": 1,
                                            "font_size": span.get("size", 12.0),
                                            "is_bold": bool(span.get("flags", 0) & 2 or "bold" in span.get("font", "").lower()),
                                        })
                except Exception:
                    pass

            try:
                words = page.get_text("words")
                drawings_count = len(page.get_drawings())
                sig = pymupdf_layout_quality_signals(
                    page,
                    text=page_text,
                    words=words,
                    drawings_count=drawings_count,
                )
                page_signals.append(sig)
            except Exception:
                pass
    finally:
        doc.close()

    return {
        "raw_text": "\n\n".join(page_texts),
        "page_signals": page_signals,
        "hyperlinks": hyperlinks,
        "first_page_visual_header": first_page_visual_header,
    }


def run_isolated_pdf_parse(pdf_bytes: bytes) -> Dict[str, Any]:
    """Execute PDF parsing in a bounded process pool, falling back to sequential in-process if pool unavailable."""
    global _process_pool
    # If running in serverless / AWS Lambda, execute directly within the isolated Lambda process
    from src.config.aws import is_running_in_lambda
    if is_running_in_lambda():
        return _parse_pdf_in_process(pdf_bytes)

    if _process_pool is None:
        try:
            max_workers = max(1, min(4, os.cpu_count() or 1))
            _process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=max_workers)
        except Exception as pool_err:
            logger.warning("Could not initialize ProcessPoolExecutor: %s; falling back to direct parse", pool_err)
            _process_pool = None

    if _process_pool is not None:
        try:
            future = _process_pool.submit(_parse_pdf_in_process, pdf_bytes)
            return future.result(timeout=30)
        except Exception as exc:
            logger.warning("Process pool submission failed: %s; falling back to sequential parse", exc)

    return _parse_pdf_in_process(pdf_bytes)


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

    # Claim file for processing with lease
    worker_id = f"stage1-{uuid.uuid4().hex[:8]}"
    claimed = files_repo.claim_file(
        job_id=job_id,
        file_id=file_id,
        worker_id=worker_id,
        lease_seconds=180,
        processing_status=FileStatus.S1_PROCESSING.value,
    )
    if not claimed:
        logger.info("Stage1Worker: could not claim file %s/%s (active lease exists or already terminal), skipping", job_id, file_id)
        return True

    s3_raw_key = s3_key or f"jobs/{job_id}/raw/{file_id}.pdf"

    try:
        t0 = time.monotonic()
        # Download PDF bytes directly into memory (NO /tmp)
        pdf_bytes = storage.get_resume(job_id, file_id, s3_key=s3_raw_key)

        # PyMuPDF fast parse executed in isolated process
        parsed_pdf = run_isolated_pdf_parse(pdf_bytes)
        raw_text = parsed_pdf["raw_text"]
        page_signals = parsed_pdf["page_signals"]
        hyperlinks = parsed_pdf.get("hyperlinks", [])
        visual_headers = parsed_pdf.get("first_page_visual_header", [])

        # Layout quality check
        min_quality = min((p["score"] for p in page_signals), default=1.0) if page_signals else 1.0
        is_clean = min_quality >= QUALITY_THRESHOLD
        min_ro = min((p["reading_order"] for p in page_signals), default=1.0) if page_signals else 1.0
        looks_tabular = any(p.get("not_table_heavy") == 0.0 for p in page_signals)

        # Deterministic regex field extraction
        extractor = MarkdownExtractionService()
        extracted = extractor.extract(
            raw_text,
            hyperlinks=hyperlinks,
            visual_header_lines=visual_headers,
            pymupdf_markdown="",
        )
        fields = extracted.get("fields", {})
        candidate_name = fields.get("name") or "Candidate"
        unresolved = extracted.get("unresolved_chunks", [])

        # Check if critical candidate fields are missing
        has_valid_name = bool(fields.get("name")) and str(fields.get("name")).strip().lower() not in ("candidate", "unknown", "")
        has_experience = bool(fields.get("experience")) and len(fields.get("experience")) > 0

        # Replace undifferentiated fallback with documented reasons
        fallback_reasons = []
        is_ocr_image = min_quality < 0.20 or len(raw_text.strip()) < 100
        is_layout_repair = min_quality < QUALITY_THRESHOLD and not is_ocr_image
        is_ambiguous_name = not has_valid_name

        raw_lower = raw_text.lower()
        is_student = (
            any(k in raw_lower for k in ("student", "fresh graduate", "undergraduate", "fresher", "entry level"))
            or (bool(fields.get("education")) and not bool(fields.get("experience")) and bool(fields.get("skills")))
        )
        is_experience_parsing_failure = (not has_experience) and (not is_student)
        is_legitimate_absent_experience = (not has_experience) and is_student

        if is_ocr_image:
            fallback_reasons.append("ocr_image_text")
        if is_layout_repair:
            fallback_reasons.append("layout_repair")
        if is_ambiguous_name:
            fallback_reasons.append("ambiguous_identity")
        if is_experience_parsing_failure:
            fallback_reasons.append("experience_parsing_failure")
        if is_legitimate_absent_experience:
            fallback_reasons.append("legitimate_absent_fields")
        if bool(unresolved):
            fallback_reasons.append("unresolved_chunks")

        needs_odl_fallback = is_layout_repair or is_ocr_image
        needs_nova_fallback = is_ambiguous_name or is_experience_parsing_failure or bool(unresolved)
        needs_fallback = needs_odl_fallback or needs_nova_fallback

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        logger.info(
            "|PYMUPDF| [Job: %s, File: %s] Extracted candidate='%s', quality=%.2f, needs_fallback=%s, reasons=%s, time=%.1fms",
            job_id, file_id, candidate_name, min_quality, needs_fallback, fallback_reasons, elapsed_ms
        )

        stage1_payload = {
            "fields": fields,
            "raw_text": raw_text[:50000],
            "quality": {
                "score": min_quality,
                "is_clean": is_clean,
                "reading_order_score": min_ro,
                "looks_tabular": looks_tabular,
            },
            "unresolved_chunks": unresolved,
            "needs_fallback": needs_fallback,
            "needs_odl": needs_odl_fallback,
            "needs_nova": needs_nova_fallback,
            "fallback_reasons": fallback_reasons,
            "fallback_reason": ", ".join(fallback_reasons) if fallback_reasons else None,
        }

        # Upload Stage 1 JSON
        s3_stage1_key = storage.upload_stage1_json(job_id, file_id, stage1_payload)

        if not needs_fallback:
            # Clean layout: fast-path directly satisfies extraction!
            fields["document_id"] = file_id
            fields["file_id"] = file_id
            fields["job_id"] = job_id
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
            logger.info("|PYMUPDF| [Job: %s, File: %s] Clean fast-path -> S2_DONE (quality %.2f, candidate: '%s')",
                        job_id, file_id, min_quality, candidate_name)
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
            logger.info("|PYMUPDF| [Job: %s, File: %s] Fallback required -> S1_DONE (quality %.2f, unresolved: %d, candidate: '%s')",
                        job_id, file_id, min_quality, len(unresolved), candidate_name)

            # If recruiter already requested analysis, handle routing to Stage 2
            job = jobs_repo.get(job_id)
            if job and job.analyze_requested:
                if job.analyze_file_ids and file_id not in job.analyze_file_ids:
                    logger.info("Stage1Worker: Job %s analyze_requested but file %s excluded -> REMOVED", job_id, file_id)
                    files_repo.transition_file_terminal(
                        job_id=job_id,
                        file_id=file_id,
                        terminal_status=FileStatus.REMOVED.value,
                        error_message="Excluded from analysis",
                    )
                else:
                    files_repo.record_outbox_event(
                        job_id=job_id,
                        outbox_sk=f"OUTBOX#STAGE2#{file_id}",
                        event_type="STAGE2_DISPATCH",
                        payload={
                            "job_id": job_id,
                            "file_id": file_id,
                            "s3_key": s3_raw_key,
                            "stage": "ODL_BATCH" if needs_odl_fallback else "NOVA",
                            "fallback_reasons": fallback_reasons,
                        },
                    )
                    files_repo.reconcile_outbox(job_id)
                    logger.info("Stage1Worker: Job %s analyze_requested=True -> durably enqueued %s to Stage 2", job_id, file_id)

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
