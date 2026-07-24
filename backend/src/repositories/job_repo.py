import logging
from typing import Any
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.models.job import JobItem

logger = logging.getLogger(__name__)

# Fallback in-memory store for local execution/testing when DynamoDB is offline
_IN_MEMORY_JOBS: dict[str, dict[str, Any]] = {}

class DynamoJobRepository:
    """
    Repository wrapper for Job operations over DynamoDB (or in-memory fallback).
    Decouples API routes from direct boto3 / DynamoDB dependencies.
    """

    def __init__(self) -> None:
        try:
            self._underlying = JobsRepository()
        except Exception:
            self._underlying = None

    def save(self, job_data: dict[str, Any]) -> dict[str, Any]:
        """Save a new job or update existing."""
        job_id = job_data.get("job_id") or job_data.get("id")
        if not job_id:
            import uuid
            job_id = str(uuid.uuid4())
            job_data["job_id"] = job_id
            job_data["id"] = job_id

        _IN_MEMORY_JOBS[job_id] = job_data

        if self._underlying:
            try:
                item = JobItem(
                    job_id=job_id,
                    title=job_data.get("title", ""),
                    department=job_data.get("department", ""),
                    description=job_data.get("description", ""),
                    must_have_skills=job_data.get("must_have_skills", []),
                    nice_to_have_skills=job_data.get("nice_to_have_skills", []),
                    min_years=job_data.get("min_years", 0),
                    max_years=job_data.get("max_years", 99),
                    education_level=job_data.get("education_level", "any"),
                    education_field=job_data.get("education_field", ""),
                    keywords=job_data.get("keywords", []),
                    weights=job_data.get("weights", {"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15}),
                )
                self._underlying.create(item)
            except Exception as e:
                logger.warning("DynamoDB save failed, using in-memory store: %s", e)

        return job_data

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve a job by job_id."""
        if self._underlying:
            try:
                item = self._underlying.get(job_id)
                if item:
                    return item.model_dump()
            except Exception as e:
                logger.warning("DynamoDB get failed, using in-memory store: %s", e)

        return _IN_MEMORY_JOBS.get(job_id)

    def update_weights(self, job_id: str, weights: dict[str, float]) -> dict[str, Any]:
        """Update scoring weights for a job."""
        job = self.get(job_id)
        if not job:
            raise KeyError(f"Job ID {job_id} does not exist")

        job["weights"] = weights
        _IN_MEMORY_JOBS[job_id] = job

        if self._underlying:
            try:
                self._underlying.update(job_id, {"weights": weights}, expected_version=job.get("version", 1))
            except Exception as e:
                logger.warning("DynamoDB update weights failed: %s", e)

        return job
