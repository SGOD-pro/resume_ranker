"""
Health route — /api/v2/health
================================
Returns structured JSON with component statuses.
Matches NFR-16: /health endpoint MUST monitor DB, Redis, S3, and Bedrock.
Bedrock check added in Phase 3 when NovaFallbackService exists.
"""

from fastapi import APIRouter
from src.infrastructure.health import check_all

router = APIRouter()


@router.get("/health")
async def health():
    """Infrastructure health check.

    Returns 200 with component statuses regardless of individual failures.
    Monitoring systems use the response body to detect degradation.
    """
    statuses = check_all()
    overall = all(statuses.values())
    return {
        "status": "healthy" if overall else "degraded",
        "components": statuses,
    }
