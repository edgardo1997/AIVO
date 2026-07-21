"""Async SQLAlchemy sessions over Sentinel's canonical SQLite schema."""

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .database import LATEST_SCHEMA_VERSION, resolve_database_path

log = logging.getLogger("sentinel.db.async_engine")

_engine_lock = threading.Lock()
_async_engine_instance = None
_AsyncSessionFactory = None


def get_db_url() -> str:
    db_path = resolve_database_path()
    return f"sqlite+aiosqlite:///{os.path.abspath(db_path)}"


def get_async_engine():
    global _async_engine_instance, _AsyncSessionFactory
    if _async_engine_instance is not None:
        return _async_engine_instance, _AsyncSessionFactory

    with _engine_lock:
        if _async_engine_instance is not None:
            return _async_engine_instance, _AsyncSessionFactory

        db_url = get_db_url()
        engine = create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )

        _AsyncSessionFactory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _async_engine_instance = engine

        log.info(
            "Async DatabaseEngine initialized: %s (%s)",
            db_url,
            "SQLite (NullPool)",
        )
        return _async_engine_instance, _AsyncSessionFactory


async def init_async_db():
    """Validate the canonical schema without creating or altering it."""
    engine, _ = get_async_engine()
    async with engine.connect() as conn:
        version = int((await conn.execute(text("PRAGMA user_version"))).scalar_one())
        if version != LATEST_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} does not match the required "
                f"version {LATEST_SCHEMA_VERSION}."
            )
        result = await conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('user_profiles', 'user_preferences_v2')"
            )
        )
        tables = {str(row[0]) for row in result}
        required = {"user_profiles", "user_preferences_v2"}
        if missing := required - tables:
            raise RuntimeError(f"Database schema is missing required tables: {sorted(missing)}")
    log.info("Async database schema validated at version %d", version)


async def close_async_engine():
    global _async_engine_instance, _AsyncSessionFactory
    with _engine_lock:
        engine = _async_engine_instance
        _async_engine_instance = None
        _AsyncSessionFactory = None
    if engine:
        await engine.dispose()
        log.info("Async DatabaseEngine disposed")


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    _, factory = get_async_engine()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_async_session() -> AsyncSession:
    _, factory = get_async_engine()
    return factory()
