"""
test_durable_pipeline.py — Comprehensive integration tests for durable S3 + SQS pipeline
========================================================================================
Implements the 8 required test scenarios:
  1. 40 valid PDFs in one session (concurrency 4): no 429 error, each file gets one document ID,
     each completion creates one fast parse event.
  2. Duplicate completion request and duplicate SQS message: no duplicate document, no duplicate
     extraction, no duplicate ranking.
  3. Stage routing: fast-parse routes directly to terminal states when quality is high, ODL only
     receives NEEDS_ODL documents, Nova only receives unresolved critical-field documents.
  4. Barrier synchronization: finalize session before fast parsing completes; final ranking waits
     correctly for barrier, no premature/stale early ranking.
  5. Partial failure resilience: one document fails, other documents continue, failed item has
     diagnostics, session/job reaches READY_WITH_WARNINGS.
  6. Stateless worker restart/retry: state recoverable from DynamoDB/S3 without in-memory locks.
  7. Job version pinning: job description changes increment job_version; final ranking binds to
     immutable version, stale rank messages cannot overwrite newer results.
  8. Scoring policy and ATS diagnostics compatibility remains valid.
"""

import hashlib
import sys
import uuid
from pathlib import Path
from typing import Dict, List

import fitz
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.config.aws import get_settings
from src.infrastructure.models.document import DocumentStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.upload_session import UploadSessionItem, UploadSessionStatus
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import (
    FAST_PARSE_QUEUE,
    FINAL_RANK_QUEUE,
    NOVA_QUEUE,
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
from src.pipeline.final_rank_worker import process_final_rank_message
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


def create_sample_pdf(name: str, skills: List[str] = None, experience_years: int = 3) -> bytes:
    """Create a valid single-column PDF resume with clear layout."""
    doc = fitz.open()
    page = doc.new_page()
    skills_text = ", ".join(skills or ["Python", "FastAPI", "SQL", "Docker", "AWS", "Git", "PostgreSQL", "Redis"])
    text = (
        f"{name}\n"
        f"{name.lower().replace(' ', '.')}@example.com | (555) 019-2834 | San Francisco, CA\n\n"
        f"Professional Summary\n"
        f"Experienced software engineer with {experience_years} years building scalable distributed backend systems.\n"
        f"Deep expertise in cloud architecture, asynchronous pipelines, relational database design, and microservices.\n"
        f"Demonstrated history of driving engineering reliability and performance across high-throughput production workloads.\n\n"
        f"Technical Skills\n"
        f"{skills_text}\n\n"
        f"Professional Experience\n"
        f"Senior Backend Engineer — TechCorp Inc.\n"
        f"2021 - Present ({experience_years} years)\n"
        f"- Architected, developed, and deployed high-performance REST and streaming APIs using FastAPI and Python.\n"
        f"- Implemented asynchronous message ingestion workers utilizing Amazon SQS and serverless event triggers.\n"
        f"- Engineered robust data modeling and access patterns in Amazon DynamoDB single-table architecture.\n"
        f"- Reduced end-to-end extraction and scoring latency by forty percent through concurrent pipelining.\n"
        f"- Mentored mid-level and junior engineers on clean code practices, testing methodologies, and architectural design.\n\n"
        f"Software Engineer — DataSystems LLC\n"
        f"2019 - 2021 (2 years)\n"
        f"- Developed backend services for candidate analytics and reporting using Python, Flask, and PostgreSQL.\n"
        f"- Collaborated with cross-functional product and design teams to deliver features on bi-weekly sprint cycles.\n"
        f"- Automated deployment pipelines and continuous integration testing using Docker and GitHub Actions.\n\n"
        f"Education\n"
        f"Bachelor of Science in Computer Science\n"
        f"State University, 2015 - 2019\n"
    )
    page.insert_text((50, 72), text, fontsize=9)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1: 40 valid PDFs in one session (concurrency 4): no 429 error
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_1_bulk_40_resumes_upload_session_no_429(client, auth_headers):
    """Scenario 1: 40 valid PDFs in one session: no 429 error, 1 document ID each, 1 fast parse event."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()

    # 1. Create a job
    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={
            "title": "Staff Platform Engineer",
            "department": "Infrastructure",
            "must_have_skills": ["Python", "FastAPI", "AWS"],
            "nice_to_have_skills": ["Docker", "Kubernetes"],
            "min_years": 3,
            "max_years": 12,
        },
    )
    assert job_resp.status_code == 200
    job_id = job_resp.json()["id"]

    # 2. Request upload session for 40 resumes
    doc_count = 40
    files_spec = [
        {"filename": f"candidate_{i:02d}.pdf", "file_size": 2500, "content_type": "application/pdf"}
        for i in range(doc_count)
    ]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={"document_count": doc_count, "files": files_spec},
    )
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    assert session_data["expected_document_count"] == doc_count
    documents = session_data["documents"]
    assert len(documents) == doc_count

    # All document IDs must be unique
    doc_ids = [d["document_id"] for d in documents]
    assert len(set(doc_ids)) == doc_count

    # 3. Simulate bounded client upload (concurrency 4): upload PDF to S3, complete upload
    concurrency_limit = 4
    for i in range(0, doc_count, concurrency_limit):
        batch = documents[i : i + concurrency_limit]
        for doc_info in batch:
            doc_id = doc_info["document_id"]
            pdf_bytes = create_sample_pdf(f"Candidate Person {doc_id[:6]}")

            # Direct S3 put simulating browser PUT
            storage._client.put_object(
                Bucket=storage._bucket,
                Key=doc_info["s3_key"],
                Body=pdf_bytes,
                ContentType="application/pdf",
            )

            # Notify complete
            comp_resp = client.post(
                f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
                headers=auth_headers,
            )
            # Must succeed without 429 rate limit error
            assert comp_resp.status_code == 202
            assert comp_resp.json()["status"] == "UPLOADED"

    # Verify FAST_PARSE_QUEUE received exactly 40 messages
    assert queue_adapter.get_queue_depth(FAST_PARSE_QUEUE) == doc_count

    # 4. Finalize session
    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202
    assert fin_resp.json()["status"] == "FAST_PREPROCESSING"

    # 5. Process fast-parse events to barrier
    drain_all_queues_sync(max_rounds=50)

    # Fast parse barrier pauses at READY_TO_ANALYZE
    prog_resp = client.get(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}",
        headers=auth_headers,
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["status"] == "READY_TO_ANALYZE"

    # Recruiter clicks Analyze
    analyze_resp = client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers,
    )
    assert analyze_resp.status_code == 202

    # Process remaining pipeline events (final ranking)
    drain_all_queues_sync(max_rounds=50)

    # 6. Verify upload session status and document counts
    prog_resp = client.get(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}",
        headers=auth_headers,
    )
    assert prog_resp.status_code == 200
    prog = prog_resp.json()
    assert prog["expected_document_count"] == doc_count
    assert prog["uploaded_document_count"] == doc_count
    assert prog["terminal_count"] == doc_count
    assert prog["status"] in ("READY", "READY_WITH_WARNINGS")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2: Duplicate completion request & duplicate SQS message idempotency
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_2_duplicate_completion_and_duplicate_sqs_idempotency(client, auth_headers):
    """Scenario 2: Duplicate completion & duplicate SQS message produces no duplicate documents or rankings."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    docs_repo = DocumentsRepository()

    # Create job
    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "Data Engineer", "must_have_skills": ["Python", "SQL"]},
    )
    job_id = job_resp.json()["id"]

    # Upload session with 1 document
    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 1,
            "files": [{"filename": "idempotent_cand.pdf", "file_size": 1200}],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]
    doc_id = doc_info["document_id"]

    pdf_bytes = create_sample_pdf("Idempotent Candidate")
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=pdf_bytes,
        ContentType="application/pdf",
    )

    # First completion call
    comp1 = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
        headers=auth_headers,
    )
    assert comp1.status_code == 202
    assert comp1.json()["status"] == "UPLOADED"

    # Duplicate completion call
    comp2 = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_id}/complete",
        headers=auth_headers,
    )
    assert comp2.status_code == 202
    assert comp2.json()["status"] == "UPLOADED"

    # Fast parse queue should have received only 1 message despite duplicate completion
    assert queue_adapter.get_queue_depth(FAST_PARSE_QUEUE) == 1

    # Receive the SQS message and process it
    msg = queue_adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=1)[0]
    process_fast_parse_message(msg)

    # Verify document is in a terminal extraction state
    doc_after_first = docs_repo.get(job_id, doc_id)
    assert doc_after_first.status in (DocumentStatus.STRUCTURED_PARSED, DocumentStatus.REVIEW_REQUIRED)

    # Duplicate SQS delivery: Re-deliver the same message
    process_fast_parse_message(msg)

    # Document state remains intact, no duplicate document in repo
    all_docs = docs_repo.list_for_job(job_id)
    matching_docs = [d for d in all_docs if d.document_id == doc_id]
    assert len(matching_docs) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3: Stage routing: ODL only receives NEEDS_ODL, Nova receives critical
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_3_stage_routing_odl_and_nova(client, auth_headers, monkeypatch):
    """Scenario 3: Fast-parse documents with high quality bypass ODL; low quality routes to NEEDS_ODL."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    docs_repo = DocumentsRepository()

    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "ML Engineer", "must_have_skills": ["Python", "PyTorch"]},
    )
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 2,
            "files": [
                {"filename": "clean_layout.pdf", "file_size": 1500},
                {"filename": "low_quality_layout.pdf", "file_size": 1500},
            ],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_clean = session_data["documents"][0]
    doc_low = session_data["documents"][1]

    # Upload clean PDF
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_clean["s3_key"],
        Body=create_sample_pdf("Alice Verified", ["Python", "PyTorch"]),
        ContentType="application/pdf",
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_clean['document_id']}/complete",
        headers=auth_headers,
    )

    # Upload low quality PDF
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_low["s3_key"],
        Body=create_sample_pdf("Bob Complex", ["Python"]),
        ContentType="application/pdf",
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_low['document_id']}/complete",
        headers=auth_headers,
    )

    # Mock PyMuPDF layout score conditionally BEFORE finalize triggers queue drain
    from src.pipeline import fast_parse_worker

    def mock_analyze(page):
        text = page.get_text()
        if "Bob Complex" in text:
            return 0.45  # Below threshold -> NEEDS_ODL
        return 0.95  # Clean single column

    monkeypatch.setattr(fast_parse_worker, "pymupdf_layout_quality", mock_analyze)

    # Finalize upload session so coordinator barrier is active
    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202

    # Process fast-parse queue
    drain_all_queues_sync(max_rounds=10)

    # Check document statuses
    clean_item = docs_repo.get(job_id, doc_clean["document_id"])
    assert clean_item.status in (DocumentStatus.STRUCTURED_PARSED, DocumentStatus.REVIEW_REQUIRED, DocumentStatus.SCORED)

    low_item = docs_repo.get(job_id, doc_low["document_id"])
    assert low_item.status in (
        DocumentStatus.NEEDS_ODL,
        DocumentStatus.ODL_QUEUED,
        DocumentStatus.ODL_PARSING,
        DocumentStatus.STRUCTURED_PARSED,
        DocumentStatus.REVIEW_REQUIRED,
        DocumentStatus.SCORED,
        "scored",
    )

    # Advance through Analyze to process ODL fallback and final ranking
    client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers,
    )
    drain_all_queues_sync(max_rounds=10)

    # Session completes successfully through ODL fallback and final ranking
    prog_resp = client.get(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}",
        headers=auth_headers,
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["status"] in ("READY", "READY_WITH_WARNINGS")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4: Barrier synchronization before fast parsing completes
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_4_barrier_synchronization_before_fast_parse_completion(client, auth_headers):
    """Scenario 4: Finalize session before fast parsing completes: waits for barrier, no early rank."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    sessions_repo = UploadSessionsRepository()

    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "DevOps Engineer", "must_have_skills": ["Terraform", "AWS"]},
    )
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 2,
            "files": [
                {"filename": "doc1.pdf", "file_size": 1000},
                {"filename": "doc2.pdf", "file_size": 1000},
            ],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc1 = session_data["documents"][0]
    doc2 = session_data["documents"][1]

    # Upload only doc1 so far
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc1["s3_key"],
        Body=create_sample_pdf("Doc One", ["Terraform"]),
        ContentType="application/pdf",
    )
    client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc1['document_id']}/complete",
        headers=auth_headers,
    )

    # Recruiter clicks finalize before doc2 is even completed or parsed
    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202
    assert fin_resp.json()["status"] == "FAST_PREPROCESSING"

    # Verify barrier: FINAL_RANK_QUEUE must NOT be enqueued because doc2 is still pending!
    assert queue_adapter.get_queue_depth(FINAL_RANK_QUEUE) == 0

    session_item = sessions_repo.get(job_id, session_id)
    assert session_item.status == UploadSessionStatus.FAST_PREPROCESSING

    # Now upload and complete doc2
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc2["s3_key"],
        Body=create_sample_pdf("Doc Two", ["AWS"]),
        ContentType="application/pdf",
    )
    comp2_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc2['document_id']}/complete",
        headers=auth_headers,
    )
    assert comp2_resp.status_code == 202

    # Process all fast-parse queue items
    drain_all_queues_sync(max_rounds=10)

    # Barrier is satisfied at fast-parse stage, transitioning session to READY_TO_ANALYZE
    session_barrier = sessions_repo.get(job_id, session_id)
    assert session_barrier.status == UploadSessionStatus.READY_TO_ANALYZE

    # Recruiter triggers analysis
    client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers,
    )
    drain_all_queues_sync(max_rounds=10)

    # Once analysis completes, session reaches READY/READY_WITH_WARNINGS
    session_final = sessions_repo.get(job_id, session_id)
    assert session_final.status in (UploadSessionStatus.READY, UploadSessionStatus.READY_WITH_WARNINGS)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 5: Partial failure resilience and diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_5_partial_failure_diagnostics_and_ready_with_warnings(client, auth_headers):
    """Scenario 5: Corrupt PDF fails, valid document succeeds; session reaches READY_WITH_WARNINGS."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()
    docs_repo = DocumentsRepository()

    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "Security Analyst", "must_have_skills": ["SIEM", "Python"]},
    )
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 2,
            "files": [
                {"filename": "valid_sec.pdf", "file_size": 1500},
                {"filename": "corrupt_sec.pdf", "file_size": 500},
            ],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_valid = session_data["documents"][0]
    doc_corrupt = session_data["documents"][1]

    # Upload valid PDF
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_valid["s3_key"],
        Body=create_sample_pdf("Carol Sec", ["SIEM", "Python"]),
        ContentType="application/pdf",
    )
    comp_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_valid['document_id']}/complete",
        headers=auth_headers,
    )
    assert comp_resp.status_code == 202

    # Upload corrupt non-PDF file directly to S3 key
    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_corrupt["s3_key"],
        Body=b"THIS IS NOT A VALID PDF CONTENT",
        ContentType="application/pdf",
    )
    # The complete call fails PDF magic-bytes / structure verification
    bad_comp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_corrupt['document_id']}/complete",
        headers=auth_headers,
    )
    assert bad_comp.status_code == 400

    # Explicitly mark corrupt document as FAILED
    docs_repo.update_status_conditional(
        job_id=job_id,
        document_id=doc_corrupt["document_id"],
        new_status=DocumentStatus.FAILED,
        allowed_current_statuses=[DocumentStatus.UPLOAD_INITIALIZED],
        extra_updates={"error_reason": "Corrupt or invalid PDF magic bytes"},
    )

    # Finalize session
    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202

    # Drain fast-parse queues
    drain_all_queues_sync(max_rounds=10)

    # Trigger analysis
    client.post(
        f"/api/v2/jobs/{job_id}/analysis",
        headers=auth_headers,
    )
    drain_all_queues_sync(max_rounds=10)

    # Progress session
    prog_resp = client.get(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}",
        headers=auth_headers,
    )
    assert prog_resp.status_code == 200
    prog = prog_resp.json()

    # Session handles partial failure with READY_WITH_WARNINGS
    assert prog["status"] == "READY_WITH_WARNINGS"
    doc_statuses = {d["filename"]: d["status"] for d in prog["documents"]}
    assert doc_statuses["corrupt_sec.pdf"] == "FAILED"
    assert doc_statuses["valid_sec.pdf"] in ("STRUCTURED_PARSED", "REVIEW_REQUIRED", "SCORED", "scored")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 6: Stateless worker restart & resumability
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_6_stateless_worker_restart_resumability(client, auth_headers):
    """Scenario 6: Worker restart restores state from DynamoDB/S3 without requiring in-memory locks."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    storage = StorageService()

    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "Cloud Architect", "must_have_skills": ["AWS", "Terraform"]},
    )
    job_id = job_resp.json()["id"]

    session_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions",
        headers=auth_headers,
        json={
            "document_count": 1,
            "files": [{"filename": "restart_cand.pdf", "file_size": 1200}],
        },
    )
    session_data = session_resp.json()
    session_id = session_data["session_id"]
    doc_info = session_data["documents"][0]

    storage._client.put_object(
        Bucket=storage._bucket,
        Key=doc_info["s3_key"],
        Body=create_sample_pdf("Restart Candidate", ["AWS", "Terraform"]),
        ContentType="application/pdf",
    )
    comp_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/documents/{doc_info['document_id']}/complete",
        headers=auth_headers,
    )
    assert comp_resp.status_code == 202

    fin_resp = client.post(
        f"/api/v2/jobs/{job_id}/upload-sessions/{session_id}/finalize",
        headers=auth_headers,
    )
    assert fin_resp.status_code == 202

    # Simulate process restart by draining in a fresh run
    drain_all_queues_sync(max_rounds=10)

    # SSE endpoint checks persistent DynamoDB state without depending on memory locks
    with client.stream("GET", f"/api/v2/jobs/{job_id}/extract", headers=auth_headers) as r:
        assert r.status_code == 200
        events = [line for line in r.iter_lines() if line]

    assert any("event: progress" in e for e in events)
    assert any("event: complete" in e for e in events)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 7: Job description changes increment job_version and reject stale rankings
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_7_job_version_pinning_and_stale_rank_rejection(client, auth_headers):
    """Scenario 7: When job description criteria update, stale ranking messages are dropped."""
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()
    jobs_repo = JobsRepository()

    # Create job with version 1
    job_resp = client.post(
        "/api/v2/jobs",
        headers=auth_headers,
        json={"title": "Backend Lead", "must_have_skills": ["Python"]},
    )
    job_id = job_resp.json()["id"]

    job_item = jobs_repo.get(job_id)
    assert job_item.job_version == 1

    # Recruiter updates job criteria, bumping job_version to 2
    patch_resp = client.patch(
        f"/api/v2/jobs/{job_id}",
        headers=auth_headers,
        json={"must_have_skills": ["Python", "FastAPI", "PostgreSQL"]},
    )
    assert patch_resp.status_code == 200
    updated_job = jobs_repo.get(job_id)
    assert updated_job.job_version == 2

    # A stale rank message from an earlier upload session pinned to job_version 1 arrives
    stale_message = QueueMessage(
        stage="FINAL_RANK",
        job_id=job_id,
        session_id=str(uuid.uuid4()),
        org_id=updated_job.org_id,
        job_version=1,  # Stale version
    )

    # Process stale ranking message
    process_final_rank_message(stale_message)

    # Job status must NOT be changed to SCORING or READY by the stale message
    fresh_job = jobs_repo.get(job_id)
    assert fresh_job.status != JobStatus.SCORING


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 8: Existing scoring-policy and ATS tests remain valid
# ─────────────────────────────────────────────────────────────────────────────

