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
from src.infrastructure.models.upload_session import UploadSessionItem


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
    mock_table.query.return_value = {"Items": []}

    with patch("src.infrastructure.repositories.files_repository._get_table", return_value=mock_table):
        repo = FilesRepository()
        files_job_a = repo.list_files_for_job("job_AAA")
        # Assert query strictly targets PK = JOB#job_AAA
        assert mock_table.query.call_count == 1
        call_expr = mock_table.query.call_args[1].get("KeyConditionExpression")
        assert call_expr is not None
        pk_values = [v.get_expression()["values"][1] for v in call_expr.get_expression()["values"] if "values" in v.get_expression()]
        assert "JOB#job_AAA" in pk_values


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
        pk_values = [v.get_expression()["values"][1] for v in call_expr.get_expression()["values"] if "values" in v.get_expression()]
        assert "JOB#job_independent_X" in pk_values


# ─────────────────────────────────────────────────────────────────────────────
# 3. Preserved Candidate Decision Atomic Updates
# ─────────────────────────────────────────────────────────────────────────────

def test_candidate_decision_preserves_independent_fields_standalone():
    """Candidate decision updates preserve existing fields without user account dependency."""
    from src.infrastructure.repositories.scoring_repository import ScoringRepository

    mock_table = MagicMock()
    stored_data = {}

    def mock_update(Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues, **kwargs):
        assignments = UpdateExpression.replace("SET ", "").split(", ")
        for assign in assignments:
            if "=" in assign:
                target, val_ref = [x.strip() for x in assign.split("=")]
                field_name = ExpressionAttributeNames.get(target, target)
                if val_ref in ExpressionAttributeValues:
                    stored_data[field_name] = ExpressionAttributeValues[val_ref]
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
    """File upload transactional commit works without any user/org authentication context and uses ConditionExpressions."""
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
            call_kwargs = mock_dynamodb.transact_write_items.call_args[1]
            items = call_kwargs["TransactItems"]
            assert len(items) == 3
            assert "ConditionExpression" in items[0]["Update"]
            assert "ConditionExpression" in items[1]["Update"]
            assert mock_sqs.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Stale Job-Version Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_stale_job_version_rejection():
    """Worker messages with job_version different from current job_version must be rejected without scoring."""
    from src.pipeline.final_rank_worker import process_final_rank_message
    from src.infrastructure.queue.message import QueueMessage
    from src.infrastructure.queue.queue_manager import FINAL_RANK_QUEUE
    from src.infrastructure.models.upload_session import UploadSessionItem, UploadSessionStatus

    job_id = "job_version_test"
    session_id = "session_version_test"

    mock_session = UploadSessionItem(
        job_id=job_id,
        session_id=session_id,
        status=UploadSessionStatus.FAST_PREPROCESSING,
    )
    mock_job = JobItem(
        job_id=job_id,
        title="Version Test",
        version=3,
        job_version=3,
        status=JobStatus.READY,
    )

    msg = QueueMessage(
        job_id=job_id,
        session_id=session_id,
        document_id=job_id,
        stage="FINAL_RANK",
        job_version=2,
        receipt_handle="rh_stale_123",
    )

    with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.get", return_value=mock_session), \
         patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job), \
         patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.list_for_session") as mock_list_docs, \
         patch("src.pipeline.final_rank_worker.get_queue_adapter") as mock_get_adapter:
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        process_final_rank_message(msg)

        mock_adapter.delete_message.assert_called_once_with(FINAL_RANK_QUEUE, "rh_stale_123")
        assert mock_list_docs.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Standalone Hardening: Findings 1 - 5 Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_complete_document_upload_fails_closed_on_outbox_failure(client):
    """Finding 1: Outbox transaction failure must fail closed with HTTP 500 and NEVER bypass the outbox."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}", session_id=session_id)
    mock_session = UploadSessionItem(job_id=job_id, session_id=session_id)
    mock_doc = DocumentItem(
        job_id=job_id,
        document_id=doc_id,
        session_id=session_id,
        status=DocumentStatus.UPLOAD_INITIALIZED,
        s3_pdf_key=f"jobs/{job_id}/resumes/{doc_id}.pdf",
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.get", return_value=mock_session):
            with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.get", return_value=mock_doc):
                with patch("src.infrastructure.storage.storage_service.StorageService.head_object", return_value={"ContentLength": 1024}):
                    with patch("src.infrastructure.storage.storage_service.StorageService.get_object_byte_range", return_value=b"%PDF-1.5 test content"):
                        with patch("src.api.routes.jobs_v2.commit_file_upload_with_outbox", side_effect=RuntimeError("DynamoDB transaction failed")):
                            with patch("src.infrastructure.repositories.files_repository.FilesRepository.update_file_non_terminal") as mock_bypass_files:
                                with patch("src.infrastructure.queue.queue_manager.enqueue_fast_parse") as mock_bypass_sqs:
                                    response = client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete")
                                    # Must fail closed with 500, not 202
                                    assert response.status_code == 500
                                    # Must NOT call direct bypass functions
                                    assert mock_bypass_files.call_count == 0
                                    assert mock_bypass_sqs.call_count == 0


def test_complete_document_upload_repeated_calls_idempotent(client):
    """Finding 1: Repeated completion requests on an already UPLOADED document must be idempotent and not re-increment counters."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}", session_id=session_id)
    mock_session = UploadSessionItem(job_id=job_id, session_id=session_id)
    mock_doc = DocumentItem(
        job_id=job_id,
        document_id=doc_id,
        session_id=session_id,
        status=DocumentStatus.UPLOADED,
        s3_pdf_key=f"jobs/{job_id}/resumes/{doc_id}.pdf",
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.get", return_value=mock_session):
            with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.get", return_value=mock_doc):
                with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.increment_document_count") as mock_inc_doc:
                    with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.increment_uploaded_count") as mock_inc_sess:
                        response = client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete")
                        assert response.status_code == 202
                        data = response.json()
                        assert data["status"] == "UPLOADED"
                        # Counters must NOT be re-incremented on duplicate completion
                        assert mock_inc_doc.call_count == 0
                        assert mock_inc_sess.call_count == 0


def test_partial_candidate_decision_update_preserves_omitted_fields(client):
    """Finding 2: Partial decision update (e.g. note only) must preserve existing decision, reason, and tags."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}")

    saved_payloads = []
    def mock_save_decision(jid, did, payload, **kwargs):
        saved_payloads.append(payload)
        return {"document_id": did, **payload}

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        with patch("src.infrastructure.repositories.scoring_repository.ScoringRepository.save_candidate_decision", side_effect=mock_save_decision):
            # Patch only note
            response = client.patch(
                f"/api/v2/jobs/{job_id}/candidates/{doc_id}/decision",
                json={"note": "Excellent technical communication"},
            )
            assert response.status_code == 200
            assert len(saved_payloads) == 1
            payload = saved_payloads[0]
            assert payload.get("note") == "Excellent technical communication"
            # Omitted fields must NOT be present in the update payload
            assert "decision" not in payload
            assert "human_decision" not in payload
            assert "status" not in payload
            assert "decision_reason" not in payload
            assert "tags" not in payload


def test_candidate_decision_does_not_mutate_s3_results_json(client):
    """Finding 3: Candidate decision update does not perform S3 results.json read-modify-write."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}")

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        with patch("src.infrastructure.repositories.scoring_repository.ScoringRepository.save_candidate_decision", return_value={}):
            with patch("src.api.routes.jobs_v2._storage") as mock_storage:
                response = client.patch(
                    f"/api/v2/jobs/{job_id}/candidates/{doc_id}/decision",
                    json={"decision": "shortlisted"},
                )
                assert response.status_code == 200
                # S3 results.json must NOT be read or written
                assert mock_storage._client.get_object.call_count == 0
                assert mock_storage._client.put_object.call_count == 0


