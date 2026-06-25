"""
scoring_repository.py — Scoring Result entity CRUD on DynamoDB Single Table
==============================================================================
All operations target PK=JOB#{job_id}, SK=SCORING#{scoring_id} in ResumePlatform.
Uses optimistic locking via version + ConditionExpression.

The full ranking JSON lives ONLY in S3. DynamoDB stores metadata + denormalized
top candidate for fast display.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from boto3.dynamodb.conditions import Key

from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.repositories.base import _get_table

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ScoringRepository:
    """CRUD operations for Scoring Result entities in the ResumePlatform table."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create(self, scoring: ScoringItem) -> ScoringItem:
        """Insert a new Scoring Result item.

        Uses ConditionExpression to prevent overwrites.
        """
        item = scoring.to_dynamodb_item()
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        logger.info("Created scoring: %s for job: %s", scoring.scoring_id, scoring.job_id)
        return scoring

    def get(self, job_id: str, scoring_id: str) -> Optional[ScoringItem]:
        """Get a Scoring Result by job_id + scoring_id. Returns None if not found."""
        response = self._table.get_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SCORING#{scoring_id}"},
        )
        item = response.get("Item")
        if not item:
            return None
        return ScoringItem.from_dynamodb_item(item)

    def get_latest(self, job_id: str) -> Optional[ScoringItem]:
        """Get the most recent Scoring Result for a job.

        Queries SCORING# items in reverse SK order and takes the first.
        Since scoring_ids are UUID v4 (not time-ordered), we also sort
        by created_at in the application layer as a safeguard.
        """
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("SCORING#")
            ),
            ScanIndexForward=False,
            Limit=10,  # Get a few to find the true latest by created_at
        )
        items = response.get("Items", [])
        if not items:
            return None

        # Sort by created_at descending to find the true latest
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return ScoringItem.from_dynamodb_item(items[0])

    def list_for_job(self, job_id: str) -> List[ScoringItem]:
        """List all Scoring Results for a job, sorted by created_at descending."""
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("SCORING#")
            ),
        )
        items = response.get("Items", [])
        results = [ScoringItem.from_dynamodb_item(item) for item in items]
        # Sort by created_at descending
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results

    def complete(
        self,
        job_id: str,
        scoring_id: str,
        top_candidate_name: str,
        top_candidate_score: float,
        candidate_count: int,
        expected_version: int,
    ) -> ScoringItem:
        """Mark a scoring run as completed.

        Sets status to COMPLETED, stores denormalized top candidate info.
        """
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SCORING#{scoring_id}"},
            UpdateExpression=(
                "SET #s = :status, top_candidate_name = :tcn, "
                "top_candidate_score = :tcs, candidate_count = :cc, "
                "completed_at = :now, #v = #v + :one"
            ),
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#s": "status", "#v": "version"},
            ExpressionAttributeValues={
                ":status": ScoringStatus.COMPLETED.value,
                ":tcn": top_candidate_name,
                ":tcs": str(top_candidate_score),
                ":cc": candidate_count,
                ":now": _utcnow_iso(),
                ":one": 1,
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        logger.info(
            "Completed scoring %s: #1=%s (%.1f), %d candidates",
            scoring_id, top_candidate_name, top_candidate_score, candidate_count,
        )
        return ScoringItem.from_dynamodb_item(response["Attributes"])

    def fail(
        self,
        job_id: str,
        scoring_id: str,
        expected_version: int,
    ) -> ScoringItem:
        """Mark a scoring run as failed."""
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SCORING#{scoring_id}"},
            UpdateExpression="SET #s = :status, completed_at = :now, #v = #v + :one",
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#s": "status", "#v": "version"},
            ExpressionAttributeValues={
                ":status": ScoringStatus.FAILED.value,
                ":now": _utcnow_iso(),
                ":one": 1,
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        logger.info("Failed scoring: %s", scoring_id)
        return ScoringItem.from_dynamodb_item(response["Attributes"])
