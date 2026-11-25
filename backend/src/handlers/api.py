"""
api.py — AWS Lambda HTTP API handler via Mangum
================================================
Imports only required API dependencies (FastAPI + Mangum).
"""

import logging
from mangum import Mangum
from src.main import app

logger = logging.getLogger(__name__)

handler = Mangum(app, lifespan="off")