def test_validate_job_session_document_associations(client):
    """Finding 4: Reject document completion if document does not belong to specified job/session."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    unrelated_session = str(uuid.uuid4())

    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}", session_id=session_id)
    mock_doc = DocumentItem(
        job_id=job_id,
        document_id=doc_id,
        session_id=session_id,
        status=DocumentStatus.UPLOAD_INITIALIZED,
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job):
        # 1. Non-existent document for this job -> 404
        with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.get", return_value=None):
            resp1 = client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete")
            assert resp1.status_code == 404

        # 2. Session does not exist in repository -> 404
        with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.get", return_value=mock_doc):
            with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.get", return_value=None):
                resp2 = client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{unrelated_session}/documents/{doc_id}/complete")
                assert resp2.status_code == 404

        # 3. Session exists but document does not belong to it -> 400
        mock_unrelated_sess = MagicMock()
        with patch("src.infrastructure.repositories.documents_repository.DocumentsRepository.get", return_value=mock_doc):
            with patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.get", return_value=mock_unrelated_sess):
                resp3 = client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{unrelated_session}/documents/{doc_id}/complete")
                assert resp3.status_code == 400


def test_server_generated_job_uuid_used_for_storage_namespace(client):
    """Finding 5: Job creation defaults to complete server-generated UUID namespace."""
    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.create") as mock_create:
        job_id = str(uuid.uuid4())
        def capture_job(job_item):
            return job_item
        mock_create.side_effect = capture_job

        resp = client.post("/api/v2/jobs", json={"title": "Cloud Architect"})
        assert resp.status_code == 200
        assert mock_create.call_count == 1
        created_job = mock_create.call_args[0][0]
        # Must use full job UUID in org_id namespace (e.g. job_<full-uuid>), not truncated 8 chars
        assert created_job.org_id == f"job_{created_job.job_id}"


def test_delete_job_purges_all_s3_prefixes_and_active_sessions(client):
    """Job deletion must purge both standard and org-scoped S3 prefixes, and remove active session items."""
    job_id = str(uuid.uuid4())
    org_id = f"job_{job_id}"
    mock_job = JobItem(job_id=job_id, title="Test", org_id=org_id)

    mock_storage = MagicMock()
    mock_paginator = MagicMock()
    mock_storage._client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.side_effect = [
        [{"Contents": [{"Key": f"jobs/{job_id}/results.json"}]}],
        [{"Contents": [{"Key": f"{org_id}/jobs/{job_id}/sessions/s1/resumes/doc1.pdf"}]}],
    ]

    mock_jobs_repo = MagicMock()
    mock_jobs_repo.get.return_value = mock_job
    mock_jobs_repo._client.query.return_value = {"Items": [{"PK": {"S": f"OUTBOX#{job_id}"}, "SK": {"S": "MSG#1"}}]}

    with patch("src.api.routes.jobs_v2._jobs_repo", mock_jobs_repo), \
         patch("src.api.routes.jobs_v2._storage", mock_storage):
        resp = client.delete(f"/api/v2/jobs/{job_id}")
        assert resp.status_code == 200
        assert mock_jobs_repo.delete.call_count == 1
        # Checked: delete_objects called for purged keys
        assert mock_storage._client.delete_objects.call_count == 2
        # Checked: active session and outbox items deleted
        assert mock_jobs_repo._client.delete_item.call_count == 2


def test_delete_resume_purges_real_s3_keys_and_updates_doc(client):
    """Resume deletion must delete actual S3 keys and update DocumentItem conditionally."""
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}")
    mock_doc = DocumentItem(
        job_id=job_id,
        document_id=doc_id,
        s3_pdf_key=f"custom_org/jobs/{job_id}/sessions/sess_1/resumes/{doc_id}.pdf",
        status=DocumentStatus.PARSED,
    )

    mock_storage = MagicMock()
    mock_docs_repo = MagicMock()
    mock_docs_repo.get.return_value = mock_doc
    mock_files_repo = MagicMock()
    mock_files_repo.get.return_value = None

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job), \
         patch("src.api.routes.jobs_v2._docs_repo", mock_docs_repo), \
         patch("src.api.routes.jobs_v2._files_repo", mock_files_repo), \
         patch("src.api.routes.jobs_v2._storage", mock_storage):
        resp = client.delete(f"/api/v2/jobs/{job_id}/resumes/{doc_id}")
        assert resp.status_code == 200
        assert mock_files_repo.transition_file_terminal.call_count == 1
        assert mock_docs_repo.update_status_conditional.call_count == 1
        # Custom S3 key must have been deleted
        deleted_keys = [call[1]["Key"] for call in mock_storage._client.delete_object.call_args_list]
        assert mock_doc.s3_pdf_key in deleted_keys


def test_candidate_decision_conflict_raises_409(client):
    """Decision update conflict (e.g. stale expected_version) must return HTTP 409 Conflict."""
    from botocore.exceptions import ClientError
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}")

    err = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Conditional check failed"}},
        "UpdateItem",
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job), \
         patch("src.infrastructure.repositories.scoring_repository.ScoringRepository.save_candidate_decision", side_effect=err):
        resp = client.patch(
            f"/api/v2/jobs/{job_id}/candidates/{doc_id}/decision",
            json={"decision": "shortlisted", "expected_version": 2},
        )
        assert resp.status_code == 409
        assert "conflict" in resp.json()["detail"].lower()


def test_relay_pending_outbox_paginates_and_dispatches():
    """Outbox relay must paginate through DynamoDB scan/query and dispatch pending records."""
    from src.infrastructure.queue.outbox import relay_pending_outbox

    mock_dynamodb = MagicMock()
    page1 = {
        "Items": [
            {
                "event_id": {"S": "ev-1"},
                "job_id": {"S": "job-1"},
                "document_id": {"S": "doc-1"},
                "session_id": {"S": "sess-1"},
                "org_id": {"S": "org-1"},
                "job_version": {"N": "1"},
                "s3_key": {"S": "key-1"},
            }
        ],
        "LastEvaluatedKey": {"PK": {"S": "OUTBOX#job-1"}, "SK": {"S": "OUTBOX#ev-1"}},
    }
    page2 = {
        "Items": [
            {
                "event_id": {"S": "ev-2"},
                "job_id": {"S": "job-1"},
                "document_id": {"S": "doc-2"},
                "session_id": {"S": "sess-1"},
                "org_id": {"S": "org-1"},
                "job_version": {"N": "1"},
                "s3_key": {"S": "key-2"},
            }
        ],
    }
    mock_dynamodb.scan.side_effect = [page1, page2]

    with patch("src.config.aws.get_client", return_value=mock_dynamodb), \
         patch("src.infrastructure.queue.queue_manager.enqueue_fast_parse") as mock_enqueue, \
         patch("src.infrastructure.queue.outbox._delete_outbox_record") as mock_delete:
        relayed_count = relay_pending_outbox(max_records=10)
        assert relayed_count == 2
        assert mock_dynamodb.scan.call_count == 2
        assert mock_enqueue.call_count == 2
        assert mock_delete.call_count == 2


def test_write_outbox_and_send_fails_closed_when_db_fails():
    """write_outbox_and_send must fail closed before SQS publish if DynamoDB put_item fails."""
    from src.infrastructure.queue.outbox import write_outbox_and_send

    mock_dynamodb = MagicMock()
    mock_dynamodb.put_item.side_effect = RuntimeError("DynamoDB write failed")

    with patch("src.config.aws.get_client", return_value=mock_dynamodb), \
         patch("src.infrastructure.queue.queue_manager.enqueue_fast_parse") as mock_enqueue:
        with pytest.raises(RuntimeError, match="outbox persistence failed"):
            write_outbox_and_send(
                job_id="job-outbox-fail",
                session_id="sess-1",
                document_id="doc-1",
                org_id="job_job-outbox-fail",
                job_version=1,
                s3_key="jobs/job-outbox-fail/raw/doc-1.pdf",
            )
        assert mock_enqueue.call_count == 0


def test_analyze_job_fails_closed_without_non_transactional_fallback(client):
    """POST /analyze must fail with HTTP 500 rather than falling back to non-transactional SQS enqueue."""
    job_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    mock_job = JobItem(job_id=job_id, title="Test", org_id=f"job_{job_id}", session_id="sess-1")
    mock_file = FileItem(
        job_id=job_id,
        file_id=file_id,
        filename="resume.pdf",
        status=FileStatus.UPLOADED,
        s3_raw_key=f"jobs/{job_id}/raw/{file_id}.pdf",
    )

    with patch("src.infrastructure.repositories.jobs_repository.JobsRepository.get", return_value=mock_job), \
         patch("src.infrastructure.repositories.upload_sessions_repository.UploadSessionsRepository.list_for_job", return_value=[]), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.list_files_for_job", return_value=[mock_file]), \
         patch("src.api.routes.jobs_v2.write_outbox_and_send", side_effect=RuntimeError("Outbox DB unavailable")), \
         patch("src.api.routes.jobs_v2.enqueue_fast_parse") as mock_bypass_enqueue:
        resp = client.post(f"/api/v2/jobs/{job_id}/analyze", json={"file_ids": [file_id]})
        assert resp.status_code == 500
        assert mock_bypass_enqueue.call_count == 0


def test_extract_pdf_text_sync_serializes_fitz_in_process():
    """Concurrent extract_pdf_text_sync calls in the same process must serialize PyMuPDF execution."""
    import concurrent.futures
    import threading
    import time as pytime
    from src.extraction import structural_parsing_service as sps

    active_calls = 0
    max_concurrent = 0
    counter_lock = threading.Lock()

    class DummyDoc:
        def __iter__(self):
            return iter([])
        def close(self):
            pass

    def slow_fitz_open(*args, **kwargs):
        nonlocal active_calls, max_concurrent
        with counter_lock:
            active_calls += 1
            max_concurrent = max(max_concurrent, active_calls)
        pytime.sleep(0.05)
        with counter_lock:
            active_calls -= 1
        return DummyDoc()

    with patch.object(sps.fitz, "open", side_effect=slow_fitz_open):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(sps.extract_pdf_text_sync, b"%PDF-1.4") for _ in range(4)]
            for f in futures:
                f.result()

    assert max_concurrent == 1

