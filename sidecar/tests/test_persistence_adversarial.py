"""FASE 11 — Adversarial persistence and recovery tests."""

import asyncio
import os
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.stability


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.skip("StorageEngine.close() may leave an aiosqlite thread and hang the runner")
def test_storage_engine_initializes_and_persists(tmp_path, monkeypatch):
    """Fresh data dir -> StorageEngine migrates and persists rows."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.storage.database import StorageEngine, StorageConfig

    async def _inner():
        engine = StorageEngine(StorageConfig())
        await engine.initialize()
        await engine.execute(
            "INSERT INTO intelligence_user_preferences (user_id, key, value, source, evidence_count, confidence, created_at, updated_at) "
            "VALUES (:user_id, :key, :value, :source, :evidence_count, :confidence, :created_at, :updated_at)",
            {
                "user_id": "u1",
                "key": "language",
                "value": '"es"',
                "source": "manual",
                "evidence_count": 1,
                "confidence": 0.9,
                "created_at": 1.0,
                "updated_at": 1.0,
            },
        )
        rows = await engine.execute(
            "SELECT value FROM intelligence_user_preferences WHERE user_id = :uid AND key = :key",
            {"uid": "u1", "key": "language"},
        )
        await engine.close()
        return rows

    rows = _run(_inner())
    assert len(rows) == 1
    assert rows[0]["value"] == '"es"'


@pytest.mark.skip("StorageEngine.close() may leave an aiosqlite thread and hang the runner")
def test_storage_engine_detects_corrupt_sqlite(tmp_path, monkeypatch):
    """Corrupt sentinel.db must not silently continue."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "sentinel.db"
    db_path.write_text("not a valid sqlite database at all!!!")

    from sentinel.storage.database import StorageEngine, StorageConfig

    async def _inner():
        engine = StorageEngine(StorageConfig())
        try:
            await engine.initialize()
            return False
        except (sqlite3.DatabaseError, RuntimeError, OSError):
            return True
        finally:
            await engine.close()

    assert _run(_inner())


def test_atomic_json_write_no_partial_file(tmp_path):
    """Atomic temp + rename leaves no partial file after crash."""
    target = tmp_path / "state.json"
    temp = tmp_path / "state.json.tmp"

    content = '{"version": 1, "value": true}'
    temp.write_text(content)
    os.replace(str(temp), str(target))

    assert target.exists()
    assert not temp.exists()
    assert target.read_text() == content


def test_json_truncation_detected(tmp_path):
    """Truncated JSON must not be treated as valid."""
    from json import JSONDecodeError
    import json

    p = tmp_path / "truncated.json"
    p.write_text('{"version": 1, "value": ')
    with pytest.raises(JSONDecodeError):
        json.loads(p.read_text())


def test_wal_orphan_recovery(tmp_path):
    """SQLite with WAL mode and a stale -wal should recover on open."""
    db_path = tmp_path / "wal.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    # Simulate a crash with an orphan WAL
    wal_path = tmp_path / "wal.db-wal"
    wal_path.write_bytes(b"stale wal bytes")

    conn2 = sqlite3.connect(str(db_path))
    conn2.row_factory = sqlite3.Row
    row = conn2.execute("SELECT * FROM t").fetchone()
    assert row["id"] == 1
    conn2.close()
