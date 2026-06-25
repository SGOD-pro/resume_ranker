"""
health.py — AWS connectivity checks
=======================================
Called on FastAPI startup to verify DynamoDB and S3 are reachable.
Works with both floci (local) and real AWS.
"""

import logging

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from src.config.aws import get_boto3_kwargs, get_settings

logger = logging.getLogger(__name__)


def check_dynamodb() -> bool:
    """Check DynamoDB connectivity by describing the ResumePlatform table.

    Returns True if the table exists and is accessible.
    """
    settings = get_settings()
    try:
        client = boto3.client("dynamodb", **get_boto3_kwargs())
        response = client.describe_table(TableName=settings.dynamodb_table_name)
        status = response["Table"]["TableStatus"]
        logger.info(
            "✅ DynamoDB connected — table: %s (status: %s)",
            settings.dynamodb_table_name, status,
        )
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            logger.error(
                "❌ DynamoDB table '%s' not found. Run: python -m src.infrastructure.scripts.create_tables",
                settings.dynamodb_table_name,
            )
        else:
            logger.error("❌ DynamoDB error: %s", e)
        return False
    except (EndpointConnectionError, ConnectionError) as e:
        endpoint = settings.aws_endpoint_url or "AWS"
        logger.error("❌ DynamoDB unreachable at %s: %s", endpoint, e)
        return False
    except NoCredentialsError:
        logger.error("❌ DynamoDB: No AWS credentials configured")
        return False
    except Exception as e:
        logger.error("❌ DynamoDB unexpected error: %s", e)
        return False


def check_s3() -> bool:
    """Check S3 connectivity by calling head_bucket.

    Returns True if the bucket exists and is accessible.
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
                "❌ S3 bucket '%s' not found. Run: python -m src.infrastructure.scripts.create_tables",
                settings.s3_bucket_name,
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
    """Run all connectivity checks. Returns {"dynamodb": bool, "s3": bool}."""
    return {
        "dynamodb": check_dynamodb(),
        "s3": check_s3(),
    }
