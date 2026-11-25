"""
scoring_worker.py — Final candidate scoring & ranking worker
============================================================
Triggered when all files reach terminal states and Analyze was requested (remaining == 0).
- Loads all S2_DONE candidates for the job.
- Runs deterministic CandidateScorer.rank() with configured job weights.
- Saves full ranking result to S3 at jobs/{job_id}/results.json.
- Updates Job status to DONE (or DONE_WITH_ERRORS if 0 usable files).
"""

import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from src.infrastructure.models.file import FileStatus
from src.infrastructure.models.job import JobStatus
from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.scoring_repository import ScoringRepository
from src.infrastructure.storage.storage_service import StorageService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

logger = logging.getLogger(__name__)


def _is_cond_failed(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
    return "ConditionalCheckFailedException" in type(exc).__name__ or "ConditionalCheckFailed" in str(exc)


def _update_job_scoring_result(
    jobs_repo: JobsRepository,
    job_id: str,
    updates: Dict[str, Any],
    initial_job: Any,
    msg_job_version: Optional[int],
) -> str:
    """Update job status with optimistic lock retries; returns 'updated' or 'skipped'."""
    candidate_job = initial_job
    for attempt in range(4):
        try:
            jobs_repo.update(job_id, updates, expected_version=candidate_job.version)
            return "updated"
        except Exception as exc:
            if not _is_cond_failed(exc):
                raise
            fresh_job = jobs_repo.get(job_id)
            if not fresh_job:
                logger.warning("ScoringWorker: Job %s deleted concurrently; skipping update", job_id)
                return "skipped"
            fresh_jv = int(getattr(fresh_job, "job_version", 1))
            if msg_job_version is not None and msg_job_version < fresh_jv:
                logger.info(
                    "ScoringWorker: Stale scoring event for job %s (msg_jv=%s < current=%s); skipping",
                    job_id, msg_job_version, fresh_jv,
                )
                return "skipped"
            if fresh_job.status in (JobStatus.DONE, JobStatus.DONE_WITH_ERRORS):
                logger.info("ScoringWorker: Job %s already %s (v%s); skipping duplicate update",
                            job_id, fresh_job.status.value, fresh_job.version)
                return "skipped"
            candidate_job = fresh_job
            time.sleep(0.05 * (attempt + 1))

    jobs_repo.update(job_id, updates, expected_version=candidate_job.version)
    return "updated"


def process_scoring_message(message: Any) -> bool:
    """Execute candidate scoring and ranking for a job."""
    jobs_repo = JobsRepository()
    files_repo = FilesRepository()
    scoring_repo = ScoringRepository()
    storage = StorageService()

    job_id = getattr(message, "job_id", None)
    msg_job_version = getattr(message, "job_version", None)
    body = message.body if hasattr(message, "body") else message
    if isinstance(body, dict) and "body" in body:
        body = body["body"]
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            pass
    if isinstance(body, dict):
        if not job_id:
            job_id = body.get("job_id")
        if msg_job_version is None:
            msg_job_version = body.get("job_version")

    if msg_job_version is not None:
        try:
            msg_job_version = int(msg_job_version)
        except (TypeError, ValueError):
            msg_job_version = None

    if not job_id:
        logger.error("ScoringWorker: message missing job_id")
        return False

    job = jobs_repo.get(job_id)
    if not job:
        logger.warning("ScoringWorker: Job %s not found in DynamoDB (deleted); acking", job_id)
        return True

    current_jv = int(getattr(job, "job_version", 1))
    if msg_job_version is not None and msg_job_version < current_jv:
        logger.info("ScoringWorker: Discarding stale scoring message for job %s (msg_jv=%d < current=%d)",
                    job_id, msg_job_version, current_jv)
        return True

    if job.status in (JobStatus.DONE, JobStatus.DONE_WITH_ERRORS) and (
        msg_job_version is None or msg_job_version == current_jv
    ):
        logger.info("ScoringWorker: Job %s already in terminal state %s (jv=%d); skipping duplicate",
                    job_id, job.status.value, current_jv)
        return True

    # Fetch all files for this job
    all_files = files_repo.list_files_for_job(job_id)
    if not all_files:
        from src.infrastructure.repositories.documents_repository import DocumentsRepository
        from src.infrastructure.models.file import FileItem
        docs_repo = DocumentsRepository()
        docs = docs_repo.list_for_job(job_id)
        if docs:
            file_items_to_create = []
            for doc in docs:
                f_item = FileItem(
                    job_id=job_id,
                    file_id=doc.document_id,
                    filename=doc.filename,
                    file_size=doc.file_size,
                    status=FileStatus.S2_DONE if doc.status.is_terminal_fast_parse() else FileStatus.UPLOADED,
                    candidate_name=doc.candidate_name,
                    s3_raw_key=doc.s3_pdf_key,
                    s3_extracted_key=doc.s3_extracted_key,
                )
                file_items_to_create.append(f_item)
            files_repo.create_files(job_id, file_items_to_create)
            all_files = files_repo.list_files_for_job(job_id)

    selected_set = set(job.analyze_file_ids) if job.analyze_file_ids else {f.file_id for f in all_files}

    usable_files = [
        f for f in all_files
        if f.status == FileStatus.S2_DONE and f.file_id in selected_set
    ]

    failed_files = [
        f for f in all_files
        if f.status in (FileStatus.S1_FAILED, FileStatus.S2_FAILED) and f.file_id in selected_set
    ]

    if not usable_files:
        # Check if DocumentItem entities exist and have terminal extraction results
        from src.infrastructure.repositories.documents_repository import DocumentsRepository
        from src.infrastructure.models.document import DocumentStatus
        docs_repo = DocumentsRepository()
        docs = docs_repo.list_for_job(job_id)
        valid_docs = [
            d for d in docs
            if d.status in (
                DocumentStatus.STRUCTURED_PARSED,
                DocumentStatus.REVIEW_REQUIRED,
                DocumentStatus.PARSED,
                DocumentStatus.SCORED,
            )
        ]
        if valid_docs:
            logger.info("ScoringWorker: 0 usable FileItems, but %d valid DocumentItems found. Delegating to final_rank_worker.", len(valid_docs))
            from src.pipeline.final_rank_worker import process_final_rank_message
            from src.infrastructure.queue.message import QueueMessage
            q_msg = QueueMessage(
                job_id=job_id,
                session_id=job.session_id or getattr(valid_docs[0], "session_id", "default"),
                org_id=getattr(job, "org_id", "org_default"),
                job_version=job.job_version,
                stage="FINAL_RANK",
            )
            process_final_rank_message(q_msg)
            return True

        logger.warning("ScoringWorker: Job %s has 0 usable files -> DONE_WITH_ERRORS", job_id)
        _update_job_scoring_result(jobs_repo, job_id, {"status": JobStatus.DONE_WITH_ERRORS.value}, job, msg_job_version)
        return True

    # Load extracted data for each usable file
    candidates: List[Dict[str, Any]] = []
    for f in usable_files:
        try:
            try:
                data = storage.get_stage2_json(job_id, f.file_id)
            except Exception:
                data = storage.get_extracted_json(job_id, f.file_id)
            data["document_id"] = f.file_id
            data["candidate_id"] = f.file_id
            data["file_id"] = f.file_id
            data["_document_id"] = f.file_id
            if "name" not in data or not data["name"]:
                data["name"] = f.candidate_name or f.filename
            data["low_confidence_extraction"] = bool(getattr(f, "low_confidence_extraction", False)) or bool(data.get("low_confidence_extraction", False))
            if getattr(f, "fallback_reason", None):
                data["fallback_reason"] = f.fallback_reason
            candidates.append(data)
        except Exception as e:
            logger.warning("ScoringWorker: Failed to read stage2/extracted JSON for %s/%s: %s", job_id, f.file_id, e)

    if not candidates:
        logger.warning("ScoringWorker: Job %s has no readable candidate payloads -> DONE_WITH_ERRORS", job_id)
        _update_job_scoring_result(jobs_repo, job_id, {"status": JobStatus.DONE_WITH_ERRORS.value}, job, msg_job_version)
        return True

    try:
        # Build JobDescription schema
        jd = JobDescription(
            title=job.title,
            department=job.department,
            description=job.description,
            must_have_skills=job.must_have_skills,
            nice_to_have_skills=job.nice_to_have_skills,
            min_years=job.min_years,
            max_years=job.max_years,
            required_degree=job.education_level or "any",
            preferred_field=job.education_field or "",
            keywords=job.keywords,
            weights=job.weights,
        )

        scorer = CandidateScorer()
        ranked_candidates = scorer.rank(jd, candidates)

        # Convert to serializable dicts with job_id and canonical pdf_url
        scored_dicts = []
        for c in ranked_candidates:
            cd = asdict(c)
            cd["job_id"] = job_id
            cd["document_id"] = c.document_id
            if not cd.get("pdf_url"):
                cd["pdf_url"] = f"/api/v2/jobs/{job_id}/resumes/{c.document_id}/download"
            scored_dicts.append(cd)

        scoring_id = str(uuid.uuid4())
        storage.upload_ranking(job_id, scoring_id, scored_dicts)

        # Also write canonical jobs/{job_id}/results.json
        storage._client.put_object(
            Bucket=storage._bucket,
            Key=f"jobs/{job_id}/results.json",
            Body=json.dumps(
                {
                    "job_id": job_id,
                    "status": "scored",
                    "total_candidates": len(scored_dicts),
                    "candidates": scored_dicts,
                },
                ensure_ascii=False,
                default=str,
            ).encode("utf-8"),
            ContentType="application/json",
        )

        # Update scoring entity in DynamoDB
        scoring_item = ScoringItem(
            scoring_id=scoring_id,
            job_id=job_id,
            status=ScoringStatus.COMPLETED,
            weights_used=job.weights,
            candidate_count=len(scored_dicts),
            s3_result_key=f"jobs/{job_id}/results.json",
        )
        try:
            scoring_repo.create(scoring_item)
        except Exception as se:
            logger.warning("ScoringWorker: ScoringItem create warning: %s", se)

        # Update Job status to DONE
        final_status = JobStatus.DONE if not failed_files else JobStatus.DONE_WITH_ERRORS
        outcome = _update_job_scoring_result(
            jobs_repo,
            job_id,
            {"status": final_status.value, "usable_files": len(scored_dicts)},
            job,
            msg_job_version,
        )
        if outcome == "skipped":
            return True
        # Keep UploadSessionItem synchronized when sessions exist
        try:
            from src.infrastructure.models.upload_session import UploadSessionStatus
            from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
            s_repo = UploadSessionsRepository()
            sess_target = UploadSessionStatus.READY_WITH_WARNINGS if failed_files else UploadSessionStatus.READY
            for sess in s_repo.list_for_job(job_id):
                if sess.status not in (UploadSessionStatus.READY, UploadSessionStatus.READY_WITH_WARNINGS):
                    s_repo.update_status(job_id, sess.session_id, sess_target, expected_version=sess.version)
        except Exception as sess_sync_err:
            logger.debug("ScoringWorker: UploadSession sync skipped: %s", sess_sync_err)
        logger.info("ScoringWorker: Job %s ranked %d candidates -> %s", job_id, len(scored_dicts), final_status.value)
        return True

    except Exception as exc:
        logger.error("ScoringWorker: scoring failed for job %s: %s", job_id, exc, exc_info=True)
        try:
            fresh_job = jobs_repo.get(job_id)
            if not fresh_job:
                return True
            if msg_job_version is not None and msg_job_version < int(getattr(fresh_job, "job_version", 1)):
                return True
            if fresh_job.status in (JobStatus.DONE, JobStatus.DONE_WITH_ERRORS):
                return True
            jobs_repo.update(
                job_id,
                {"status": JobStatus.FAILED.value, "error_message": str(exc)},
                expected_version=fresh_job.version,
            )
        except Exception as mark_err:
            logger.warning("ScoringWorker: could not mark job %s FAILED safely: %s", job_id, mark_err)
        return False
