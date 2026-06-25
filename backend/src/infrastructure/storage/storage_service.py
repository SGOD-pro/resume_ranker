"""
storage_service.py — S3 storage operations
=============================================
Six methods, one for each storage operation.
All S3 keys follow: jobs/{job_id}/{type}/{id}.{ext}

Bucket name and endpoint are read from AWSSettings.
"""

import json
import logging
from typing import Any, Dict

import boto3

from src.config.aws import get_boto3_kwargs, get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """S3 storage for resumes, extraction JSON, and ranking JSON."""

    def __init__(self) -> None:
        self._client = boto3.client("s3", **get_boto3_kwargs())
        self._bucket = get_settings().s3_bucket_name

    # ── Resume PDFs ───────────────────────────────────────────────────────

    def upload_resume(
        self,
        job_id: str,
        document_id: str,
        file_content: bytes,
        filename: str,
    ) -> str:
        """Upload a resume PDF to S3.

        Args:
            job_id: Parent job UUID.
            document_id: Document UUID.
            file_content: Raw PDF bytes.
            filename: Original filename (stored as metadata, not in key).

        Returns:
            The S3 object key.
        """
        s3_key = f"jobs/{job_id}/resumes/{document_id}.pdf"
        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=file_content,
            ContentType="application/pdf",
            Metadata={"original-filename": filename},
        )
        logger.info("Uploaded resume: s3://%s/%s (%d bytes)", self._bucket, s3_key, len(file_content))
        return s3_key

    def get_resume(self, job_id: str, document_id: str) -> bytes:
        """Download a resume PDF from S3.

        Returns:
            Raw PDF bytes.
        """
        s3_key = f"jobs/{job_id}/resumes/{document_id}.pdf"
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        data = response["Body"].read()
        logger.info("Downloaded resume: s3://%s/%s (%d bytes)", self._bucket, s3_key, len(data))
        return data

    # ── Extraction JSON ───────────────────────────────────────────────────

    def upload_extracted_json(
        self,
        job_id: str,
        document_id: str,
        data: Dict[str, Any],
    ) -> str:
        """Upload extraction result JSON to S3.

        Args:
            job_id: Parent job UUID.
            document_id: Document UUID.
            data: Extraction result dict (fields, metadata, etc.).

        Returns:
            The S3 object key.
        """
        s3_key = f"jobs/{job_id}/extracted/{document_id}.json"
        body = json.dumps(data, ensure_ascii=False, default=str)
        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Uploaded extraction: s3://%s/%s", self._bucket, s3_key)
        return s3_key

    def get_extracted_json(self, job_id: str, document_id: str) -> Dict[str, Any]:
        """Download and parse extraction result JSON from S3.

        Returns:
            Parsed dict of extraction results.
        """
        s3_key = f"jobs/{job_id}/extracted/{document_id}.json"
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        body = response["Body"].read().decode("utf-8")
        logger.info("Downloaded extraction: s3://%s/%s", self._bucket, s3_key)
        return json.loads(body)

    # ── Ranking JSON ──────────────────────────────────────────────────────

    def upload_ranking(
        self,
        job_id: str,
        scoring_id: str,
        data: Any,
    ) -> str:
        """Upload full ranking results JSON to S3.

        Args:
            job_id: Parent job UUID.
            scoring_id: Scoring run UUID.
            data: Full List[ScoredCandidate] as dicts.

        Returns:
            The S3 object key.
        """
        s3_key = f"jobs/{job_id}/scoring/{scoring_id}.json"
        body = json.dumps(data, ensure_ascii=False, default=str)
        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Uploaded ranking: s3://%s/%s", self._bucket, s3_key)
        return s3_key

    def get_ranking(self, job_id: str, scoring_id: str) -> Dict[str, Any]:
        """Download and parse ranking results JSON from S3.

        Returns:
            Parsed ranking results (usually a list of ScoredCandidate dicts).
        """
        s3_key = f"jobs/{job_id}/scoring/{scoring_id}.json"
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        body = response["Body"].read().decode("utf-8")
        logger.info("Downloaded ranking: s3://%s/%s", self._bucket, s3_key)
        return json.loads(body)
