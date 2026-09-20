"""
audit.py — Audit logging service for Sortlist v2
=================================================
Records and queries security- and compliance-relevant state changes:
- Job creation, updates, and cascading deletions
- Document ingestion, extraction runs, and failures
- Scoring operations and weight changes
- Human decisions (Shortlist, Reject with mandatory reason)
- Data exports and retention events
"""

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("audit")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AuditEvent:
    event_id: str
    timestamp: str
    org_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """In-memory event buffer with structured log output."""

    def __init__(self, max_buffer_size: int = 1000):
        self._events: List[AuditEvent] = []
        self._max_buffer_size = max_buffer_size

    def record(
        self,
        org_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=_utcnow_iso(),
            org_id=org_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )

        self._events.append(event)
        if len(self._events) > self._max_buffer_size:
            self._events.pop(0)

        logger.info(
            "AUDIT_EVENT [%s] action=%s actor=%s org=%s target=%s/%s details=%s",
            event.timestamp,
            event.action,
            event.user_id,
            event.org_id,
            event.resource_type,
            event.resource_id,
            event.details,
        )
        return event

    def query(
        self,
        org_id: str,
        resource_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query audit log events scoped to the organization."""
        results = [
            e.to_dict()
            for e in reversed(self._events)
            if e.org_id == org_id and (resource_id is None or e.resource_id == resource_id)
        ]
        return results[:limit]


# Global singleton instance
audit_logger = AuditLogger()
