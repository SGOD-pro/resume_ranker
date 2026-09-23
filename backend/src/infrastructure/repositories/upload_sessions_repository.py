"""
upload_sessions_repository.py — UploadSession CRUD on DynamoDB Single Table
=============================================================================
Targets PK=JOB#{job_id}, SK=SESSION#{session_id} in ResumePlatform table.
Uses optimistic locking via version + ConditionExpression.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Attr, Key

from src.infrastructure.models.upload_session import (
    UploadSessionItem,
    UploadSessionStatus,
)
from src.infrastructure.repositories.base import _get_table, to_decimal

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UploadSessionsRepository:
    """CRUD operations for UploadSession entities in DynamoDB."""

    def __init__(self) -> None:
        self._table = _get_table()

    def create(self, session: UploadSessionItem) -> UploadSessionItem:
        """Insert a new UploadSession item.

        Uses ConditionExpression to prevent duplicate session IDs.
        """
        item = session.to_dynamodb_item()
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
        logger.info("Created upload session: %s for job: %s", session.session_id, session.job_id)
        return session

    def get(self, job_id: str, session_id: str) -> Optional[UploadSessionItem]:
        """Get an UploadSession by job_id and session_id."""
        response = self._table.get_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SESSION#{session_id}"},
        )
        item = response.get("Item")
        if not item:
            return None
        return UploadSessionItem.from_dynamodb_item(item)

    def list_for_job(self, job_id: str) -> List[UploadSessionItem]:
        """List all upload sessions for a job."""
        response = self._table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"JOB#{job_id}") & Key("SK").begins_with("SESSION#")
            ),
        )
        items = response.get("Items", [])
        return [UploadSessionItem.from_dynamodb_item(it) for it in items]

    def count_active_for_org(self, org_id: str, max_age_seconds: int = 1800) -> int:
        """Count active in-flight upload sessions for an organization to enforce quotas.

        Sessions in READY_TO_ANALYZE or terminal states (READY, FAILED, EXPIRED) are excluded.
        Sessions older than max_age_seconds (default 30 min) are treated as expired and excluded.
        """
        active_statuses = [
            UploadSessionStatus.UPLOADING.value,
            UploadSessionStatus.UPLOAD_FINALIZED.value,
            UploadSessionStatus.FAST_PREPROCESSING.value,
            UploadSessionStatus.FAST_PARSING.value,
            UploadSessionStatus.ANALYSIS_REQUESTED.value,
            UploadSessionStatus.FALLBACK_PROCESSING.value,
            UploadSessionStatus.FINAL_RANKING.value,
        ]
        response = self._table.scan(
            FilterExpression=(
                Attr("entity_type").eq("UPLOAD_SESSION")
                & Attr("org_id").eq(org_id)
                & Attr("status").is_in(active_statuses)
            ),
            ProjectionExpression="session_id, created_at, updated_at",
        )
        items = response.get("Items", [])
        now = datetime.now(timezone.utc)
        active_count = 0
        for it in items:
            ts_str = it.get("updated_at") or it.get("created_at")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if (now - ts).total_seconds() > max_age_seconds:
                        continue
                except Exception:
                    pass
            active_count += 1
        return active_count

    def update_status(
        self,
        job_id: str,
        session_id: str,
        status: UploadSessionStatus,
        expected_version: int,
        error_message: Optional[str] = None,
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> UploadSessionItem:
        """Update session status with optimistic locking."""
        set_parts = ["#s = :status", "#v = #v + :one", "updated_at = :now"]
        expr_names = {"#s": "status", "#v": "version"}
        expr_values: Dict[str, Any] = {
            ":status": status.value,
            ":one": 1,
            ":now": _utcnow_iso(),
            ":expected_version": expected_version,
        }
        if error_message:
            set_parts.append("error_message = :err")
            expr_values[":err"] = error_message

        if extra_updates:
            for idx, (k, v) in enumerate(extra_updates.items()):
                p_name = f"#ext_{idx}"
                p_val = f":ext_val_{idx}"
                set_parts.append(f"{p_name} = {p_val}")
                expr_names[p_name] = k
                expr_values[p_val] = to_decimal(v)

        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SESSION#{session_id}"},
            UpdateExpression="SET " + ", ".join(set_parts),
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW",
        )
        logger.info(
            "Updated upload session %s status → %s (v%d → v%d)",
            session_id, status.value, expected_version, expected_version + 1
        )
        return UploadSessionItem.from_dynamodb_item(response["Attributes"])

    def set_analysis_requested(
        self,
        job_id: str,
        session_id: str,
        expected_version: int,
        analysis_requested: bool = True,
        new_status: Optional[UploadSessionStatus] = None,
        job_version: Optional[int] = None,
    ) -> UploadSessionItem:
        """Set analysis_requested flag and optionally update pinned job_version and status."""
        set_parts = ["analysis_requested = :ar", "#v = #v + :one", "updated_at = :now"]
        expr_names = {"#v": "version"}
        expr_values: Dict[str, Any] = {
            ":ar": analysis_requested,
            ":one": 1,
            ":now": _utcnow_iso(),
            ":expected_version": expected_version,
        }
        if new_status:
            set_parts.append("#s = :status")
            expr_names["#s"] = "status"
            expr_values[":status"] = new_status.value
        if job_version is not None:
            set_parts.append("job_version = :jv")
            expr_values[":jv"] = job_version

        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SESSION#{session_id}"},
            UpdateExpression="SET " + ", ".join(set_parts),
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW",
        )
        logger.info(
            "Set analysis_requested=%s for session %s (v%d → v%d)",
            analysis_requested, session_id, expected_version, expected_version + 1
        )
        return UploadSessionItem.from_dynamodb_item(response["Attributes"])

    def increment_uploaded_count(
        self,
        job_id: str,
        session_id: str,
        expected_version: int,
    ) -> UploadSessionItem:
        """Increment uploaded document count for a session."""
        response = self._table.update_item(
            Key={"PK": f"JOB#{job_id}", "SK": f"SESSION#{session_id}"},
            UpdateExpression="SET uploaded_document_count = uploaded_document_count + :one, #v = #v + :one, updated_at = :now",
            ConditionExpression="#v = :expected_version",
            ExpressionAttributeNames={"#v": "version"},
            ExpressionAttributeValues={
                ":one": 1,
                ":now": _utcnow_iso(),
                ":expected_version": expected_version,
            },
            ReturnValues="ALL_NEW",
        )
        return UploadSessionItem.from_dynamodb_item(response["Attributes"])

