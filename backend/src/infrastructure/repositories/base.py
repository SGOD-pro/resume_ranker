"""
base.py — Shared DynamoDB client factory
==========================================
All repositories call _get_table() to access the single ResumePlatform table.
Endpoint URL is read from AWSSettings for floci/production switching.
"""

from functools import lru_cache
from decimal import Decimal
from typing import Any

import boto3

from src.config.aws import get_boto3_kwargs, get_settings


@lru_cache(maxsize=1)
def _get_dynamodb_resource():
    """Cached boto3 DynamoDB resource.

    For Lambda: cached across warm invocations (lru_cache lives in module scope).
    For FastAPI: cached for the lifetime of the process.
    """
    return boto3.resource("dynamodb", **get_boto3_kwargs())


def _get_table():
    """Get the single ResumePlatform DynamoDB Table resource."""
    settings = get_settings()
    return _get_dynamodb_resource().Table(settings.dynamodb_table_name)


def to_decimal(val: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB serialization."""
    if isinstance(val, float):
        return Decimal(str(val))
    elif isinstance(val, dict):
        return {k: to_decimal(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [to_decimal(v) for v in val]
    elif isinstance(val, tuple):
        return tuple(to_decimal(v) for v in val)
    return val

