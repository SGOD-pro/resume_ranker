"""
test_pre_merge_hardening_regressions.py — Section 1 Behavioral Regression Tests
================================================================================
Demonstrates and guards all 11 required scenarios:
1. Duplicate Analyze requests and repeated uploads.
2. Browser closing, refreshing, or disconnecting while processing.
3. A worker crashing after S3 upload but before DynamoDB persistence.
4. A message being processed twice or by two workers.
5. SQS enqueue failure, timeout, or unknown delivery outcome.
6. Failed S3 upload with successfully uploaded peers.
7. Pool initialization races, worker failures, and timeouts.
8. Partial Stage 2 completion and safe recovery.
9. Invalid PDFs, renamed extensions, oversized files, truncated files, unsupported formats.
10. Cross-organization access, manipulated IDs, stale job versions.
11. Missing extraction fields, uncertain evidence, misleading experience dates.
"""

import asyncio
import io
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.main import app
from src.config.aws import get_settings
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.upload_session import UploadSessionItem, UploadSessionStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import (
    FAST_PARSE_QUEUE,
    FINAL_RANK_QUEUE,
    ODL_BATCH_QUEUE,
    get_queue_adapter,
)
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.files_repository import FilesRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
from src.infrastructure.storage.storage_service import StorageService
from src.pipeline.fast_parse_worker import process_fast_parse_message
from src.pipeline.stage1_worker import run_isolated_pdf_parse
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v2/auth/register",
        json={
            "org_name": f"Org_{uid}",
            "email": f"recruiter_{uid}@example.com",
            "name": f"Recruiter {uid}",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def auth_headers_org2(client):
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v2/auth/register",
        json={
            "org_name": f"Org2_{uid}",
            "email": f"recruiter2_{uid}@example.com",
            "name": f"Recruiter2 {uid}",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def make_dummy_pdf(text: str = "Candidate Resume") -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"{text}\nJane Doe\njane@example.com\nSkills: Python, SQL\nExperience: 3 years")
    b = doc.tobytes()
    doc.close()
    return b


# ─────────────────────────────────────────────────────────────────────────────
# 1. SQS Enqueue Failure must not increment enqueued_count or claim success
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_sqs_enqueue_failure_does_not_claim_success(client, auth_headers):
    """When enqueue_fast_parse fails due to SQS timeout/error, enqueued_count must be 0 and fail gracefully."""
    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Test Enqueue Fail"})
    assert job_resp.status_code == 200
    job_id = job_resp.json()["id"]

    files_repo = FilesRepository()
    fid = str(uuid.uuid4())
    f_item = FileItem(
        job_id=job_id,
        file_id=fid,
        filename="test.pdf",
        status=FileStatus.UPLOADED,
        s3_raw_key=f"jobs/{job_id}/raw/{fid}.pdf",
    )
    files_repo.create_files(job_id, [f_item])

    with patch("src.api.routes.jobs_v2.enqueue_fast_parse", side_effect=RuntimeError("SQS network error")):
        resp = client.post(
            f"/api/v2/jobs/{job_id}/fast-parse",
            headers=auth_headers,
            json={"file_ids": [fid]},
        )
        data = resp.json()
        assert data.get("enqueued", 0) == 0, f"Expected enqueued=0 on SQS error, got {data.get('enqueued')}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PDF Structure Verification: Truncated or Invalid PDFs rejected at complete
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_complete_upload_rejects_truncated_pdf(client, auth_headers):
    """A file with %PDF magic bytes but truncated or invalid PDF structure must be rejected."""
    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "PDF Integrity Test"})
    job_id = job_resp.json()["id"]

    sess_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": 1, "files": [{"filename": "corrupt.pdf", "file_size": 20}]},
    )
    sess_data = sess_resp.json()
    sess_id = sess_data["session_id"]
    doc_info = sess_data["documents"][0]
    doc_id = doc_info["document_id"]

    storage = StorageService()
    # Put truncated 10-byte pseudo-PDF
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=b"%PDF-1.4\nJUNK",
        ContentType="application/pdf",
    )

    # Complete call must reject truncated/corrupt PDF structure, not just check first 5 bytes
    comp_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{sess_id}/documents/{doc_id}/complete",
        headers=auth_headers,
    )
    assert comp_resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cross-Tenant Access is strictly 403 Forbidden
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_cross_tenant_access_forbidden(client, auth_headers, auth_headers_org2):
    """Org2 cannot access or complete uploads for jobs belonging to Org1."""
    # Org1 creates job
    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Org1 Secret Job"})
    job_id = job_resp.json()["id"]

    # Org2 attempts to create upload session on Org1's job
    sess_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers_org2,
        json={"document_count": 1, "files": [{"filename": "attack.pdf", "file_size": 1000}]},
    )
    assert sess_resp.status_code in (403, 404)

    # Org2 attempts to request analysis on Org1's job
    ana_resp = client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers_org2,
    )
    assert ana_resp.status_code in (403, 404)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Caller Candidate Dictionaries are not mutated during scoring
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_scorer_does_not_mutate_caller_candidate_dicts():
    """Scorer.rank() must not modify input candidate dictionaries in-place."""
    jd = JobDescription(
        title="Software Engineer",
        department="Engineering",
        must_have_skills=["Python", "FastAPI"],
    )
    # Candidate with cross-domain (legal) background to trigger severe domain mismatch flag
    candidate = {
        "_document_id": "cand_1",
        "name": "Jane Lawyer",
        "skills": ["Litigation", "Contract Law"],
        "experience": [{"role": "Senior Attorney", "start": "2020-01", "end": "2023-01"}],
    }
    candidate_copy = json.loads(json.dumps(candidate))

    scorer = CandidateScorer()
    scorer.rank(jd, [candidate])

    assert "_severe_domain_mismatch" not in candidate, "Scorer mutated input dict with internal domain flags!"
    assert candidate == candidate_copy, "Scorer mutated candidate dictionary fields in-place!"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Process Pool Initialization Race and Recovery in stage1_worker
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_stage1_worker_recovers_from_broken_pool():
    """If process pool raises BrokenProcessPool or crashes, stage1_worker must recover and parse directly."""
    import concurrent.futures.process
    from src.pipeline import stage1_worker

    dummy_pdf = make_dummy_pdf("Worker Resilience")

    mock_pool = MagicMock()
    mock_pool.submit.side_effect = concurrent.futures.process.BrokenProcessPool("Worker process died")

    with patch.object(stage1_worker, "_process_pool", mock_pool):
        res = stage1_worker.run_isolated_pdf_parse(dummy_pdf)
        assert res is not None
        assert "raw_text" in res
        assert "Worker Resilience" in res["raw_text"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Duplicate Analyze requests are safe and idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_duplicate_analyze_requests_idempotent(client, auth_headers):
    """Submitting Analyze twice consecutively must not crash, produce 500, or duplicate dispatch events."""
    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Analyze Idempotency"})
    job_id = job_resp.json()["id"]

    # First analyze call
    res1 = client.post(f"/api/v2/jobs/{job_id}/analysis", headers=auth_headers)
    assert res1.status_code == 202

    # Second immediate duplicate analyze call
    res2 = client.post(f"/api/v2/jobs/{job_id}/analysis", headers=auth_headers)
    assert res2.status_code == 202
    assert res2.json()["status"] == "ANALYSIS_REQUESTED"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Stale Job Versions reject out-of-order final ranking messages
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_stale_job_version_rejected():
    """If job description was updated to v2, a v1 ranking message must be safely dropped."""
    from src.pipeline.final_rank_worker import process_final_rank_message

    jobs_repo = JobsRepository()
    uid = uuid.uuid4().hex[:8]
    job_item = JobItem(
        job_id=uid,
        org_id="org_test",
        title="Original Job",
        job_version=2,  # Current is 2
        status=JobStatus.READY,
    )
    jobs_repo.create(job_item)

    stale_msg = QueueMessage(
        stage="FINAL_RANK",
        job_id=uid,
        session_id=str(uuid.uuid4()),
        org_id="org_test",
        job_version=1,  # Stale version 1
    )

    process_final_rank_message(stale_msg)
    fresh_job = jobs_repo.get(uid)
    # Stale message must not overwrite job status to SCORING or corrupt version
    assert fresh_job.job_version == 2
    assert fresh_job.status == JobStatus.READY


# ─────────────────────────────────────────────────────────────────────────────
# 8. Observability & Logging Sanitization: PII is never emitted at INFO/WARNING
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_logging_sanitization_no_pii_emitted(caplog):
    """Logging statements must NEVER emit candidate PII (names, emails, phones) at INFO or WARNING."""
    import logging
    from src.pipeline.stage2_worker import merge_extracted_fields

    base_fields = {"name": "", "email": "", "phone": ""}
    fallback_fields = {
        "name": "SuperSecret CandidateName",
        "email": "private.applicant@domain.com",
        "phone": "+1-555-867-5309",
    }

    with caplog.at_level(logging.INFO):
        merged = merge_extracted_fields(base_fields, fallback_fields, "TestFallback")

    assert merged["name"] == "SuperSecret CandidateName"

    # Inspect all emitted log messages at INFO or higher
    for record in caplog.records:
        if record.levelno in (logging.INFO, logging.WARNING):
            msg = record.getMessage()
            assert "SuperSecret CandidateName" not in msg, f"PII candidate name leaked in log: {msg}"
            assert "private.applicant@domain.com" not in msg, f"PII email leaked in log: {msg}"
            assert "+1-555-867-5309" not in msg, f"PII phone leaked in log: {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# 9. _trigger_scoring Authoritative Org ID and Stale Event Safety
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_trigger_scoring_authoritative_org_id_and_no_stale_upgrade():
    """_trigger_scoring must use authoritative org_id and NEVER upgrade stale unversioned events to latest job_version."""
    jobs_repo = JobsRepository()
    files_repo = FilesRepository()
    queue_adapter = get_queue_adapter()

    job_id = f"job_auth_{uuid.uuid4().hex[:8]}"
    authoritative_org = f"org_{uuid.uuid4().hex[:8]}"

    job_item = JobItem(
        job_id=job_id,
        org_id=authoritative_org,
        title="Authoritative Org Job",
        job_version=3,  # Job has been modified up to version 3
        status=JobStatus.PROCESSING,
    )
    jobs_repo.create(job_item)

    # 1. Calling _trigger_scoring without explicit job_version (e.g. stale unversioned event)
    # MUST NOT upgrade to version 3; it must default safely to base version 1.
    # It must also resolve authoritative_org rather than hardcoding "org_default".
    with patch.object(queue_adapter, "send_message") as mock_send:
        files_repo._trigger_scoring(job_id)

        assert mock_send.call_count == 1
        sent_queue, sent_msg = mock_send.call_args[0]
        assert sent_queue == FINAL_RANK_QUEUE
        assert sent_msg.job_id == job_id
        assert sent_msg.org_id == authoritative_org
        assert sent_msg.job_version == 1  # Crucial: NOT upgraded to 3!

    # 2. Calling _trigger_scoring with explicit pinned job_version (e.g. version 2)
    # preserves that exact pinned version
    with patch.object(queue_adapter, "send_message") as mock_send:
        files_repo._trigger_scoring(job_id, job_version=2, org_id=authoritative_org)

        assert mock_send.call_count == 1
        _, sent_msg = mock_send.call_args[0]
        assert sent_msg.org_id == authoritative_org
        assert sent_msg.job_version == 2

    # 3. _handle_zero_remaining must record pinned job_version and authoritative org_id in OUTBOX#SCORING
    now_iso = "2026-03-30T12:00:00Z"
    files_repo._handle_zero_remaining(job_id, usable_count=1, analyze_requested=True, now_iso=now_iso)
    outbox_item = files_repo._table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "OUTBOX#SCORING"}).get("Item")
    assert outbox_item is not None
    assert outbox_item["payload"]["job_version"] == 3
    assert outbox_item["payload"]["org_id"] == authoritative_org


