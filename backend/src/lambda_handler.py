"""
lambda_handler.py — AWS Lambda entry point
==========================================
Wraps the FastAPI application with Mangum so it can receive events
from API Gateway HTTP API (payload format v2.0).

AWS Lambda invokes:  lambda_handler.handler(event, context)
"""

from mangum import Mangum

from src.api.app import app

# Mangum translates API Gateway HTTP API events ↔ ASGI (FastAPI)
# lifespan="off" is recommended for Lambda where the container may be
# recycled between requests; startup/shutdown hooks run per-import instead.
handler = Mangum(app, lifespan="off")
