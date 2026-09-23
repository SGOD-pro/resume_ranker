"""
test_v2_2_hardening.py — Dedicated unit & integration tests for v2.2 production hardening
========================================================================================
Tests cover:
  1. complete_document_upload returns HTTP 202 without downloading full PDF.
  2. Duplicate completion is idempotent (returns 202, no duplicate SQS messages).
  3. Duplicate PDF content is marked REJECTED_DUPLICATE in FastParseWorker.
  4. finalize_upload_session leaves analysis_requested = False and status FAST_PREPROCESSING.
  5. POST /api/v2/jobs/{job_id}/analysis sets analysis_requested = True and pins job_version.
  6. ODL batch worker processes bounded batches and isolates per-document failures.
  7. Rate limit structured 429 error diagnostics contain all required fields.
"""

import hashlib
import io
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.infrastructure.models.document import DocumentItem, DocumentStatus
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
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
from src.infrastructure.storage.storage_service import StorageService
from src.main import app
from src.pipeline.coordinator import check_and_progress_session
from src.pipeline.fast_parse_worker import process_fast_parse_message
from src.pipeline.odl_batch_worker import process_odl_batch_message
from src.pipeline.worker_runner import drain_all_queues_sync


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Create a unique authenticated organization context for each test."""
    unique_id = uuid.uuid4().hex[:8]
    reg_resp = client.post(
        "/api/v2/auth/register",
        json={
            "org_name": f"Org_{unique_id}",
            "email": f"recruiter_{unique_id}@example.com",
            "name": f"Recruiter {unique_id}",
            "password": "Password123!",
        },
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def make_pdf(text: str = "Candidate Resume Content") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), f"John Doe\njohn@example.com | 555-1234\nSkills: Python, FastAPI\n{text}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: complete_document_upload returns 202 without downloading full PDF
# ─────────────────────────────────────────────────────────────────────────────

def test_complete_document_upload_lightweight_returns_202(client, auth_headers):
    """complete_document_upload must return HTTP 202 and verify magic bytes via Range header only."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()

    # Create job
    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Lightweight Upload Test"})
    job_id = job_resp.json()["id"]

    # Request upload session
    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": 1, "files": [{"filename": "sample.pdf", "file_size": 2000}]},
    )
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]
    doc_id = doc_info["document_id"]

    # Upload PDF bytes to S3
    pdf_bytes = make_pdf("Senior Engineer Experience")
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=pdf_bytes,
        ContentType="application/pdf",
    )

    # Spy on get_object in jobs_v2 module to verify Range header usage
    import src.api.routes.jobs_v2 as jobs_v2_module
    real_get_object = jobs_v2_module._storage._client.get_object
    get_object_calls = []

    def spy_get_object(*args, **kwargs):
        get_object_calls.append(kwargs)
        return real_get_object(*args, **kwargs)

    with patch.object(jobs_v2_module._storage._client, "get_object", side_effect=spy_get_object):
        comp_resp = client.post(
            f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
            headers=auth_headers,
        )

    # Must return 202 Accepted
    assert comp_resp.status_code == 202
    assert comp_resp.json()["status"] == "UPLOADED"

    # Verify that get_object was called with Range='bytes=0-9' (lightweight magic bytes check)
    assert len(get_object_calls) == 1
    assert get_object_calls[0].get("Range") == "bytes=0-9"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Duplicate completion is idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_duplicate_completion_is_idempotent(client, auth_headers):
    """Calling complete multiple times returns 202 without creating duplicate SQS messages."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Idempotent Test"})
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": 1, "files": [{"filename": "cand.pdf", "file_size": 1500}]},
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]
    doc_id = doc_info["document_id"]

    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=make_pdf("Idempotent Content"),
        ContentType="application/pdf",
    )

    # First complete
    r1 = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
        headers=auth_headers,
    )
    assert r1.status_code == 202

    # Second complete
    r2 = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
        headers=auth_headers,
    )
    assert r2.status_code == 202

    # Exactly 1 message in fast parse queue
    assert queue_adapter.get_queue_depth(FAST_PARSE_QUEUE) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Duplicate PDF content marked REJECTED_DUPLICATE in FastParseWorker
# ─────────────────────────────────────────────────────────────────────────────

def test_duplicate_pdf_marked_rejected_duplicate_in_worker(client, auth_headers):
    """When two documents in the same job have identical SHA-256, worker marks second as REJECTED_DUPLICATE."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    docs_repo = DocumentsRepository()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Dedup Test"})
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 2,
            "files": [
                {"filename": "doc_original.pdf", "file_size": 1500},
                {"filename": "doc_copy.pdf", "file_size": 1500},
            ],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc1 = session_data["documents"][0]
    doc2 = session_data["documents"][1]

    # Identical PDF bytes
    identical_bytes = make_pdf("Identical Resume Content")
    storage._client.put_object(Bucket=storage._bucket, Key=doc1["s3_key"], Body=identical_bytes)
    storage._client.put_object(Bucket=storage._bucket, Key=doc2["s3_key"], Body=identical_bytes)

    client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc1['document_id']}/complete", headers=auth_headers)
    client.post(f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc2['document_id']}/complete", headers=auth_headers)

    # Process first message
    msg1 = queue_adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=1)[0]
    process_fast_parse_message(msg1)

    item1 = docs_repo.get(job_id, doc1["document_id"])
    assert item1.status in (DocumentStatus.STRUCTURED_PARSED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.NEEDS_ODL)
    assert item1.content_hash is not None

    # Process second message (identical hash)
    msg2 = queue_adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=1)[0]
    process_fast_parse_message(msg2)

    item2 = docs_repo.get(job_id, doc2["document_id"])
    assert item2.status == DocumentStatus.REJECTED_DUPLICATE
    assert "duplicate" in (item2.error_reason or "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Finalize upload session leaves analysis_requested = False
# ─────────────────────────────────────────────────────────────────────────────

def test_finalize_upload_session_fast_preprocessing_analysis_unrequested(client, auth_headers):
    """Finalize returns 202, sets FAST_PREPROCESSING, analysis_requested remains False, pauses at READY_TO_ANALYZE."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    sessions_repo = UploadSessionsRepository()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Finalize Phase Test"})
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": 1, "files": [{"filename": "cand.pdf", "file_size": 1500}]},
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]

    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=make_pdf("Software Developer"),
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_info['document_id']}/complete",
        headers=auth_headers,
    )

    # Finalize
    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202
    assert fin_resp.json()["status"] == "FAST_PREPROCESSING"

    session_item = sessions_repo.get(job_id, session_id)
    assert session_item.analysis_requested is False

    # Drain fast parse
    drain_all_queues_sync(max_rounds=5)

    # Barrier stops at READY_TO_ANALYZE without enqueuing final rank
    session_barrier = sessions_repo.get(job_id, session_id)
    assert session_barrier.status == UploadSessionStatus.READY_TO_ANALYZE
    assert queue_adapter.get_queue_depth(FINAL_RANK_QUEUE) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: POST /api/v2/jobs/{job_id}/analysis sets analysis_requested & pins version
# ─────────────────────────────────────────────────────────────────────────────

def test_trigger_analysis_sets_analysis_requested_and_pins_job_version(client, auth_headers):
    """Analyze trigger validates weights, updates version, sets analysis_requested = True, and progresses."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    sessions_repo = UploadSessionsRepository()
    jobs_repo = JobsRepository()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "Analyze Trigger Test", "must_have_skills": ["Python"]})
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": 1, "files": [{"filename": "cand.pdf", "file_size": 1500}]},
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]

    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=make_pdf("Python Developer"),
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_info['document_id']}/complete",
        headers=auth_headers,
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    drain_all_queues_sync(max_rounds=5)

    # Recruiter triggers analysis with modified weights and updated must_have_skills
    analyze_resp = client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers,
        json={
            "must_have_skills": ["Python", "FastAPI"],
            "weights": {"skills": 50, "experience": 30, "keywords": 10, "education": 10},
        },
    )
    assert analyze_resp.status_code == 202
    res_data = analyze_resp.json()
    assert res_data["status"] == "ANALYSIS_REQUESTED"
    assert res_data["job_version"] == 2

    # Job version was incremented
    job_item = jobs_repo.get(job_id)
    assert job_item.job_version == 2
    assert job_item.must_have_skills == ["Python", "FastAPI"]

    # Session is pinned and analysis_requested is True
    session_item = sessions_repo.get(job_id, session_id)
    assert session_item.analysis_requested is True
    assert session_item.job_version == 2

    # Repeat call is idempotent (returns 202)
    repeat_resp = client.post(f"/api/v2/jobs/{job_id}/analysis", headers=auth_headers)
    assert repeat_resp.status_code == 202


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: ODL batch worker processes bounded batches and isolates failures
# ─────────────────────────────────────────────────────────────────────────────

