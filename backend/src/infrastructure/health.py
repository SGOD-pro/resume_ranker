"""
health.py — Infrastructure connectivity checks
==================================================
V2: PostgreSQL + Redis + S3. DynamoDB removed.
Called on FastAPI startup and exposed via /health endpoint.
"""

import logging

import boto3
import redis
import psycopg
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from src.config.aws import get_boto3_kwargs, get_settings

logger = logging.getLogger(__name__)


def check_postgres() -> bool:
    """Check PostgreSQL connectivity with a simple SELECT 1."""
    settings = get_settings()
    try:
        # Use sync psycopg directly — health check is a one-shot probe,
        # no need for async or SQLAlchemy overhead here.
        conninfo = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(conninfo, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        logger.info("✅ PostgreSQL connected — %s", conninfo.split("@")[-1])
        return True
    except Exception as e:
        logger.error("❌ PostgreSQL unreachable: %s", e)
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

    Returns {"postgres": bool, "redis": bool, "s3": bool}.
    """
    return {
        "postgres": check_postgres(),
        "redis": check_redis(),
        "s3": check_s3(),
    }
