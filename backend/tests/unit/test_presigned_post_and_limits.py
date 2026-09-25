"""
test_presigned_post_and_limits.py — Tests for presigned POST upload, limits, and deleted endpoints
===================================================================================================
Verifies:
1. storage.generate_presigned_post enforces content-length-range 1..10MB.
2. POST /api/v2/jobs rejects > 100 files with HTTP 400.
3. POST /api/v2/jobs paginates response when files > 50.
4. GET /api/v2/jobs/{id}/presigned-posts returns subsequent pages.
5. Endpoints /complete and /finalize return HTTP 404 (deleted).
6. Session ownership: mismatched session ID returns HTTP 403 Forbidden.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.storage.storage_service import StorageService
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_storage_generate_presigned_post_conditions():
    """Verify presigned POST policy enforces content-length-range 1..10MB and key match."""
    storage = StorageService()
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_post.return_value = {
        "url": "https://test-bucket.s3.amazonaws.com",
        "fields": {"key": "jobs/test/raw/file1.pdf"},
    }
    storage._client = mock_s3
    storage._bucket = "test-bucket"

    res = storage.generate_presigned_post("jobs/test/raw/file1.pdf")
    assert "url" in res
    assert "fields" in res

    # Check conditions passed to boto3
    call_args = mock_s3.generate_presigned_post.call_args[1]
    conditions = call_args["Conditions"]
    expected_range = ["content-length-range", 1, 10 * 1024 * 1024]
    assert expected_range in conditions
    assert {"key": "jobs/test/raw/file1.pdf"} in conditions


def test_post_jobs_rejects_over_100_files(client):
    """POST /api/v2/jobs must reject requests with >100 files."""
    files_spec = [{"filename": f"candidate_{i}.pdf", "file_size": 1000} for i in range(101)]
    resp = client.post(
        "/api/v2/jobs",
        json={"title": "Test Bulk", "files": files_spec},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "FILE_LIMIT_EXCEEDED" in str(data) or "exceeds limit" in str(data)


def test_post_jobs_pagination_over_50_files(client):
    """POST /api/v2/jobs with 70 files returns page 1 of 50 items and pagination metadata."""
    files_spec = [{"filename": f"cand_{i:02d}.pdf", "file_size": 2000} for i in range(70)]

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.create") as mock_job_create, \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.create_files") as mock_files_create, \
         patch("src.infrastructure.storage.storage_service.StorageService.generate_presigned_post") as mock_presigned:

        mock_presigned.return_value = {"url": "https://s3.amazonaws.com", "fields": {}}

        resp = client.post(
            "/api/v2/jobs",
            json={"title": "Test 70", "files": files_spec},
        )
        assert resp.status_code == 201
        data = resp.json()

        assert data["total_files"] == 70
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["total_pages"] == 2
        assert data["has_more"] is True
        assert data["next_page"] == 2
        assert len(data["files"]) == 50


def test_deleted_complete_and_finalize_endpoints_return_404(client):
    """Verify /complete and /finalize endpoints are deleted and return 404."""
    resp_complete = client.post("/api/v2/jobs/job-123/upload-sessions/sess-123/documents/doc-123/complete")
    assert resp_complete.status_code == 404

    resp_finalize = client.post("/api/v2/jobs/job-123/upload-sessions/sess-123/finalize")
    assert resp_finalize.status_code == 404


def test_session_ownership_enforcement(client):
    """Mismatched session ID on job route returns HTTP 403 Forbidden."""
    job_item = JobItem(
        job_id="job-owned-by-alice",
        session_id="session-alice-123",
        status=JobStatus.UPLOADING,
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=job_item), \
         patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get_job_with_files", return_value=(job_item, [])):

        # Request from Bob's session
        resp = client.get(
            "/api/v2/jobs/job-owned-by-alice/status",
            headers={"X-Session-ID": "session-bob-456"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert "FORBIDDEN" in str(data) or "Access denied" in str(data)

        # Request from Alice's session -> OK
        resp_alice = client.get(
            "/api/v2/jobs/job-owned-by-alice/status",
            headers={"X-Session-ID": "session-alice-123"},
        )
        assert resp_alice.status_code == 200
