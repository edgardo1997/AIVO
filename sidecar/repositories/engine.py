"""SQLAlchemy engine with connection pool and WAL mode for concurrent access."""

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .database import DB_PATH, resolve_database_path
from .models import Base

log = logging.getLogger("sentinel.db.engine")

_engine_lock = threading.Lock()
_engine_instance = None
_SessionFactory = None


def get_engine():
    global _engine_instance, _SessionFactory
    if _engine_instance is not None:
        return _engine_instance, _SessionFactory

    with _engine_lock:
        if _engine_instance is not None:
            return _engine_instance, _SessionFactory

        db_path = resolve_database_path()
        db_url = f"sqlite:///{os.path.abspath(db_path)}"

        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-8000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456")
            cursor.close()

        Base.metadata.create_all(engine)

        with engine.connect() as conn:
            existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(audit_log)")).fetchall()}
            extra_cols = {
                "event_id": "TEXT",
                "execution_id": "TEXT",
                "payload": "TEXT NOT NULL DEFAULT '{}'",
                "previous_hash": "TEXT NOT NULL DEFAULT ''",
                "entry_hash": "TEXT",
            }
            for col, decl in extra_cols.items():
                if col not in existing_cols:
                    conn.execute(text(f"ALTER TABLE audit_log ADD COLUMN {col} {decl}"))
            conn.commit()

        _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        _engine_instance = engine

        log.info("DatabaseEngine initialized with pool_size=5, overflow=10, WAL mode enabled, schema migrated")
        return _engine_instance, _SessionFactory


def get_session() -> Session:
    _, factory = get_engine()
    return factory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_engine():
    global _engine_instance, _SessionFactory
    with _engine_lock:
        if _engine_instance:
            _engine_instance.dispose()
            _engine_instance = None
            _SessionFactory = None
            log.info("DatabaseEngine disposed")
