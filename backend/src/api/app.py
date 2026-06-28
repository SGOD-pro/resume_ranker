"""
app.py — FastAPI application factory
=======================================
Creates and configures the FastAPI application with CORS, route registration,
and AWS connectivity checks on startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.health import router as health_router
from src.api.routes.jobs import router as jobs_router
from src.infrastructure.health import check_all
from src.config.aws import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    On startup: verify DynamoDB and S3 are reachable.
    Logs ✅ or ❌ for each service — does NOT block startup
    so the health endpoint remains available for debugging.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("━" * 60)
    logger.info("Resume Intelligence Platform — Starting up")
    logger.info("━" * 60)

    health = check_all()
    if all(health.values()):
        logger.info("All AWS services connected ✅")
    else:
        failed = [k for k, v in health.items() if not v]
        logger.warning("Some AWS services unavailable: %s", ", ".join(failed))

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Shutting down...")

# uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Resume Intelligence Platform",
        version="0.1.0",
        description="API for resume extraction, scoring, and ranking.",
        lifespan=lifespan,
    )

    settings = get_settings()
    origins = []

    # Only allow localhost origins in non-production environments to avoid security 
    # vulnerabilities in production deployments.
    if settings.environment != "production":
        origins.extend([
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ])

    if settings.frontend_url:
        # Support comma-separated strings of origins
        frontend_origins = [org.strip() for org in settings.frontend_url.split(",") if org.strip()]
        for org in frontend_origins:
            if org not in origins:
                origins.append(org)

    if settings.environment == "production" and not origins:
        logger.warning(
            "CORS: Running in production environment but no frontend_url is configured. "
            "CORS requests will be rejected."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route modules
    app.include_router(health_router)
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

    return app


app = create_app()
