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

from src.config.aws import get_client, get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """S3 storage for resumes, extraction JSON, and ranking JSON."""

    def __init__(self) -> None:
        self._client = get_client("s3")
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

    def generate_presigned_put_url(
        self,
        s3_key: str,
        content_type: str = "application/pdf",
        expires_in: int = 900,
    ) -> str:
        """Generate a presigned PUT URL for direct browser-to-S3 upload."""
        params = {
            "Bucket": self._bucket,
            "Key": s3_key,
            "ContentType": content_type,
        }
        url = self._client.generate_presigned_url(
            ClientMethod="put_object",
            Params=params,
            ExpiresIn=expires_in,
        )
        return url

    def generate_presigned_post(
        self,
        s3_key: str,
        content_type: str = "application/pdf",
        min_bytes: int = 1,
        max_bytes: int = 10 * 1024 * 1024,
        expires_in: int = 900,
    ) -> Dict[str, Any]:
        """Generate presigned POST policy and fields for direct browser-to-S3 upload (Amendment 4).
        Enforces content-length-range 1..10MB and key exact match.
        """
        fields = {
            "Content-Type": content_type,
        }
        conditions = [
            ["content-length-range", min_bytes, max_bytes],
            {"key": s3_key},
            {"Content-Type": content_type},
        ]
        return self._client.generate_presigned_post(
            Bucket=self._bucket,
            Key=s3_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires_in,
        )

    def head_object(self, s3_key: str) -> Dict[str, Any]:
        """Retrieve S3 object metadata via HEAD request."""
        return self._client.head_object(Bucket=self._bucket, Key=s3_key)

    def get_object_byte_range(self, s3_key: str, start: int = 0, length: int = 1024) -> bytes:
        """Read a slice of bytes from an S3 object (e.g. for magic bytes check)."""
        end = start + length - 1
        resp = self._client.get_object(
            Bucket=self._bucket,
            Key=s3_key,
            Range=f"bytes={start}-{end}",
        )
        return resp["Body"].read()

    def get_resume(self, job_id: str, document_id: str, s3_key: str | None = None) -> bytes:
        """Download a resume PDF from S3.

        Returns:
            Raw PDF bytes.
        """
        key = s3_key or f"jobs/{job_id}/resumes/{document_id}.pdf"
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        data = response["Body"].read()
        logger.info("Downloaded resume: s3://%s/%s (%d bytes)", self._bucket, key, len(data))
        return data

    def configure_s3_cors(self, allowed_origins: list[str]) -> None:
        """Configure S3 CORS rules for direct browser uploads."""
        if not allowed_origins:
            return
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["POST", "PUT", "HEAD", "GET"],
                    "AllowedOrigins": allowed_origins,
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        }
        try:
            self._client.put_bucket_cors(
                Bucket=self._bucket,
                CORSConfiguration=cors_configuration,
            )
            logger.info("Configured S3 CORS for origins: %s", allowed_origins)
        except Exception as e:
            logger.warning("Could not set S3 CORS (may lack permissions or local mock): %s", e)

    # ── Stage 1 & Stage 2 JSON ─────────────────────────────────────────────

    def upload_stage1_json(
        self,
        job_id: str,
        file_id: str,
        data: Dict[str, Any],
    ) -> str:
        """Upload Stage 1 intermediate extraction JSON."""
        s3_key = f"jobs/{job_id}/stage1/{file_id}.json"
        body = json.dumps(data, ensure_ascii=False, default=str)
        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Uploaded stage 1 JSON: s3://%s/%s", self._bucket, s3_key)
        return s3_key

    def get_stage1_json(self, job_id: str, file_id: str) -> Dict[str, Any]:
        """Download and parse Stage 1 intermediate extraction JSON."""
        s3_key = f"jobs/{job_id}/stage1/{file_id}.json"
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    def upload_stage2_json(
        self,
        job_id: str,
        file_id: str,
        data: Dict[str, Any],
    ) -> str:
        """Upload final structured extraction JSON (Stage 2 or clean Stage 1)."""
        s3_key = f"jobs/{job_id}/stage2/{file_id}.json"
        body = json.dumps(data, ensure_ascii=False, default=str)
        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Uploaded stage 2 JSON: s3://%s/%s", self._bucket, s3_key)
        return s3_key

    def get_stage2_json(self, job_id: str, file_id: str) -> Dict[str, Any]:
        """Download and parse final structured extraction JSON."""
        s3_key = f"jobs/{job_id}/stage2/{file_id}.json"
        response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    # ── Extraction JSON (Legacy compatibility) ────────────────────────────

    def upload_extracted_json(
        self,
        job_id: str,
        document_id: str,
        data: Dict[str, Any],
    ) -> str:
        """Upload extraction result JSON to S3."""
        # Save to stage2 key as canonical and mirror to extracted for backwards compat
        self.upload_stage2_json(job_id, document_id, data)
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
