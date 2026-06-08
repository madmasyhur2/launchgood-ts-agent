"""
app/main.py

FastAPI application factory.

Responsibilities:
- Create the FastAPI app with metadata (title, description, version)
- Register all API routers under the /api prefix
- Configure CORS from environment variables
- Lifespan handler: verify DB connectivity on startup
- Health-check endpoint
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.routers import analytics, campaigns, reviews

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    On startup:
      - Verifies database connectivity (fails fast if DB is not ready)
      - Logs environment and configuration summary

    On shutdown:
      - Disposes the async engine (closes all pooled connections cleanly)
    """
    # ---- Startup ----
    logger.info("Starting LaunchGood T&S Agent API [env=%s]", settings.environment)

    # Verify DB connectivity — will raise immediately if postgres is not up
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified ✓")

    yield  # <── application runs here

    # ---- Shutdown ----
    logger.info("Shutting down — disposing database engine...")
    await engine.dispose()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LaunchGood Campaign Trust & Safety Review Agent",
    description=(
        "AI-powered campaign moderation system with Human-in-the-Loop (HITL) "
        "approval workflow for LaunchGood fundraising platform. "
        "Implements risk scoring, compliance screening, fraud detection, "
        "and full audit trails."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# All routers are mounted under the /api prefix
API_PREFIX = settings.api_prefix  # default: "/api"

app.include_router(campaigns.router, prefix=API_PREFIX)
app.include_router(reviews.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

_HEALTH_PAYLOAD = {
    "status": "ok",
    "service": "launchgood-ts-agent",
    "version": "1.0.0",
}


@app.get(f"{API_PREFIX}/health", tags=["health"], summary="Health check")
async def health_check() -> dict:
    """
    Returns 200 OK when the API is running.
    Used by Railway healthcheck, load balancers, and monitoring.
    """
    return {**_HEALTH_PAYLOAD, "environment": settings.environment}


# Bare /health alias for Docker HEALTHCHECK and Kubernetes liveness probes
# that probe the container directly (before the /api prefix is known).
@app.get("/health", tags=["health"], include_in_schema=False)
async def health_check_bare() -> dict:
    return {**_HEALTH_PAYLOAD, "environment": settings.environment}
