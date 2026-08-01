from functools import lru_cache
from typing import Optional

import boto3
from pydantic_settings import BaseSettings, SettingsConfigDict


class AWSSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    AWS_ENDPOINT_URL: Optional[str] = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_PROFILE: Optional[str] = None

    S3_BUCKET_NAME: str = "resume-ranker-dev-storage"
    DYNAMODB_TABLE_NAME: str = "ResumePlatform"

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    FRONTEND_URL: str = ""

    def is_local(self) -> bool:
        return self.ENVIRONMENT == "local"


@lru_cache(maxsize=1)
def get_settings() -> AWSSettings:
    return AWSSettings()


_LOCAL_SERVICES = {"dynamodb", "s3", "sqs", "sns", "lambda"}


def _get_session() -> boto3.Session:
    s = get_settings()
    if s.is_local() and s.AWS_PROFILE:
        return boto3.Session(profile_name=s.AWS_PROFILE, region_name=s.AWS_DEFAULT_REGION)
    return boto3.Session(region_name=s.AWS_DEFAULT_REGION)


def get_client(service: str, config=None):
    s = get_settings()
    extra = {} if config is None else {"config": config}

    if service == "bedrock-runtime":
        if s.is_local():
            session = boto3.Session(profile_name="aws", region_name="ap-south-1")
        else:
            session = boto3.Session(region_name=s.AWS_DEFAULT_REGION)
        return session.client("bedrock-runtime", **extra)

    kwargs: dict = {}
    if s.AWS_ENDPOINT_URL and service in _LOCAL_SERVICES:
        kwargs["endpoint_url"] = s.AWS_ENDPOINT_URL
    kwargs.update(extra)

    return _get_session().client(service, **kwargs)
