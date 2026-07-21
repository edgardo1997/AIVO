import os
import sqlite3
import threading

import pytest
from repositories import database
from repositories import async_engine


def _create_sqlite_db(path: str, value: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE marker (value TEXT NOT NULL)")
    conn.execute("INSERT INTO marker (value) VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _read_marker(path: str) -> str:
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT value FROM marker").fetchone()
    conn.close()
    return row[0]


@pytest.mark.unit
def test_resolve_database_path_prefers_sentinel_env(monkeypatch, tmp_path):
    sentinel_path = tmp_path / "sentinel.db"
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("SENTINEL_DB_PATH", str(sentinel_path))
    monkeypatch.setenv("AIVO_DB_PATH", str(legacy_path))

    assert database.resolve_database_path() == os.path.abspath(str(sentinel_path))


@pytest.mark.unit
def test_resolve_database_path_accepts_legacy_env(monkeypatch, tmp_path):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.delenv("SENTINEL_DB_PATH", raising=False)
    monkeypatch.setenv("AIVO_DB_PATH", str(legacy_path))

    assert database.resolve_database_path() == os.path.abspath(str(legacy_path))


@pytest.mark.unit
def test_migrate_legacy_database_copies_once(tmp_path):
    legacy_path = tmp_path / ".aivo.db"
    target_path = tmp_path / ".sentinel" / "sentinel.db"
    _create_sqlite_db(str(legacy_path), "legacy-data")

    migrated = database.migrate_legacy_database(str(target_path), str(legacy_path))

    assert migrated is True
    assert target_path.exists()
    assert _read_marker(str(target_path)) == "legacy-data"


@pytest.mark.unit
def test_migrate_legacy_database_does_not_overwrite_existing_target(tmp_path):
    legacy_path = tmp_path / ".aivo.db"
    target_path = tmp_path / ".sentinel" / "sentinel.db"
    target_path.parent.mkdir()
    _create_sqlite_db(str(legacy_path), "legacy-data")
    _create_sqlite_db(str(target_path), "sentinel-data")

    migrated = database.migrate_legacy_database(str(target_path), str(legacy_path))

    assert migrated is False
    assert _read_marker(str(target_path)) == "sentinel-data"


@pytest.mark.unit
def test_database_records_current_schema_version():
    db = database.DatabaseManager()

    assert db.schema_version == database.LATEST_SCHEMA_VERSION
    migration = db.fetchone(
        "SELECT description FROM schema_migrations WHERE version = ?",
        (database.LATEST_SCHEMA_VERSION,),
    )
    assert migration == {"description": database.DatabaseManager.MIGRATIONS[database.LATEST_SCHEMA_VERSION]}


@pytest.mark.unit
def test_newer_database_schema_is_rejected(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {database.LATEST_SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than this Sentinel build"):
        database._assert_supported_schema_version(conn)

    conn.close()


@pytest.mark.unit
def test_close_connections_closes_handles_from_worker_threads():
    db = database.DatabaseManager()
    worker_connections = []

    def open_worker_connection():
        worker_connections.append(db._get_conn())

    worker = threading.Thread(target=open_worker_connection)
    worker.start()
    worker.join()
    worker_conn = worker_connections[0]

    db.close_connections()

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        worker_conn.execute("SELECT 1")
    assert db.schema_version == database.LATEST_SCHEMA_VERSION


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_engine_rejects_unmigrated_schema(monkeypatch, tmp_path):
    await async_engine.close_async_engine()
    empty_database = tmp_path / "unmigrated.db"
    sqlite3.connect(empty_database).close()
    monkeypatch.setenv("SENTINEL_DB_PATH", str(empty_database))

    with pytest.raises(RuntimeError, match="does not match the required version"):
        await async_engine.init_async_db()

    await async_engine.close_async_engine()


@pytest.mark.security
def test_assert_safe_database_path_raises_for_production_path(monkeypatch):
    monkeypatch.setattr(database, "_TESTING", False)
    with pytest.raises(RuntimeError, match="Refusing to open a production database path"):
        database._assert_safe_database_path(database.SENTINEL_PRODUCTION_DB_PATH)


@pytest.mark.security
def test_assert_safe_database_path_raises_for_legacy_path(monkeypatch):
    monkeypatch.setattr(database, "_TESTING", False)
    with pytest.raises(RuntimeError, match="Refusing to open a production database path"):
        database._assert_safe_database_path(database.LEGACY_PRODUCTION_DB_PATH)


@pytest.mark.security
def test_assert_safe_database_path_allows_arbitrary_path(monkeypatch):
    monkeypatch.setattr(database, "_TESTING", False)
    database._assert_safe_database_path("/tmp/arbitrary/test.db")


@pytest.mark.security
def test_reset_for_testing_raises_when_testing_flag_is_false(monkeypatch):
    monkeypatch.setattr(database, "_TESTING", False)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    with pytest.raises(RuntimeError, match="reset_for_testing is available only when _TESTING is True"):
        db.reset_for_testing()
