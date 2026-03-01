"""Database session management.

Provides async SQLAlchemy 2.0 session management with connection pooling
and a FastAPI dependency for per-request sessions.

Schema management is handled exclusively by Alembic migrations.
Run `alembic upgrade head` (or `python scripts/migrate.py`) before first deployment.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..core.config import Settings, get_settings

log = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""


class DatabaseManager:
    """Manages PostgreSQL async connection pool and session factory."""

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _create_engine(self) -> AsyncEngine:
        """Create the async SQLAlchemy engine."""
        engine = create_async_engine(
            self.settings.DATABASE_URL,
            echo=self.settings.DATABASE_ECHO,
            pool_size=self.settings.DATABASE_POOL_SIZE,
            max_overflow=self.settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=self.settings.DATABASE_POOL_TIMEOUT,
            pool_pre_ping=True,
        )
        log.info(
            "db_engine_created",
            pool_size=self.settings.DATABASE_POOL_SIZE,
            max_overflow=self.settings.DATABASE_MAX_OVERFLOW,
        )
        return engine

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        return self._session_factory

    async def close(self) -> None:
        """Dispose the connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            log.info("db_connections_closed")

    async def health_check(self) -> dict[str, Any]:
        """Ping the database. Returns {'status': 'healthy'|'unhealthy'}."""
        from sqlalchemy import text
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "healthy", "error": None}
        except Exception as exc:
            log.error("db_health_check_failed", error=str(exc))
            return {"status": "unhealthy", "error": str(exc)}

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Async context manager that yields a session, commits or rolls back."""
        async_session = self.session_factory()
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise
        finally:
            await async_session.close()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Return the process-level DatabaseManager singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a per-request async database session."""
    async with get_db_manager().session() as session:
        yield session


async def close_db() -> None:
    """Close all database connections (called on application shutdown)."""
    if _db_manager is not None:
        await get_db_manager().close()


# Type alias for clean endpoint signatures
DbSession = Annotated[AsyncSession, Depends(get_db)]
