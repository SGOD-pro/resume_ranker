"""
health.py — Infrastructure connectivity checks
==================================================
V2: DynamoDB + Redis + S3.
Called on FastAPI startup and exposed via /health endpoint.
"""

import logging

import boto3
import redis
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from src.config.aws import get_boto3_kwargs, get_settings

logger = logging.getLogger(__name__)


def check_dynamodb() -> bool:
    """Check DynamoDB connectivity by describing the main table."""
    settings = get_settings()
    try:
        client = boto3.client("dynamodb", **get_boto3_kwargs())
        client.describe_table(TableName=settings.dynamodb_table_name)
        logger.info("✅ DynamoDB connected — table: %s", settings.dynamodb_table_name)
        return True
    except Exception as e:
        logger.error("❌ DynamoDB unreachable: %s", e)
        return False


def check_redis() -> bool:
    """Check Redis connectivity with PING."""
    settings = get_settings()
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=5)
        client.ping()
        logger.info("✅ Redis connected — %s", settings.redis_url)
        return True
    except Exception as e:
        logger.error("❌ Redis unreachable: %s", e)
        return False


def check_s3() -> bool:
    """Check S3 connectivity by calling head_bucket.

    Returns True if the bucket exists and is accessible.
    Returns False (non-blocking) if S3/LocalStack is not running.
    """
    settings = get_settings()
    try:
        client = boto3.client("s3", **get_boto3_kwargs())
        client.head_bucket(Bucket=settings.s3_bucket_name)
        logger.info("✅ S3 connected — bucket: %s", settings.s3_bucket_name)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            logger.error(
                "❌ S3 bucket '%s' not found", settings.s3_bucket_name,
            )
        elif code in ("403", "AccessDenied"):
            logger.error("❌ S3 bucket '%s' exists but access denied", settings.s3_bucket_name)
        else:
            logger.error("❌ S3 error: %s", e)
        return False
    except (EndpointConnectionError, ConnectionError) as e:
        endpoint = settings.aws_endpoint_url or "AWS"
        logger.error("❌ S3 unreachable at %s: %s", endpoint, e)
        return False
    except NoCredentialsError:
        logger.error("❌ S3: No AWS credentials configured")
        return False
    except Exception as e:
        logger.error("❌ S3 unexpected error: %s", e)
        return False


def check_all() -> dict:
    """Run all connectivity checks.

    Returns {"dynamodb": bool, "redis": bool, "s3": bool}.
    """
    return {
        "dynamodb": check_dynamodb(),
        "redis": check_redis(),
        "s3": check_s3(),
    }
