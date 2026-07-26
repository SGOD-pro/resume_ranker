"""
app.py — FastAPI application factory
=======================================
Resume Ranker V2. Creates and configures the FastAPI application with CORS,
route registration, and infrastructure connectivity checks on startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.health import router as health_router
from src.infrastructure.health import check_all
from src.config.aws import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    On startup: verify PostgreSQL, Redis, and S3 are reachable.
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
    logger.info("Resume Ranker V2 — Starting up")
    logger.info("━" * 60)

    health = check_all()
    if all(health.values()):
        logger.info("All infrastructure services connected ✅")
    else:
        failed = [k for k, v in health.items() if not v]
        logger.warning("Some services unavailable: %s", ", ".join(failed))

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Resume Ranker V2",
        version="2.0.0-alpha",
        description=(
            "Hybrid extraction, deterministic ATS scoring, "
            "explainable candidate ranking."
        ),
        lifespan=lifespan,
    )

    settings = get_settings()
    origins: list[str] = []

    if settings.environment != "production":
        origins.extend([
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ])

    if settings.frontend_url:
        frontend_origins = [
            org.strip() for org in settings.frontend_url.split(",") if org.strip()
        ]
        for org in frontend_origins:
            if org not in origins:
                origins.append(org)

    if settings.environment == "production" and not origins:
        logger.warning(
            "CORS: Running in production but no frontend_url is configured. "
            "CORS requests will be rejected."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All routes under /api/v2/
    app.include_router(health_router, prefix="/api/v2", tags=["health"])

    from src.api.routes.jobs_v2 import router as jobs_v2_router
    from src.api.routes.ats import router as ats_router
    from src.api.errors import register_exception_handlers

    app.include_router(jobs_v2_router)
    app.include_router(ats_router)

    register_exception_handlers(app)

    return app


app = create_app()
