"""
aws.py — Application configuration via Pydantic Settings
============================================================
V2: PostgreSQL + Redis + S3. DynamoDB removed.
Reads from environment variables or .env file.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration — all values come from env vars or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/resume_ranker"
    )

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── AWS Core ──────────────────────────────────────────────────────────
    aws_endpoint_url: Optional[str] = None
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_default_region: str = "ap-south-1"

    # ── S3 ────────────────────────────────────────────────────────────────
    s3_bucket_name: str = "resume-ranker-dev-storage"

    # ── App ───────────────────────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "DEBUG"
    frontend_url: str = ""

    def is_local(self) -> bool:
        """True when running against LocalStack."""
        return bool(self.aws_endpoint_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton — parsed once, cached forever."""
    return Settings()


def get_boto3_kwargs() -> dict:
    """Build kwargs dict for boto3.client() / boto3.resource().

    When aws_endpoint_url is set (LocalStack), it's included.
    When empty/None (production), it's omitted → boto3 uses real AWS.
    """
    settings = get_settings()
    kwargs: dict = {
        "region_name": settings.aws_default_region,
    }

    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    return kwargs
