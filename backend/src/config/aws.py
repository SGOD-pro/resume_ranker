from functools import lru_cache
from typing import Optional

import logging
import boto3
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.getLogger("botocore.credentials").setLevel(logging.WARNING)


from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


class AWSSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )



    S3_BUCKET_NAME: str = "resume-ranker-dev-storage"
    DYNAMODB_TABLE_NAME: str = "ResumePlatform"

    ENVIRONMENT: str = "dev"
    LOG_LEVEL: str = "DEBUG"
    FRONTEND_URL: str = "http://localhost:5173"

    # SQS Queue URLs & DLQs
    SQS_FAST_PARSE_QUEUE_URL: str = ""
    SQS_FAST_PARSE_DLQ_URL: str = ""
    SQS_ODL_BATCH_QUEUE_URL: str = ""
    SQS_ODL_BATCH_DLQ_URL: str = ""
    SQS_NOVA_QUEUE_URL: str = ""
    SQS_NOVA_DLQ_URL: str = ""
    SQS_FINAL_RANK_QUEUE_URL: str = ""
    SQS_FINAL_RANK_DLQ_URL: str = ""

    # SNS Topic ARN for pub/sub events
    SNS_EVENTS_TOPIC_ARN: str = ""

    # Queue execution mode (False = use deterministic LocalQueueAdapter)
    USE_REAL_SQS: bool = False

    # Upload session guardrails & limits
    MAX_DOCS_PER_SESSION: int = 100
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_PAGE_COUNT: int = 50
    MAX_BATCH_BYTES: int = 200 * 1024 * 1024  # 200 MB
    MAX_ACTIVE_SESSIONS_PER_ORG: int = 5
    CLIENT_UPLOAD_CONCURRENCY: int = 4
    PRESIGNED_URL_EXPIRY_SECONDS: int = 900  # 15 minutes

    # Worker concurrency and batch settings
    ODL_BATCH_SIZE: int = 10
    ODL_WORKER_CONCURRENCY: int = 2
    NOVA_WORKER_CONCURRENCY: int = 2

    def is_local(self) -> bool:
        return self.ENVIRONMENT == "dev"

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    @property
    def s3_bucket_name(self) -> str:
        return self.S3_BUCKET_NAME

    @property
    def dynamodb_table_name(self) -> str:
        return self.DYNAMODB_TABLE_NAME

    @property
    def frontend_url(self) -> str:
        return self.FRONTEND_URL


@lru_cache(maxsize=1)
def get_settings() -> AWSSettings:
    return AWSSettings()


def is_running_in_lambda() -> bool:
    """Returns True if the code is deployed in AWS Lambda."""
    import os
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


def _get_session_for_service(service: str) -> boto3.Session:
    """Helper to return a properly profiled session depending on the service."""
    s = get_settings()
    session_kwargs = {}
    
    if not is_running_in_lambda():
        if service in ("bedrock-runtime", "lambda", "sqs", "sns"):
            # Cloud services MUST use real AWS credentials
            session_kwargs["profile_name"] = "aws"
        else:
            # Normal resources (S3, Dynamo) use the profile tied to the environment
            if s.ENVIRONMENT in ("dev", "local", "development"):
                session_kwargs["profile_name"] = "local"
            elif s.ENVIRONMENT in ("prod", "production"):
                session_kwargs["profile_name"] = "aws"
                
    return boto3.Session(**session_kwargs)


def get_client(service: str, config=None):
    """Get a boto3 client."""
    s = get_settings()
    extra = {} if config is None else {"config": config}
    kwargs: dict = {}
    kwargs.update(extra)
    
    # Only use local endpoint for local dev when NOT targeting cloud services
    if s.is_local() and service not in ("bedrock-runtime", "lambda", "sqs", "sns"):
        kwargs["endpoint_url"] = "http://localhost:4566"
    
    session = _get_session_for_service(service)
    return session.client(service, **kwargs)


def get_resource(service: str, config=None):
    """Get a boto3 resource."""
    s = get_settings()
    extra = {} if config is None else {"config": config}
    kwargs: dict = {}
    kwargs.update(extra)
    
    if s.is_local() and service not in ("bedrock-runtime", "lambda", "sqs", "sns"):
        kwargs["endpoint_url"] = "http://localhost:4566"
    
    session = _get_session_for_service(service)
    return session.resource(service, **kwargs)

