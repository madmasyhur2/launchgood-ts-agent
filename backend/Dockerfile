# =============================================================================
# LaunchGood T&S Agent — Backend Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): Install Python dependencies with uv into a virtual env
#   Stage 2 (runtime): Copy the venv + app code into a slim final image
# =============================================================================

# ---- Stage 1: dependency builder ----
FROM python:3.11-slim AS builder

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first (for better layer caching).
# NOTE: Source paths are relative to the repo root (Railway build context).
COPY backend/pyproject.toml backend/uv.lock ./

# Install dependencies into a project-local virtual env (.venv)
# --frozen: respect uv.lock, no updates
# --no-dev: skip dev dependencies
RUN uv sync --frozen --no-dev

# ---- Stage 2: runtime image ----
FROM python:3.11-slim AS runtime

# Create a non-root user for security
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source.
# NOTE: Source paths are relative to the repo root (Railway build context).
COPY backend/app/ ./app/
COPY backend/alembic/ ./alembic/
COPY backend/alembic.ini ./

# Make the venv's Python the default for this container
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose the port uvicorn will listen on
EXPOSE 8000

# Health check — Docker/Railway will poll this
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start command: run migrations then launch the API server.
# Railway injects $PORT — we must use it (not hardcode 8000).
CMD alembic upgrade head && \
    uvicorn app.main:app \
      --host 0.0.0.0 \
      --port ${PORT:-8000} \
      --workers 2 \
      --log-level info
