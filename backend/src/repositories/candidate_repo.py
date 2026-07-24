import logging
from typing import Any
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.models.document import DocumentItem

logger = logging.getLogger(__name__)

# Fallback in-memory store for local execution/testing when DynamoDB is offline
_IN_MEMORY_CANDIDATES: dict[str, list[dict[str, Any]]] = {}

class DynamoCandidateRepository:
    """
    Repository wrapper for Candidate operations over DynamoDB (or in-memory fallback).
    Decouples API routes from direct boto3 / DynamoDB dependencies.
    """

    def __init__(self) -> None:
        try:
            self._underlying = DocumentsRepository()
        except Exception:
            self._underlying = None

    def save(self, job_id: str, candidate_data: dict[str, Any]) -> dict[str, Any]:
        """Save a new candidate record."""
        cand_id = candidate_data.get("candidate_id") or candidate_data.get("document_id") or candidate_data.get("id")
        if not cand_id:
            import uuid
            cand_id = str(uuid.uuid4())
            candidate_data["candidate_id"] = cand_id

        candidate_data["job_id"] = job_id
        candidate_data["id"] = cand_id

        if job_id not in _IN_MEMORY_CANDIDATES:
            _IN_MEMORY_CANDIDATES[job_id] = []
        
        # Replace if exists, else append
        existing_idx = next((i for i, c in enumerate(_IN_MEMORY_CANDIDATES[job_id]) if (c.get("id") == cand_id or c.get("candidate_id") == cand_id)), None)
        if existing_idx is not None:
            _IN_MEMORY_CANDIDATES[job_id][existing_idx] = candidate_data
        else:
            _IN_MEMORY_CANDIDATES[job_id].append(candidate_data)

        if self._underlying:
            try:
                item = DocumentItem(
                    document_id=cand_id,
                    job_id=job_id,
                    candidate_name=candidate_data.get("name", "Unknown Candidate"),
                    s3_pdf_key=candidate_data.get("s3_pdf_key", f"jobs/{job_id}/resumes/{cand_id}.pdf")
                )
                self._underlying.create(item)
            except Exception as e:
                logger.warning("DynamoDB candidate save failed: %s", e)

        return candidate_data

    def get(self, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        """Get candidate detail by job_id and candidate_id."""
        cands = _IN_MEMORY_CANDIDATES.get(job_id, [])
        cand = next((c for c in cands if c.get("id") == candidate_id or c.get("candidate_id") == candidate_id or c.get("document_id") == candidate_id), None)
        if cand:
            return cand

        if self._underlying:
            try:
                doc = self._underlying.get(job_id, candidate_id)
                if doc:
                    return doc.model_dump()
            except Exception as e:
                logger.warning("DynamoDB candidate get failed: %s", e)

        return None

    def list_for_job(
        self,
        job_id: str,
        min_score: float | None = None,
        max_score: float | None = None,
        skill_filter: str | None = None,
        limit: int = 20,
        cursor: int = 0
    ) -> dict[str, Any]:
        """
        List candidates for a job with in-memory score & skill filtering and cursor pagination.
        """
        all_cands = _IN_MEMORY_CANDIDATES.get(job_id, [])

        if self._underlying and not all_cands:
            try:
                docs = self._underlying.list_for_job(job_id)
                all_cands = [d.model_dump() for d in docs]
            except Exception as e:
                logger.warning("DynamoDB list candidates failed: %s", e)

        # In-memory filtering
        filtered = []
        for c in all_cands:
            composite_score = c.get("composite_score", c.get("score", 0.0))
            if min_score is not None and composite_score < min_score:
                continue
            if max_score is not None and composite_score > max_score:
                continue
            if skill_filter:
                skills = [s.lower() for s in c.get("skills", [])]
                if skill_filter.lower() not in skills:
                    continue
            filtered.append(c)

        # Sort by composite_score descending
        filtered.sort(key=lambda x: x.get("composite_score", x.get("score", 0.0)), reverse=True)

        # Pagination
        start = cursor
        end = cursor + limit
        paged_cands = filtered[start:end]
        next_cursor = end if end < len(filtered) else None

        return {
            "candidates": paged_cands,
            "total": len(filtered),
            "next_cursor": next_cursor
        }
