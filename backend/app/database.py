"""
app/database.py

Async SQLAlchemy engine and session factory.
Provides a FastAPI dependency (get_db) for injecting DB sessions into routes.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# pool_pre_ping=True — verifies connections before using them (handles DB
# restarts gracefully without "connection closed" errors in long-running apps).
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,       # connections kept in pool
    max_overflow=20,    # extra connections allowed beyond pool_size
    echo=settings.environment == "development",  # log SQL in dev only
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep ORM objects usable after commit
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Base class for all ORM models
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Declarative base — all SQLAlchemy models inherit from this."""
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session; roll back on error, close when done."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