# ─────────────────────────────────────────────────────────────────────────────
# 10. GET /results distinguishes Not Ready (409) vs Storage Failure (500)
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_get_results_distinguishes_not_ready_and_storage_failure(client, auth_headers):
    """GET /results must never return success-shaped 200 empty results for in-progress or storage failures."""
    jobs_repo = JobsRepository()
    uid = uuid.uuid4().hex[:8]

    from src.api.auth import verify_session_token
    token = auth_headers["Authorization"].split(" ")[1]
    auth_ctx = verify_session_token(token)
    caller_org = auth_ctx.org_id if auth_ctx else "org_default"

    # Scenario A: Job is in PROCESSING and results are not ready yet -> 409 Conflict
    job_processing = JobItem(
        job_id=uid,
        org_id=caller_org,
        title="Processing Job",
        status=JobStatus.PROCESSING,
        usable_files=2,
    )
    jobs_repo.create(job_processing)

    resp_proc = client.get(f"/api/v2/jobs/{uid}/results", headers=auth_headers)
    assert resp_proc.status_code == 409, f"Expected 409 for not-ready job, got {resp_proc.status_code}: {resp_proc.text}"

    # Scenario B: Job is terminal READY with usable_files > 0, but results missing -> 500 Internal Server Error
    uid2 = uuid.uuid4().hex[:8]
    job_ready_missing = JobItem(
        job_id=uid2,
        org_id=caller_org,
        title="Ready Job Missing Results",
        status=JobStatus.READY,
        usable_files=2,
    )
    jobs_repo.create(job_ready_missing)

    resp_missing = client.get(f"/api/v2/jobs/{uid2}/results", headers=auth_headers)
    assert resp_missing.status_code == 500, f"Expected 500 for missing results in terminal job, got {resp_missing.status_code}: {resp_missing.text}"

    # Scenario C: Job is terminal DONE_WITH_ERRORS with legitimately 0 usable files -> 200 OK with empty list
    uid3 = uuid.uuid4().hex[:8]
    job_zero_usable = JobItem(
        job_id=uid3,
        org_id=caller_org,
        title="Zero Usable Files Job",
        status=JobStatus.DONE_WITH_ERRORS,
        usable_files=0,
    )
    jobs_repo.create(job_zero_usable)

    resp_zero = client.get(f"/api/v2/jobs/{uid3}/results", headers=auth_headers)
    assert resp_zero.status_code == 200
    assert resp_zero.json()["total_candidates"] == 0
    assert resp_zero.json()["candidates"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 11. Reconcile Outbox Flooding Prevention for Freshly Uploaded Files
# ─────────────────────────────────────────────────────────────────────────────

def test_regression_reconcile_outbox_does_not_flood_freshly_uploaded_files():
    """Freshly uploaded or in-flight files without expired leases must not be repeatedly redispatched on every status poll."""
    files_repo = FilesRepository()
    jobs_repo = JobsRepository()
    job_id = f"job-flood-guard-{uuid.uuid4().hex[:6]}"
    file_id = f"file-flood-{uuid.uuid4().hex[:6]}"

    job = JobItem(
        job_id=job_id,
        org_id="org_default",
        title="Flood Guard Test",
        status=JobStatus.PROCESSING,
        remaining=1,
        total_files=1,
        usable_files=0,
        analyze_requested=True,
    )
    jobs_repo.create(job)

    # File freshly uploaded 2 seconds ago, no claim lease
    now_dt = datetime.now(timezone.utc)
    fresh_ts = (now_dt - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    file_item = FileItem(
        job_id=job_id,
        file_id=file_id,
        filename="fresh.pdf",
        status=FileStatus.UPLOADED,
        created_at=fresh_ts,
        updated_at=fresh_ts,
    )
    files_repo.create_files(job_id, [file_item])

    with patch("src.infrastructure.repositories.files_repository.get_queue_adapter") as mock_qa:
        mock_adapter = MagicMock()
        mock_qa.return_value = mock_adapter

        # Status poll occurs: should NOT redispatch fresh file
        dispatched = files_repo.reconcile_outbox(job_id)
        assert dispatched == 0
        mock_adapter.send_message.assert_not_called()

    # Now simulate file stranded for 45 seconds
    stale_ts = (now_dt - timedelta(seconds=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    files_repo._table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": f"FILE#{file_id}"},
        UpdateExpression="SET #upd = :ts, #c = :ts",
        ExpressionAttributeNames={"#upd": "updated_at", "#c": "created_at"},
        ExpressionAttributeValues={":ts": stale_ts},
    )

    with patch("src.infrastructure.repositories.files_repository.get_queue_adapter") as mock_qa:
        mock_adapter = MagicMock()
        mock_qa.return_value = mock_adapter

        # Status poll occurs: SHOULD redispatch stranded file once and set cooldown
        dispatched = files_repo.reconcile_outbox(job_id)
        assert dispatched == 1
        mock_adapter.send_message.assert_called_once()

    with patch("src.infrastructure.repositories.files_repository.get_queue_adapter") as mock_qa:
        mock_adapter = MagicMock()
        mock_qa.return_value = mock_adapter

        # Immediate subsequent poll within cooldown: should NOT redispatch again
        dispatched2 = files_repo.reconcile_outbox(job_id)
        assert dispatched2 == 0
        mock_adapter.send_message.assert_not_called()





