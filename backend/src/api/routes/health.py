"""
health.py — Health check endpoint
====================================
Simple /health endpoint for backend reachability checks.
Used by the frontend cold-start gate on app load.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return 200 OK if the backend is reachable and ready."""
    return {"status": "ok"}
