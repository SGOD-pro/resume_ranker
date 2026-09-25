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
import uuid
from dataclasses import asdict
from typing import Any, Dict, List

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


def process_scoring_message(message: Any) -> bool:
    """Execute candidate scoring and ranking for a job."""
    jobs_repo = JobsRepository()
    files_repo = FilesRepository()
    scoring_repo = ScoringRepository()
    storage = StorageService()

    job_id = getattr(message, "job_id", None)
    if not job_id:
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

    if not job_id:
        logger.error("ScoringWorker: message missing job_id")
        return False

    job = jobs_repo.get(job_id)
    if not job:
        logger.error("ScoringWorker: Job %s not found in DynamoDB", job_id)
        return False

    # Fetch all files for this job
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
        logger.warning("ScoringWorker: Job %s has 0 usable files -> DONE_WITH_ERRORS", job_id)
        jobs_repo.update(job_id, {"status": JobStatus.DONE_WITH_ERRORS.value}, expected_version=job.version)
        return True

    # Load extracted data for each usable file
    candidates: List[Dict[str, Any]] = []
    for f in usable_files:
        try:
            data = storage.get_stage2_json(job_id, f.file_id)
            data["document_id"] = f.file_id
            data["candidate_id"] = f.file_id
            if "name" not in data or not data["name"]:
                data["name"] = f.candidate_name or f.filename
            data["low_confidence_extraction"] = bool(getattr(f, "low_confidence_extraction", False)) or bool(data.get("low_confidence_extraction", False))
            if getattr(f, "fallback_reason", None):
                data["fallback_reason"] = f.fallback_reason
            candidates.append(data)
        except Exception as e:
            logger.warning("ScoringWorker: Failed to read stage2 JSON for %s/%s: %s", job_id, f.file_id, e)

    if not candidates:
        logger.warning("ScoringWorker: Job %s has no readable candidate payloads -> DONE_WITH_ERRORS", job_id)
        jobs_repo.update(job_id, {"status": JobStatus.DONE_WITH_ERRORS.value}, expected_version=job.version)
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

        # Convert to serializable dicts
        scored_dicts = [asdict(c) for c in ranked_candidates]

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
            weights=job.weights,
            candidate_count=len(scored_dicts),
            s3_results_key=f"jobs/{job_id}/results.json",
        )
        try:
            scoring_repo.create(scoring_item)
        except Exception as se:
            logger.warning("ScoringWorker: ScoringItem create warning: %s", se)

        # Update Job status to DONE
        final_status = JobStatus.DONE if not failed_files else JobStatus.DONE_WITH_ERRORS
        jobs_repo.update(
            job_id,
            {"status": final_status.value, "usable_files": len(scored_dicts)},
            expected_version=job.version,
        )
        logger.info("ScoringWorker: Job %s ranked %d candidates -> %s", job_id, len(scored_dicts), final_status.value)
        return True

    except Exception as exc:
        logger.error("ScoringWorker: scoring failed for job %s: %s", job_id, exc, exc_info=True)
        jobs_repo.update(job_id, {"status": JobStatus.FAILED.value, "error_message": str(exc)}, expected_version=job.version)
        return False
