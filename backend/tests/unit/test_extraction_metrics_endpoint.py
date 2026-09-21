"""
test_extraction_metrics_endpoint.py — Unit tests for GET /jobs/{job_id}/extraction-metrics
========================================================================================
Validates:
1. Retrieval of aggregate extraction metrics across documents in a job.
2. Correct calculation of average quality, identity status counts, and unresolved rate.
3. Summary timing aggregations (download_ms, structure_ms, deterministic_ms, nova_ms, total_ms).
4. Per-document metadata breakdown.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.infrastructure.models.document import DocumentItem, DocumentStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_extraction_metrics_endpoint(client):
    job_id = "test-job-metrics-123"

    mock_job = MagicMock()
    mock_job.job_id = job_id
    mock_job.org_id = "org_default"

    # Create 3 sample documents: 2 extracted (1 verified, 1 unresolved), 1 failed
    doc1 = DocumentItem(
        job_id=job_id,
        document_id="doc-1",
        filename="alice.pdf",
        content_hash="hash1",
        s3_pdf_key="pdf1",
        s3_extracted_key="json1",
        status=DocumentStatus.PARSED,
        extraction_quality=0.92,
        candidate_name="Alice Smith",
        page_count=2,
    )
    doc2 = DocumentItem(
        job_id=job_id,
        document_id="doc-2",
        filename="mystery.pdf",
        content_hash="hash2",
        s3_pdf_key="pdf2",
        s3_extracted_key="json2",
        status=DocumentStatus.PARSED,
        extraction_quality=0.45,
        candidate_name=None,
        page_count=1,
    )
    doc3 = DocumentItem(
        job_id=job_id,
        document_id="doc-3",
        filename="corrupted.pdf",
        content_hash="hash3",
        s3_pdf_key="pdf3",
        s3_extracted_key=None,
        status=DocumentStatus.PARSE_FAILED,
        extraction_quality=0.0,
        candidate_name=None,
        page_count=0,
    )

    doc1_json = {
        "name": "Alice Smith",
        "identity": {"status": "VERIFIED", "confidence": 0.95},
        "_timings": {
            "download_ms": 50.0,
            "structure_ms": 120.0,
            "deterministic_ms": 30.0,
            "nova_ms": 0.0,
            "total_ms": 200.0,
        }
    }
    doc2_json = {
        "name": None,
        "identity": {"status": "UNRESOLVED", "confidence": 0.0},
        "_timings": {
            "download_ms": 40.0,
            "structure_ms": 180.0,
            "deterministic_ms": 40.0,
            "nova_ms": 250.0,
            "total_ms": 510.0,
        }
    }

    with patch("src.api.routes.jobs_v2._jobs_repo.get", return_value=mock_job), \
         patch("src.api.routes.jobs_v2._docs_repo.list_for_job", return_value=[doc1, doc2, doc3]), \
         patch("src.api.routes.jobs_v2._storage.get_extracted_json", side_effect=lambda jid, did: doc1_json if did == "doc-1" else doc2_json):

        response = client.get(f"/api/v2/jobs/{job_id}/extraction-metrics")
        assert response.status_code == 200
        data = response.json()

        assert data["job_id"] == job_id
        assert data["total_documents"] == 3
        assert data["extracted_count"] == 2
        assert data["failed_count"] == 1
        assert data["pending_count"] == 0

        # Quality: (0.92 + 0.45) / 2 = 0.685
        assert data["avg_quality_score"] == pytest.approx(0.685, 0.001)

        # Identity counts: 1 verified, 0 plausible, 1 unresolved -> unresolved_rate = 1/2 = 0.5
        assert data["identity_metrics"]["verified_count"] == 1
        assert data["identity_metrics"]["unresolved_count"] == 1
        assert data["identity_metrics"]["unresolved_rate"] == 0.5

        # Timings
        timings = data["timings_summary"]
        assert timings["download_ms"] == pytest.approx(45.0, 0.1)
        assert timings["structure_ms"] == pytest.approx(150.0, 0.1)
        assert timings["deterministic_ms"] == pytest.approx(35.0, 0.1)
        assert timings["nova_ms"] == pytest.approx(125.0, 0.1)

        # Per-document items
        docs = data["documents"]
        assert len(docs) == 3
        d1 = next(d for d in docs if d["document_id"] == "doc-1")
        assert d1["candidate_name"] == "Alice Smith"
        assert d1["identity_status"] == "VERIFIED"
        assert d1["timings"]["download_ms"] == 50.0

        d2 = next(d for d in docs if d["document_id"] == "doc-2")
        assert d2["candidate_name"] is None
        assert d2["identity_status"] == "UNRESOLVED"

        d3 = next(d for d in docs if d["document_id"] == "doc-3")
        assert d3["status"] == DocumentStatus.PARSE_FAILED.value
