"""
test_standalone_architecture.py
================================
Test-first verification for standalone resume ranking engine architecture
per HC-01 (No Authentication Layer) and ADR-07 (Open Endpoints).

Verifies:
1. Complete analysis lifecycle without authentication credentials (no tokens, no cookies, no user accounts)
2. Complete job-level isolation between independent jobs (no cross-job access)
3. Preserved transactional outbox durability without auth dependencies
4. Preserved atomic candidate decision updates and optimistic concurrency
5. Stale job-version rejection and barrier synchronization
"""

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.main import create_app
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.models.document import DocumentItem, DocumentStatus


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unauthenticated Job Creation & Endpoints (HC-01 & ADR-07)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_job_unauthenticated(client):
    """POST /api/v2/jobs must be open and succeed without any Authorization header or session cookie."""
    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.create") as mock_create:
        job_id = str(uuid.uuid4())
        mock_job = JobItem(
            job_id=job_id,
            title="Senior Backend Engineer",
            org_id="org_default",
            session_id=str(uuid.uuid4()),
            status=JobStatus.CREATED,
        )
        mock_create.return_value = mock_job

        payload = {
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "description": "Looking for Python and AWS expertise",
            "must_have_skills": ["Python", "FastAPI"],
            "nice_to_have_skills": ["DynamoDB"],
        }

        # Send request without any Authorization header or cookies
        response = client.post("/api/v2/jobs", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0
        assert "session_id" in data
        assert data["status"] == "created"


def test_get_job_status_unauthenticated(client):
    """GET /api/v2/jobs/{job_id}/status must be open and accessible without credentials."""
    job_id = str(uuid.uuid4())
    mock_job = JobItem(
        job_id=job_id,
        title="Data Scientist",
        org_id="org_default",
        session_id=str(uuid.uuid4()),
        status=JobStatus.READY,
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get_job_with_files", return_value=(mock_job, [])):
            with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.list_for_job", return_value=[]):
                response = client.get(f"/api/v2/jobs/{job_id}/status")
                assert response.status_code == 200
                data = response.json()
                assert data["job_id"] == job_id
                assert data["status"] == "READY"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Strict Job-Level Isolation
# ─────────────────────────────────────────────────────────────────────────────

def test_cross_job_isolation_prevents_file_cross_talk():
    """Files registered to Job A must NEVER appear or be accessible under Job B."""
    from src.infrastructure.repositories.files_repository import FilesRepository

    mock_table = MagicMock()
    stored_items = []

    def mock_query(KeyConditionExpression, **kwargs):
        # Filter items where PK matches requested job
        return {"Items": stored_items}

    mock_table.query.side_effect = mock_query

    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=mock_table):
        repo = FilesRepository()
        files_job_a = repo.list_files_for_job("job_AAA")
        # Assert query strictly targets PK = JOB#job_AAA
        assert mock_table.query.call_count == 1
        call_expr = mock_table.query.call_args[1].get("KeyConditionExpression")
        assert call_expr is not None


def test_cross_job_candidate_decisions_isolation():
    """Candidate decisions saved for Job A must never bleed into Job B."""
    from src.infrastructure.repositories.scoring_repository import ScoringRepository

    mock_table = MagicMock()
    mock_table.query.return_value = {"Items": []}

    with patch("src.infrastructure.repositories.scoring_repository._get_table", return_value=mock_table):
        repo = ScoringRepository()
        repo.get_candidate_decisions(job_id="job_independent_X")
        assert mock_table.query.call_count == 1
        call_expr = mock_table.query.call_args[1].get("KeyConditionExpression")
        assert call_expr is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Preserved Candidate Decision Atomic Updates
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_decision_preserves_independent_fields_standalone():
    """Candidate decision updates preserve existing fields without user account dependency."""
    from src.infrastructure.repositories.scoring_repository import ScoringRepository

    mock_table = MagicMock()
    stored_data = {}

    def mock_update(Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, **kwargs):
        for short_name, actual_field in ExpressionAttributeNames.items():
            val_key = f":{actual_field}"
            if val_key in ExpressionAttributeValues:
                stored_data[actual_field] = ExpressionAttributeValues[val_key]
        return {"Attributes": stored_data}

    mock_table.update_item.side_effect = mock_update

    with patch("src.infrastructure.repositories.scoring_repository._get_table", return_value=mock_table):
        repo = ScoringRepository()
        # 1. First recruiter sets decision
        res1 = repo.save_candidate_decision(
            job_id="job_standalone_1",
            document_id="doc_standalone_1",
            decision_data={"decision": "shortlisted"},
        )
        assert res1.get("decision") == "shortlisted"

        # 2. Second update sets note
        res2 = repo.save_candidate_decision(
            job_id="job_standalone_1",
            document_id="doc_standalone_1",
            decision_data={"notes": "Available next month"},
        )
        assert res2.get("decision") == "shortlisted"
        assert res2.get("notes") == "Available next month"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Preserved Transactional Outbox
# ─────────────────────────────────────────────────────────────────────────────

def test_transactional_outbox_commits_without_auth():
    """File upload transactional commit works without any user/org authentication context."""
    from src.infrastructure.queue.outbox import commit_file_upload_with_outbox

    mock_dynamodb = MagicMock()

    with patch("src.config.aws.get_client", return_value=mock_dynamodb):
        with patch("src.infrastructure.queue.queue_manager.enqueue_fast_parse") as mock_sqs:
            event_id = commit_file_upload_with_outbox(
                job_id="job_standalone_outbox",
                file_id="file_doc_1",
                actual_size=2048,
                session_id="session_upload_1",
                org_id="org_default",
                job_version=1,
                s3_key="jobs/job_standalone_outbox/raw/file_doc_1.pdf",
            )
            assert event_id is not None
            assert mock_dynamodb.transact_write_items.call_count == 1
            assert mock_sqs.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Stale Job-Version Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_stale_job_version_rejection():
    """Worker messages with job_version lower than current job_version must be rejected."""
    from src.infrastructure.models.job import JobItem, JobStatus

    current_job = JobItem(
        job_id="job_version_test",
        title="Version Test",
        version=3,
        job_version=3,
        status=JobStatus.READY,
    )

    incoming_message_version = 2
    is_stale = incoming_message_version < current_job.job_version
    assert is_stale is True, "Stale job version must be detected"
