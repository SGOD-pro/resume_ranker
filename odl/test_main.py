import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import boto3
from moto import mock_aws

# main.py is importable even without opendataloader_pdf (lazy import guard)
from main import lambda_handler


# ── Shared setup ──────────────────────────────────────────────────────────────

BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set fake AWS credentials so botocore doesn't look for real ones."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID",     "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN",    "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN",     "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION",    REGION)


def _make_s3():
    """Return a moto-backed S3 client with the test bucket pre-created."""
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    return client


def _mock_odl_convert(out_dir: Path, docs: dict):
    """
    Return a side_effect callable for mock_odl.convert that writes fake ODL
    output files.  *docs* is a mapping:
        {doc_id: {"md": "...", "json": [...], "images": {name: bytes}}}
    """
    def _convert(**kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        for doc_id, spec in docs.items():
            if "md" in spec:
                (out_dir / f"{doc_id}.md").write_text(spec["md"], encoding="utf-8")
            if "json" in spec:
                (out_dir / f"{doc_id}.json").write_bytes(
                    json.dumps(spec["json"]).encode()
                )
            for img_name, img_bytes in spec.get("images", {}).items():
                (out_dir / img_name).write_bytes(img_bytes)

    return _convert


# ── Test: single-doc flat payload ─────────────────────────────────────────────


@mock_aws
def test_payload_normalizer_single_doc():
    """Single-doc flat payload → images land under {prefix}/images/{doc_id}/."""
    s3 = _make_s3()
    s3.put_object(Bucket=BUCKET, Key="invoices/doc1.pdf", Body=b"fake-pdf")

    event = {
        "s3_bucket":   BUCKET,
        "s3_key":      "invoices/doc1.pdf",
        "document_id": "doc_123",
        "save_images": True,
    }

    with patch("main.opendataloader_pdf") as mock_odl:
        # Capture the out_dir that lambda_handler creates so we can write files there
        real_convert = None

        def side_effect(**kwargs):
            out_dir = Path(kwargs["output_dir"])
            _mock_odl_convert(out_dir, {
                "doc_123": {
                    "md": "Hello ![](doc_123-img_001.png)",
                    "json": [{"text": "Hello"}],
                    "images": {"doc_123-img_001.png": b"fake-image"},
                }
            })(**kwargs)

        mock_odl.convert.side_effect = side_effect

        result = lambda_handler(event, {})

    assert "results" in result, result
    assert len(result["results"]) == 1

    res = result["results"][0]
    assert res["document_id"] == "doc_123"

    # Canonical key: invoices/images/doc_123/doc_123-img_001.png
    expected_key = "invoices/images/doc_123/doc_123-img_001.png"
    expected_uri = f"s3://{BUCKET}/{expected_key}"

    assert res["image_s3_keys"] == [expected_uri], res["image_s3_keys"]

    # Image must be present in S3
    body = s3.get_object(Bucket=BUCKET, Key=expected_key)["Body"].read()
    assert body == b"fake-image"

    # Markdown must contain the rewritten s3:// URI
    assert expected_uri in res["markdown"], res["markdown"]


# ── Test: batch payload ───────────────────────────────────────────────────────


@mock_aws
def test_payload_normalizer_batch():
    """Batch payload → each doc's images live under its own prefix/images/ dir."""
    s3 = _make_s3()
    s3.put_object(Bucket=BUCKET, Key="invoices/doc1.pdf", Body=b"fake-pdf1")
    s3.put_object(Bucket=BUCKET, Key="resumes/doc2.pdf",  Body=b"fake-pdf2")

    event = {
        "documents": [
            {"s3_bucket": BUCKET, "s3_key": "invoices/doc1.pdf", "document_id": "doc1"},
            {"s3_bucket": BUCKET, "s3_key": "resumes/doc2.pdf",  "document_id": "doc2"},
        ],
        "save_images": True,
    }

    with patch("main.opendataloader_pdf") as mock_odl:
        def side_effect(**kwargs):
            out_dir = Path(kwargs["output_dir"])
            _mock_odl_convert(out_dir, {
                "doc1": {
                    "md": "Doc 1 ![](doc1-img_001.png)",
                    "json": [],
                    "images": {"doc1-img_001.png": b"img1"},
                },
                "doc2": {
                    "md": "Doc 2 ![](doc2-img_001.png)",
                    "json": [],
                    "images": {"doc2-img_001.png": b"img2"},
                },
            })(**kwargs)

        mock_odl.convert.side_effect = side_effect

        result = lambda_handler(event, {})

    assert len(result["results"]) == 2

    doc1_res = next(r for r in result["results"] if r["document_id"] == "doc1")
    doc2_res = next(r for r in result["results"] if r["document_id"] == "doc2")

    doc1_key = "invoices/images/doc1/doc1-img_001.png"
    doc2_key = "resumes/images/doc2/doc2-img_001.png"
    doc1_uri = f"s3://{BUCKET}/{doc1_key}"
    doc2_uri = f"s3://{BUCKET}/{doc2_key}"

    assert doc1_res["image_s3_keys"] == [doc1_uri]
    assert doc2_res["image_s3_keys"] == [doc2_uri]
    assert doc1_uri in doc1_res["markdown"]
    assert doc2_uri in doc2_res["markdown"]

    assert s3.get_object(Bucket=BUCKET, Key=doc1_key)["Body"].read() == b"img1"
    assert s3.get_object(Bucket=BUCKET, Key=doc2_key)["Body"].read() == b"img2"


# ── Test: save_images=False → no images ──────────────────────────────────────


@mock_aws
def test_no_images_when_save_images_false():
    """save_images=False → image_s3_keys is empty and markdown is untouched."""
    s3 = _make_s3()
    s3.put_object(Bucket=BUCKET, Key="jobs/j1/resumes/abc.pdf", Body=b"fake-pdf")

    event = {
        "s3_bucket":   BUCKET,
        "s3_key":      "jobs/j1/resumes/abc.pdf",
        "document_id": "abc",
        "save_images": False,
    }

    with patch("main.opendataloader_pdf") as mock_odl:
        def side_effect(**kwargs):
            out_dir = Path(kwargs["output_dir"])
            _mock_odl_convert(out_dir, {
                "abc": {"md": "Just text, no images.", "json": []}
            })(**kwargs)

        mock_odl.convert.side_effect = side_effect

        result = lambda_handler(event, {})

    res = result["results"][0]
    assert res["image_s3_keys"] == []
    assert res["markdown"] == "Just text, no images."


# ── Test: corrupt / missing output → failed list ──────────────────────────────


@mock_aws
def test_missing_output_marked_as_failed():
    """If ODL produces no .md or .json for a doc, it must appear in failed[]."""
    s3 = _make_s3()
    s3.put_object(Bucket=BUCKET, Key="resumes/bad.pdf", Body=b"fake-pdf")

    event = {
        "s3_bucket":   BUCKET,
        "s3_key":      "resumes/bad.pdf",
        "document_id": "bad_doc",
        "save_images": False,
    }

    with patch("main.opendataloader_pdf") as mock_odl:
        def side_effect(**kwargs):
            # Produce nothing — simulates a corrupt / unsupported PDF
            Path(kwargs["output_dir"]).mkdir(parents=True, exist_ok=True)

        mock_odl.convert.side_effect = side_effect

        result = lambda_handler(event, {})

    assert "bad_doc" in result["failed"]
    assert result["results"] == []
