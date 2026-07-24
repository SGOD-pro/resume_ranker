# ── Stage 1: Build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

# opendataloader-pdf requires JRE 11+. JRE 21 is the current LTS in Debian Trixie.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

COPY src ./src

EXPOSE 8000

# Default: API server. Worker overrides CMD in docker-compose.yml.
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]