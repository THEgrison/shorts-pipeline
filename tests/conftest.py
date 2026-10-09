"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure test env before importing app settings
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault(
    "FERNET_KEY",
    "dGVzdC1mZXJuZXQta2V5LTMyYnl0ZXMhMTIzNDU2Nzg=",  # may fall back to derived
)

from shorts_pipeline.config import clear_settings_cache, get_settings
from shorts_pipeline.db import models as _models  # noqa: F401
from shorts_pipeline.db.base import Base
from shorts_pipeline.db.session import clear_engine_cache


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    clear_settings_cache()
    clear_engine_cache()
    yield
    clear_settings_cache()
    clear_engine_cache()


@pytest.fixture
def settings(tmp_path: Path):
    clear_settings_cache()
    os.environ["STORAGE_LOCAL_ROOT"] = str(tmp_path / "storage")
    os.environ["STORAGE_TEMP_DIR"] = str(tmp_path / "tmp")
    return get_settings()


@pytest.fixture
def sync_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sync_session(sync_engine) -> Generator[Session, None, None]:
    factory = sessionmaker(sync_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    clear_settings_cache()
    from shorts_pipeline.api.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
