"""Async and sync SQLAlchemy session factories."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from shorts_pipeline.config import Settings, get_settings


@lru_cache
def get_async_engine(url: str | None = None) -> AsyncEngine:
    """Create (cached) async engine."""
    settings = get_settings()
    return create_async_engine(
        url or settings.database_url,
        pool_pre_ping=True,
        echo=settings.debug,
    )


@lru_cache
def get_sync_engine(url: str | None = None) -> Engine:
    """Create (cached) sync engine (Alembic / Celery tasks)."""
    settings = get_settings()
    return create_engine(
        url or settings.database_url_sync,
        pool_pre_ping=True,
        echo=settings.debug,
    )


def async_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Build an async sessionmaker."""
    cfg = settings or get_settings()
    engine = get_async_engine(cfg.database_url)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async session."""
    factory = async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def get_sync_session(settings: Settings | None = None) -> Generator[Session, None, None]:
    """Context manager for sync sessions (workers)."""
    cfg = settings or get_settings()
    engine = get_sync_engine(cfg.database_url_sync)
    factory = sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def clear_engine_cache() -> None:
    """Clear cached engines (tests)."""
    get_async_engine.cache_clear()
    get_sync_engine.cache_clear()