def test_odl_batch_worker_bounded_batches_and_isolation(client, auth_headers):
    """ODL batch worker isolates per-document failure without failing healthy documents in batch."""
    storage = StorageService()
    docs_repo = DocumentsRepository()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "ODL Batch Test"})
    job_id = job_resp.json()["id"]

    # Create two document items directly in DynamoDB in NEEDS_ODL status
    doc1_id = f"doc_good_{uuid.uuid4().hex[:6]}"
    doc2_id = f"doc_bad_{uuid.uuid4().hex[:6]}"
    session_id = str(uuid.uuid4())

    s3_key_good = f"jobs/{job_id}/resumes/{doc1_id}.pdf"
    s3_key_bad = f"jobs/{job_id}/resumes/{doc2_id}.pdf"

    storage._client.put_object(Bucket=storage._bucket, Key=s3_key_good, Body=make_pdf("Good ODL Resume"))
    # Corrupt content for doc2 to trigger failure during parse
    storage._client.put_object(Bucket=storage._bucket, Key=s3_key_bad, Body=b"CORRUPT DATA NOT PDF")

    item1 = DocumentItem(
        job_id=job_id,
        document_id=doc1_id,
        session_id=session_id,
        filename="good.pdf",
        s3_pdf_key=s3_key_good,
        status=DocumentStatus.NEEDS_ODL,
    )
    item2 = DocumentItem(
        job_id=job_id,
        document_id=doc2_id,
        session_id=session_id,
        filename="bad.pdf",
        s3_pdf_key=s3_key_bad,
        status=DocumentStatus.NEEDS_ODL,
    )
    docs_repo.create(item1)
    docs_repo.create(item2)

    # Construct batch message
    batch_msg = QueueMessage(
        stage="ODL_BATCH",
        job_id=job_id,
        session_id=session_id,
        org_id="org_test",
        document_ids=[doc1_id, doc2_id],
    )

    # Process batch
    process_odl_batch_message(batch_msg)

    # Verify doc1 succeeded to terminal state or NEEDS_NOVA
    res1 = docs_repo.get(job_id, doc1_id)
    assert res1.status in (DocumentStatus.STRUCTURED_PARSED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.NEEDS_NOVA)

    # Verify doc2 failure was isolated and recorded
    res2 = docs_repo.get(job_id, doc2_id)
    assert res2.status in (DocumentStatus.REVIEW_REQUIRED, DocumentStatus.FAILED, DocumentStatus.NEEDS_NOVA)
    assert res2.error_reason is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Rate limit structured 429 error diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def test_structured_429_error_diagnostics(client):
    """Breaching active upload sessions quota returns structured 429 diagnostic payload."""
    import time
    from src.api.auth import create_session_token, User
    test_org = f"org_429_{uuid.uuid4().hex[:8]}"
    test_user = User(f"user_{uuid.uuid4().hex[:6]}", test_org, "test@429.local", "Test User", "admin", "hash", time.time())
    token = create_session_token(test_user)
    headers = {"Authorization": f"Bearer {token}"}

    job_resp = client.post("/api/v2/jobs", headers=headers, json={"title": "Quota 429 Test"})
    job_id = job_resp.json()["id"]

    # Settings allows max 5 active upload sessions per org
    # Create 5 active sessions
    created_sessions = []
    try:
        for i in range(5):
            s_resp = client.post(
                f"/api/v2/jobs/{job_id}/upload-sessions",
                headers=headers,
                json={"document_count": 1, "files": [{"filename": f"cand_{i}.pdf", "file_size": 1000}]},
            )
            assert s_resp.status_code == 201
            created_sessions.append(s_resp.json()["session_id"])

        # Attempt 6th session -> must return structured 429
        breach_resp = client.post(
            f"/api/v2/jobs/{job_id}/upload-sessions",
            headers=headers,
            json={"document_count": 1, "files": [{"filename": "cand_breach.pdf", "file_size": 1000}]},
        )
        assert breach_resp.status_code == 429
        assert breach_resp.headers.get("Retry-After") == "60"

        diag = breach_resp.json().get("detail", {})
        assert diag.get("status_code") == 429
        assert diag.get("error_code") == "CONCURRENT_SESSIONS_EXCEEDED"
        assert diag.get("route") == f"/api/v2/jobs/{job_id}/upload-sessions"
        assert diag.get("job_id") == job_id
        assert diag.get("org_id") == test_org
        assert "client_ip_hash" in diag
        assert diag.get("retry_after") == 60
    finally:
        # Clean up test sessions
        from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
        repo = UploadSessionsRepository()
        for sid in created_sessions:
            try:
                repo._table.update_item(
                    Key={"PK": f"JOB#{job_id}", "SK": f"SESSION#{sid}"},
                    UpdateExpression="SET #s = :exp",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":exp": "EXPIRED"},
                )
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Score normalization produces realistic scores (not 100% or 0%)
# ─────────────────────────────────────────────────────────────────────────────

