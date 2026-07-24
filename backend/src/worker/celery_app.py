"""
celery_app.py — Celery application for Resume Ranker V2
=========================================================
Clean V2 module. Does NOT import any V1 task registrations.
V1 extractors import fitz (pymupdf) which is banned in V2 —
wiring them here would crash the worker on startup.

Tasks are registered in later phases:
  - Phase 1: structural parsing tasks
  - Phase 2: deterministic extraction tasks
  - Phase 3: Nova fallback batch tasks
"""

from celery import Celery
from src.config.aws import get_settings

settings = get_settings()

celery_app = Celery(
    "resume_ranker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Batching config for Nova fallback (Phase 3)
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
