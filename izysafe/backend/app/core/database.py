"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

The app uses the **async** engine (asyncpg). Alembic migrations use a separate
**sync** engine (psycopg2) — see alembic/env.py — so we never run async DDL.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Pooling sized per CLAUDE.md scaling notes (min 10 / max ~50 effective).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=40,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Yields a session and guarantees close/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