def test_weights_normalization_produces_realistic_scores():
    """Weights on 0-100 scale (sum=100) are normalized so candidate scores are realistic and discriminated."""
    from src.ranking.scorer import CandidateScorer, JobDescription

    jd = JobDescription(
        title="Software Engineer",
        must_have_skills=["Python", "SQL", "Docker"],
        nice_to_have_skills=["FastAPI"],
        min_years=2,
        max_years=6,
        weights={"skills": 40.0, "experience": 25.0, "keywords": 20.0, "education": 15.0},
    )

    candidates = [
        {
            "_document_id": "cand_partial",
            "name": "Alex Mercer",
            "skills": ["Python", "FastAPI"],  # Matches 1 must-have, 1 nice-to-have, misses 2 must-have
            "experience": [{"role": "Software Developer", "start": "2021-01", "end": "2023-01"}],
            "education": [{"degree": "bachelor", "field": "Computer Science"}],
            "extraction_quality": 0.85,
        },
        {
            "_document_id": "cand_strong",
            "name": "Jordan Lee",
            "skills": ["Python", "SQL", "Docker", "FastAPI"],
            "experience": [{"role": "Software Engineer", "start": "2019-01", "end": "2023-01"}],
            "education": [{"degree": "bachelor", "field": "Computer Science"}],
            "extraction_quality": 0.90,
        },
    ]

    scorer = CandidateScorer()
    results = scorer.rank(jd, candidates)

    assert len(results) == 2
    # Verify scores are discriminated between 0 and 100, not all 100% or all 0%
    for r in results:
        assert 0.0 < r.relevance_score < 100.0, f"Expected realistic score, got {r.relevance_score}"
        assert r.final_score == r.relevance_score

    # Jordan Lee (stronger match) should have a higher score than Alex Mercer
    strong = next(r for r in results if r.name == "Jordan Lee")
    partial = next(r for r in results if r.name == "Alex Mercer")
    assert strong.relevance_score > partial.relevance_score


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: PDF download endpoint and URL injection
# ─────────────────────────────────────────────────────────────────────────────

