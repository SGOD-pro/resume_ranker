"""
create_tables.py — Create DynamoDB table + S3 bucket
======================================================
Idempotent: skips if resources already exist.
Works with both floci (local) and real AWS.

Usage:
    python -m src.infrastructure.scripts.create_tables
"""

import sys
import logging
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import boto3
from botocore.exceptions import ClientError

from src.config.aws import get_boto3_kwargs, get_settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def create_dynamodb_table() -> None:
    """Create the ResumePlatform DynamoDB table."""
    settings = get_settings()
    client = boto3.client("dynamodb", **get_boto3_kwargs())

    try:
        client.describe_table(TableName=settings.dynamodb_table_name)
        logger.info("✅ DynamoDB table '%s' already exists — skipping", settings.dynamodb_table_name)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    logger.info("Creating DynamoDB table: %s ...", settings.dynamodb_table_name)
    client.create_table(
        TableName=settings.dynamodb_table_name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Wait for table to become active
    waiter = client.get_waiter("table_exists")
    waiter.wait(
        TableName=settings.dynamodb_table_name,
        WaiterConfig={"Delay": 1, "MaxAttempts": 30},
    )
    logger.info("✅ DynamoDB table '%s' created successfully", settings.dynamodb_table_name)


def create_s3_bucket() -> None:
    """Create the S3 bucket for resume storage."""
    settings = get_settings()
    client = boto3.client("s3", **get_boto3_kwargs())

    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
        logger.info("✅ S3 bucket '%s' already exists — skipping", settings.s3_bucket_name)
        return
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("404", "NoSuchBucket"):
            raise

    logger.info("Creating S3 bucket: %s ...", settings.s3_bucket_name)

    # us-east-1 doesn't accept LocationConstraint
    create_kwargs: dict = {"Bucket": settings.s3_bucket_name}
    if settings.aws_default_region != "us-east-1":
        create_kwargs["CreateBucketConfiguration"] = {
            "LocationConstraint": settings.aws_default_region,
        }

    client.create_bucket(**create_kwargs)
    logger.info("✅ S3 bucket '%s' created successfully", settings.s3_bucket_name)


def main() -> None:
    settings = get_settings()
    endpoint = settings.aws_endpoint_url or "AWS (production)"
    logger.info("━" * 60)
    logger.info("Phase 10 — AWS Resource Setup")
    logger.info("Endpoint: %s", endpoint)
    logger.info("Region:   %s", settings.aws_default_region)
    logger.info("Table:    %s", settings.dynamodb_table_name)
    logger.info("Bucket:   %s", settings.s3_bucket_name)
    logger.info("━" * 60)

    create_dynamodb_table()
    create_s3_bucket()

    logger.info("━" * 60)
    logger.info("✅ All resources ready!")
    logger.info("━" * 60)


if __name__ == "__main__":
    main()