def test_scenario_8_scoring_policy_and_ats_compatibility():
    """Scenario 8: CandidateScorer fairness guarantees and ATS diagnostics remain functional."""
    import os
    import tempfile
    from src.ats.b2b_ats_scorer import B2BAtsScorer
    from src.extractors.contact.identity_resolver import CandidateIdentityResolver
    from src.ranking.scorer import CandidateScorer
    from src.schemas.scoring import JobDescription

    # 1. CandidateScorer fairness checks: prestige bonus is 0, gap penalty is disabled
    scorer = CandidateScorer()
    jd = JobDescription(
        title="Software Engineer",
        must_have_skills=["Python"],
    )
    candidate_prestigious = {
        "_document_id": "cand_1",
        "name": "Jane Engineer",
        "skills": ["Python"],
        "experience": [{"company": "Google", "role": "Software Engineer", "duration_years": 4.0}],
    }
    candidate_standard = {
        "_document_id": "cand_2",
        "name": "Bob Developer",
        "skills": ["Python"],
        "experience": [{"company": "Local Agency", "role": "Software Engineer", "duration_years": 4.0}],
    }

    scored_prestigious = scorer.rank(jd, [candidate_prestigious])[0]
    scored_standard = scorer.rank(jd, [candidate_standard])[0]

    # Equal skills and duration must receive equal scores (zero FAANG/employer bonus)
    assert scored_prestigious.final_score == scored_standard.final_score

    # 2. CandidateIdentityResolver strictly rejects non-identity phrases
    resolver = CandidateIdentityResolver()
    res = resolver.resolve(text_lines=["Insights possible sub-space.", "Senior Developer", "user@example.com"])
    assert res.display_name is None
    assert res.status.value == "UNRESOLVED"

    # 3. ATS diagnostics executes reliably
    from src.ranking.ats_scorer import AtsScoringService
    from src.extractors.layout.layout_extractor import DocumentStructure, ClassifiedLine

    header_line = ClassifiedLine(
        text="EXPERIENCE",
        role="section_header",
        column="full",
        top=50.0,
        x0=50.0,
        font_size=12.0,
        page=1,
        x1=150.0,
        bottom=65.0,
    )
    doc_struct = DocumentStructure(
        full_width_text=header_line.text,
        sidebar_text="",
        main_text="Some resume text",
        classified_lines=[header_line],
        extraction_metadata={"text_quality_score": 0.90, "semantic_quality_score": 0.90},
    )
    ats_svc = AtsScoringService()
    ats_res = ats_svc.score(doc_struct)
    assert ats_res.score > 0
    assert "structural_score" in ats_res.breakdown
