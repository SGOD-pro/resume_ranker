"""
app.py — FastAPI application factory
=======================================
Creates and configures the FastAPI application with CORS and route registration.
Does NOT modify any pipeline or core logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.health import router as health_router
from src.api.routes.jobs import router as jobs_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Resume Intelligence Platform",
        version="0.1.0",
        description="API for resume extraction, scoring, and ranking.",
    )

    # CORS — allow the Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route modules
    app.include_router(health_router)
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

    return app


app = create_app()