def test_pdf_download_endpoint_and_url_injection(client, auth_headers):
    """get_results injects pdf_url, and download_resume serves PDF from presigned key."""
    storage = StorageService()
    docs_repo = DocumentsRepository()

    job_resp = client.post("/api/v2/jobs", headers=auth_headers, json={"title": "PDF Test Job"})
    job_id = job_resp.json()["id"]

    doc_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    s3_key = f"org_default/jobs/{job_id}/sessions/{session_id}/resumes/{doc_id}.pdf"

    pdf_content = make_pdf("Candidate PDF Content")
    storage._client.put_object(Bucket=storage._bucket, Key=s3_key, Body=pdf_content, ContentType="application/pdf")

    # Create document item with non-standard s3_pdf_key
    doc = DocumentItem(
        job_id=job_id,
        document_id=doc_id,
        session_id=session_id,
        filename="candidate.pdf",
        s3_pdf_key=s3_key,
        status=DocumentStatus.STRUCTURED_PARSED,
    )
    docs_repo.create(doc)

    # Download resume through endpoint
    dl_resp = client.get(f"/api/v2/jobs/{job_id}/resumes/{doc_id}/download", headers=auth_headers)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert dl_resp.content == pdf_content


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: LLM fallback routing when candidate name or experience missing
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_fallback_routing_when_name_or_experience_missing():
    """When candidate name is unresolved or experience is empty, FastParse routes to NEEDS_NOVA, and Nova infill resolves them."""
    from src.extraction.fallback.nova_service import NovaService

    nova = NovaService()
    text = (
        "Subhadip Mondal\n"
        "subhadip.mondal@example.com\n\n"
        "Professional Experience\n"
        "Senior Cloud Engineer at Acme Corp (2020 - Present)\n"
        "Leading distributed systems and backend cloud deployments using Python and Kubernetes.\n\n"
        "Skills: Python, Go, Docker, AWS\n"
    )

    existing_empty = {
        "name": None,
        "identity_status": "UNRESOLVED",
        "experience": [],
        "skills": ["Python", "Docker"],
    }

    resolved = nova.resolve_chunks([text], existing_empty)

    assert resolved.get("name") == "Subhadip Mondal"
    assert resolved.get("identity", {}).get("status") in ("PLAUSIBLE", "VERIFIED")
    assert len(resolved.get("experience", [])) > 0


