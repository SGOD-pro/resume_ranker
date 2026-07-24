"""
extraction/odl_cache.py — S3-backed cache for ODL parse results
================================================================
Implements the DocumentCache protocol from structural_parsing_service.py.

Key format: odl-cache/{content_hash}.json   (ODL JSON)
            odl-cache/{content_hash}.md      (Markdown)

S3 Lifecycle TTL (30 days) is set via bucket policy per boundaries.md §5,
not enforced here — we write; TTL policy evicts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3  # type: ignore

from src.config.aws import get_boto3_kwargs, get_settings

logger = logging.getLogger(__name__)

_JSON_PREFIX = "odl-cache"


class S3DocumentCache:
    """
    S3-backed implementation of the DocumentCache protocol.

    Uses the same S3 bucket as StorageService.  Separate key prefix
    keeps ODL cache objects isolated from resume PDFs and extraction JSON.
    """

    def __init__(self) -> None:
        self._client = boto3.client("s3", **get_boto3_kwargs())
        self._bucket = get_settings().s3_bucket_name

    def get(self, content_hash: str) -> dict[str, Any] | None:
        """Return cached ODL JSON dict or None on cache miss."""
        key = self._json_key(content_hash)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read().decode("utf-8")
            logger.debug("ODL cache hit: s3://%s/%s", self._bucket, key)
            data: dict[str, Any] = json.loads(body)
            return data
        except self._client.exceptions.NoSuchKey:
            logger.debug("ODL cache miss: %s", content_hash[:12])
            return None
        except Exception as exc:  # noqa: BLE001
            # Cache failures are non-fatal — log and return None so ODL re-runs
            logger.warning("ODL cache get failed for %s: %s", content_hash[:12], exc)
            return None

    def put(self, content_hash: str, odl_json: dict[str, Any], markdown: str) -> str:
        """Persist ODL JSON (and markdown) to S3. Returns the JSON S3 key."""
        json_key = self._json_key(content_hash)
        md_key = self._md_key(content_hash)

        body = json.dumps(odl_json, ensure_ascii=False).encode("utf-8")
        self._client.put_object(
            Bucket=self._bucket,
            Key=json_key,
            Body=body,
            ContentType="application/json",
        )
        logger.info("ODL result cached: s3://%s/%s", self._bucket, json_key)

        if markdown:
            self._client.put_object(
                Bucket=self._bucket,
                Key=md_key,
                Body=markdown.encode("utf-8"),
                ContentType="text/markdown",
            )

        return json_key

    def get_markdown(self, content_hash: str) -> str:
        """Return cached markdown string or empty string on miss."""
        key = self._md_key(content_hash)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return str(response["Body"].read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------

    @staticmethod
    def _json_key(content_hash: str) -> str:
        return f"{_JSON_PREFIX}/{content_hash}.json"

    @staticmethod
    def _md_key(content_hash: str) -> str:
        return f"{_JSON_PREFIX}/{content_hash}.md"


class InMemoryDocumentCache:
    """
    In-memory implementation for unit tests.
    No S3 dependency.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._md_store: dict[str, str] = {}

    def get(self, content_hash: str) -> dict[str, Any] | None:
        return self._store.get(content_hash)

    def put(self, content_hash: str, odl_json: dict[str, Any], markdown: str) -> str:
        self._store[content_hash] = odl_json
        self._md_store[content_hash] = markdown
        return f"in-memory://{content_hash}"

    def get_markdown(self, content_hash: str) -> str:
        return self._md_store.get(content_hash, "")
