"""
alembic/env.py

Async-compatible Alembic environment configuration.

Key design decisions:
- Uses asyncpg driver via SQLAlchemy async engine
- Imports all ORM models so Alembic autogenerate can detect schema changes
- DATABASE_URL is read from app settings (not alembic.ini) for consistency
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------------
# Import all models so Alembic can see them for autogenerate
# ---------------------------------------------------------------------------
# NOTE: order of imports matters — Base must be imported after all models
# so that the metadata is populated.
from app.database import Base  # noqa: F401
import app.models  # noqa: F401 — triggers __init__.py which imports all models

from app.config import get_settings

# ---------------------------------------------------------------------------
# Alembic config
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the sqlalchemy.url with our app settings so we have a single
# source of truth for the database URL.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# The metadata Alembic uses for autogenerate comparison
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (no live DB connection needed).
    Useful for generating SQL scripts for manual review.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # detect column type changes
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations — required for asyncpg."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # use NullPool in migration context
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to a live DB)."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
