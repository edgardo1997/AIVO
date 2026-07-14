"""Async SQLAlchemy engine with connection pool.

Supports both SQLite (aiosqlite) and PostgreSQL (asyncpg).
Swap DB_URL to switch: sqlite+aiosqlite:// or postgresql+asyncpg://
"""

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from .database import DB_PATH, resolve_database_path
from .models import Base

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
        is_sqlite = "sqlite" in db_url

        if is_sqlite:
            engine = create_async_engine(
                db_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )
        else:
            engine = create_async_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False,
            )

        _AsyncSessionFactory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _async_engine_instance = engine

        log.info(
            "Async DatabaseEngine initialized: %s (%s)",
            db_url, "SQLite (NullPool)" if is_sqlite else "PostgreSQL (pool_size=10, overflow=20)",
        )
        return _async_engine_instance, _AsyncSessionFactory


async def init_async_db():
    """Create all tables. Safe to call multiple times (IF NOT EXISTS)."""
    engine, _ = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in str(engine.url):
            from sqlalchemy import text
            existing_cols = set()
            result = await conn.execute(text("PRAGMA table_info(audit_log)"))
            for row in result:
                existing_cols.add(row[1])
            extra_cols = {
                "event_id": "TEXT",
                "execution_id": "TEXT",
                "payload": "TEXT NOT NULL DEFAULT '{}'",
                "previous_hash": "TEXT NOT NULL DEFAULT ''",
                "entry_hash": "TEXT",
            }
            for col, decl in extra_cols.items():
                if col not in existing_cols:
                    await conn.execute(text(f"ALTER TABLE audit_log ADD COLUMN {col} {decl}"))
    log.info("Async database schema initialized")


async def close_async_engine():
    global _async_engine_instance, _AsyncSessionFactory
    with _engine_lock:
        if _async_engine_instance:
            await _async_engine_instance.dispose()
            _async_engine_instance = None
            _AsyncSessionFactory = None
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
