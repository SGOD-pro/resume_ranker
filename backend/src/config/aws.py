"""
aws.py — AWS configuration via Pydantic Settings
====================================================
Reads from environment variables or .env file.
Provides get_settings() singleton and get_boto3_kwargs() helper.

Switching environments:
  cp .env.development .env   # floci (local)
  cp .env.production .env    # real AWS
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AWSSettings(BaseSettings):
    """AWS configuration — all values come from env vars or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── AWS Core ──────────────────────────────────────────────────────────
    # Empty string → None (boto3 uses real AWS endpoints)
    aws_endpoint_url: Optional[str] = None
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_default_region: str = "us-east-1"

    # ── S3 ────────────────────────────────────────────────────────────────
    s3_bucket_name: str = "resume-ranker-dev-storage"

    # ── DynamoDB ──────────────────────────────────────────────────────────
    dynamodb_table_name: str = "ResumePlatform"

    # ── App ───────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "DEBUG"
    frontend_url: str = ""


    def is_local(self) -> bool:
        """True when running against floci / LocalStack."""
        return bool(self.aws_endpoint_url)


@lru_cache(maxsize=1)
def get_settings() -> AWSSettings:
    """Singleton — parsed once, cached forever."""
    return AWSSettings()


def get_boto3_kwargs() -> dict:
    """Build kwargs dict for boto3.client() / boto3.resource().

    When aws_endpoint_url is set (floci/LocalStack), it's included.
    When empty/None (production), it's omitted → boto3 uses real AWS.
    """
    settings = get_settings()
    kwargs = {
        "region_name": settings.aws_default_region,
    }

    # LocalStack / Floci only
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    return kwargs
