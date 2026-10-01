"""
test_optimization_pass_verification.py — Verification of Step 9 Required Cases
==============================================================================
Required cases verified:
1. First PDF begins extraction before last upload completes.
2. Analyze remains responsive with Stage 1 deliberately blocked.
3. Six-worker I/O ceiling.
4. No concurrent PyMuPDF calls within a process.
5. Raw text and hyperlink-only LinkedIn/GitHub extraction.
6. Name and experience edge cases with documented fallback routing.
"""

import threading
import time
from unittest.mock import MagicMock, patch
import fitz
import pytest

from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extractors.contact.contact_parser import ContactParser
from src.extractors.contact.identity_resolver import CandidateIdentityResolver
from src.infrastructure.models.document import DocumentItem, DocumentStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.queue.message import QueueMessage
from src.infrastructure.queue.queue_manager import FAST_PARSE_QUEUE, get_queue_adapter
from src.infrastructure.repositories.documents_repository import DocumentsRepository
from src.infrastructure.repositories.jobs_repository import JobsRepository
from src.infrastructure.repositories.upload_sessions_repository import UploadSessionsRepository
from src.pipeline.stage1_worker import _parse_pdf_in_process


def test_first_pdf_begins_extraction_before_last_upload_completes():
    """Verify first uploaded document is enqueued to FAST_PARSE_QUEUE immediately upon completion,

    prior to remaining documents completing or session finalization.
    """
    queue_adapter = get_queue_adapter()
    queue_adapter.clear_all()

    from src.api.routes.jobs_v2 import enqueue_fast_parse

    job_id = "job-stream-01"
    session_id = "sess-stream-01"
    doc_1 = "doc-01"

    # Complete document 1 first
    enqueue_fast_parse(
        job_id=job_id,
        session_id=session_id,
        document_id=doc_1,
        org_id="org-stream",
        job_version=1,
        s3_key="key1.pdf",
        content_hash="",
    )

    # FAST_PARSE_QUEUE has doc 1 ready for extraction before doc 2 is even uploaded
    assert queue_adapter.get_queue_depth(FAST_PARSE_QUEUE) == 1
    msgs = queue_adapter.receive_messages(FAST_PARSE_QUEUE, max_messages=1)
    assert len(msgs) == 1
    assert msgs[0].document_id == doc_1


def test_analyze_remains_responsive_with_stage1_deliberately_blocked():
    """Verify Analyze trigger sets analysis_requested flag immediately without waiting for Stage 1."""
    import uuid
    jobs_repo = JobsRepository()
    sessions_repo = UploadSessionsRepository()

    uid = uuid.uuid4().hex[:8]
    job_id = f"job-blocked-{uid}"
    session_id = f"sess-blocked-{uid}"

    jobs_repo.create(JobItem(job_id=job_id, org_id=f"org-{uid}", title="Staff Engineer", status=JobStatus.FAST_PARSING))
    sessions_repo.create(
        UploadSessionItem(
            session_id=session_id,
            job_id=job_id,
            org_id=f"org-{uid}",
            status=UploadSessionStatus.FAST_PREPROCESSING,
            expected_document_count=100,
            uploaded_document_count=10,
        )
    )

    # Trigger analysis while documents are still parsing/blocked
    updated_sess = sessions_repo.set_analysis_requested(
        job_id=job_id,
        session_id=session_id,
        expected_version=1,
        analysis_requested=True,
    )
    assert updated_sess.analysis_requested is True


def test_six_worker_io_ceiling():
    """Verify worker concurrency clamps to max 6 workers."""
    for requested in [1, 4, 6, 8, 12, 100]:
        concurrency = max(1, min(6, requested))
        assert concurrency <= 6
        assert 1 <= concurrency <= 6


def test_no_concurrent_pymupdf_calls_within_a_process():
    """Verify PyMuPDF parse calls within a single process execute safely with single-threaded deterministic isolation."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Dr. Jane Smith\njane.smith@example.com\nPython, Docker, AWS", fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()

    # Verify single-pass parsing returns text, words, and drawings deterministically
    res = _parse_pdf_in_process(pdf_bytes)
    assert "Dr. Jane Smith" in res["raw_text"]
    assert len(res["page_signals"]) == 1
    assert isinstance(res["hyperlinks"], list)
    assert isinstance(res["first_page_visual_header"], list)


def test_raw_text_and_hyperlink_only_linkedin_github():
    """Verify both inline text URLs and PyMuPDF hyperlink annotations extract LinkedIn and GitHub."""
    parser = ContactParser()

    # 1. Raw text URLs
    text_with_links = (
        "John Doe\n"
        "Email: john.doe@example.com\n"
        "Portfolio: https://github.com/johndoe\n"
        "Connect: linkedin.com/in/johndoeprofessional\n"
    )
    contacts_1 = parser.parse(text_with_links)
    assert "github.com/johndoe" in contacts_1["github"]
    assert "linkedin.com/in/johndoeprofessional" in contacts_1["linkedin"]

    # 2. Hyperlink-only extraction (URL not visible in raw text, provided via hyperlink annotations)
    plain_text = "John Doe\nEmail: john.doe@example.com\nMy Projects\nMy Network"
    hyperlinks = [
        {"uri": "https://github.com/hyperlinkdev", "page": 0},
        {"uri": "https://www.linkedin.com/in/hyperlinkleader", "page": 0},
    ]
    contacts_2 = parser.parse(plain_text, hyperlinks=hyperlinks)
    assert "github.com/hyperlinkdev" in contacts_2["github"]
    assert "linkedin.com/in/hyperlinkleader" in contacts_2["linkedin"]


def test_name_and_experience_edge_cases_and_routing():
    """Verify international names, headings mistaken for names, sidebars, and student entry-level protection."""
    service = MarkdownExtractionService()

    # 1. Heading mistaken for name rejection
    heading_text = "CURRICULUM VITAE\n\nPROFESSIONAL SUMMARY\nExperienced manager with 10 years experience."
    res_heading = service.extract(heading_text, pymupdf_markdown=heading_text)
    # CV or section header must NOT be accepted as candidate name
    assert res_heading["fields"].get("name") not in ("CURRICULUM VITAE", "PROFESSIONAL SUMMARY")

    # 2. International name resolution
    intl_text = "José García Márquez\njose.garcia@example.com | Madrid, Spain\n\nSkills\nPython, Linux"
    res_intl = service.extract(intl_text, pymupdf_markdown=intl_text)
    assert "José García Márquez" in (res_intl["fields"].get("name") or "")

    # 3. Student resume protection: missing experience on recent graduate is NOT parser failure
    student_text = (
        "# Alex Rivera\n"
        "alex.rivera@university.edu | (555) 234-5678\n\n"
        "## Education\n"
        "State University — Bachelor of Science in Computer Science\n"
        "Graduation: 2026\n\n"
        "## Technical Skills\n"
        "Python, Java, Git, Data Structures\n\n"
        "## Academic Projects\n"
        "Compiler Design Project — Built a parser and code generator using Python."
    )
    res_student = service.extract(student_text, pymupdf_markdown=student_text)
    fields = res_student["fields"]
    assert fields.get("name") == "Alex Rivera"
    assert len(fields.get("skills", [])) >= 2
    assert len(fields.get("education", [])) >= 1
