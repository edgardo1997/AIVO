import os
import sqlite3

from repositories import database


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


def test_resolve_database_path_prefers_sentinel_env(monkeypatch, tmp_path):
    sentinel_path = tmp_path / "sentinel.db"
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("SENTINEL_DB_PATH", str(sentinel_path))
    monkeypatch.setenv("AIVO_DB_PATH", str(legacy_path))

    assert database.resolve_database_path() == os.path.abspath(str(sentinel_path))


def test_resolve_database_path_accepts_legacy_env(monkeypatch, tmp_path):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.delenv("SENTINEL_DB_PATH", raising=False)
    monkeypatch.setenv("AIVO_DB_PATH", str(legacy_path))

    assert database.resolve_database_path() == os.path.abspath(str(legacy_path))


def test_migrate_legacy_database_copies_once(tmp_path):
    legacy_path = tmp_path / ".aivo.db"
    target_path = tmp_path / ".sentinel" / "sentinel.db"
    _create_sqlite_db(str(legacy_path), "legacy-data")

    migrated = database.migrate_legacy_database(str(target_path), str(legacy_path))

    assert migrated is True
    assert target_path.exists()
    assert _read_marker(str(target_path)) == "legacy-data"


def test_migrate_legacy_database_does_not_overwrite_existing_target(tmp_path):
    legacy_path = tmp_path / ".aivo.db"
    target_path = tmp_path / ".sentinel" / "sentinel.db"
    target_path.parent.mkdir()
    _create_sqlite_db(str(legacy_path), "legacy-data")
    _create_sqlite_db(str(target_path), "sentinel-data")

    migrated = database.migrate_legacy_database(str(target_path), str(legacy_path))

    assert migrated is False
    assert _read_marker(str(target_path)) == "sentinel-data"
