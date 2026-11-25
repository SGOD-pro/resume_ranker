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
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key

from src.infrastructure.models.scoring import ScoringItem, ScoringStatus
from src.infrastructure.repositories.base import _get_table, to_decimal

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

    def save_candidate_decision(
        self,
        job_id: str,
        document_id: str,
        decision_data: Dict[str, Any],
        expected_version: Optional[int] = None,
        client_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist recruiter candidate decision, reason, and notes to DynamoDB atomically.

        Uses field-specific update_item rather than put_item to preserve independent fields
        (e.g. notes, tags, decision, reason) updated by separate recruiters or requests.
        Supports optimistic concurrency via expected_version and out-of-order protection via client_timestamp.
        """
        now = _utcnow_iso()
        expr_names: Dict[str, str] = {
            "#et": "entity_type",
            "#jid": "job_id",
            "#did": "document_id",
        }
        expr_vals: Dict[str, Any] = {
            ":et": "DECISION",
            ":jid": job_id,
            ":did": document_id,
            ":now": now,
            ":zero": 0,
            ":one": 1,
        }

        set_clauses = [
            "#et = if_not_exists(#et, :et)",
            "#jid = if_not_exists(#jid, :jid)",
            "#did = if_not_exists(#did, :did)",
            "updated_at = :now",
            "version = if_not_exists(version, :zero) + :one",
        ]

        for i, (k, v) in enumerate(decision_data.items()):
            field_alias = f"#field_{i}"
            val_alias = f":val_{i}"
            expr_names[field_alias] = k
            expr_vals[val_alias] = to_decimal(v)
            set_clauses.append(f"{field_alias} = {val_alias}")

        update_expr = f"SET {', '.join(set_clauses)}"

        cond_clauses = []
        if expected_version is not None:
            expr_names["#v"] = "version"
            expr_vals[":expected_v"] = expected_version
            cond_clauses.append("(attribute_not_exists(#v) OR #v = :expected_v)")
        if client_timestamp is not None:
            expr_vals[":client_ts"] = client_timestamp
            cond_clauses.append("(attribute_not_exists(updated_at) OR updated_at <= :client_ts)")

        cond_expr = " AND ".join(cond_clauses) if cond_clauses else None

        update_kwargs: Dict[str, Any] = {
            "Key": {"PK": f"JOB#{job_id}", "SK": f"DECISION#{document_id}"},
            "UpdateExpression": update_expr,
            "ExpressionAttributeNames": expr_names,
            "ExpressionAttributeValues": expr_vals,
            "ReturnValues": "ALL_NEW",
        }
        if cond_expr:
            update_kwargs["ConditionExpression"] = cond_expr

        response = self._table.update_item(**update_kwargs)
        attrs = response.get("Attributes", {})
        logger.info("Persisted decision for candidate %s in job %s to DynamoDB", document_id, job_id)
        return attrs

    def get_candidate_decisions(self, job_id: str) -> Dict[str, Dict[str, Any]]:
        """Retrieve all recruiter candidate decisions for a job from DynamoDB."""
        from boto3.dynamodb.conditions import Key
        resp = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("DECISION#")
        )
        decisions: Dict[str, Dict[str, Any]] = {}
        for it in resp.get("Items", []):
            doc_id = it.get("document_id")
            if doc_id:
                decisions[doc_id] = it
        return decisions
