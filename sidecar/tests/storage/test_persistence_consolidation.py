"""P2-7: Single-file persistence consolidation.

Guards the contract that DatabaseManager (sidecar schema) and StorageEngine
(intelligence schema) share the same SQLite file without clobbering each
other's schema version or colliding on table names.
"""

import os

import pytest
import pytest_asyncio

from repositories.database import DatabaseManager, resolve_database_path
from sentinel.storage.database import StorageEngine, StorageConfig
from sentinel.storage.models import UserPreference
from sentinel.storage.repositories.user_preference_repository import UserPreferenceRepository


@pytest.fixture
def shared_db_path(tmp_path):
    path = str(tmp_path / "shared.db")
    return path


def _clear_storage_overrides(monkeypatch):
    """Keep only SENTINEL_DB_PATH so both backends resolve through it."""
    monkeypatch.delenv("SENTINEL_STORAGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("SENTINEL_DATABASE_URL", raising=False)
    monkeypatch.delenv("SENTINEL_STORAGE_DB_PATH", raising=False)
    monkeypatch.delenv("SENTINEL_DATA_DIR", raising=False)


def test_both_backends_resolve_to_same_file(shared_db_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DB_PATH", shared_db_path)
    _clear_storage_overrides(monkeypatch)

    sidecar_db = resolve_database_path()
    storage = StorageEngine()

    assert storage._resolve_url().endswith(shared_db_path)
    assert os.path.normcase(sidecar_db) == os.path.normcase(shared_db_path)


@pytest_asyncio.fixture
async def merged_engine(monkeypatch):
    sidecar = DatabaseManager()
    eng = StorageEngine(StorageConfig(database_url=f"sqlite:///{sidecar.db_path}", migrate_on_start=True))
    await eng.initialize()
    yield eng, sidecar.db_path
    await eng.close()


@pytest.mark.asyncio
async def test_storage_engine_and_sidecar_coexist_single_file(merged_engine):
    eng, db_path = merged_engine
    sidecar = DatabaseManager()
    assert os.path.normcase(sidecar.db_path) == os.path.normcase(db_path)

    # Sidecar writes its own domain tables.
    sidecar.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('consolidation_marker', 'ok')")
    sidecar.commit()

    # Intelligence writes its own (renamed) preference table.
    repo = UserPreferenceRepository(eng)
    await repo.save(UserPreference(user_id="u-merge", key="response_style", value="concise", source="explicit"))

    # Sidecar data survives the intelligence write.
    assert sidecar.fetchone("SELECT value FROM config WHERE key = 'consolidation_marker'")["value"] == "ok"
    assert await repo.get("u-merge", "response_style") is not None

    # Versions are tracked independently: sidecar user_version is untouched by
    # the intelligence engine, and intelligence version >= 2.
    assert sidecar.schema_version >= 10
    assert await eng._schema_version() >= 2

    # No table-name collision: intelligence preferences live in their own table.
    assert sidecar.fetchone("SELECT COUNT(*) AS c FROM intelligence_user_preferences")["c"] >= 1


@pytest.mark.asyncio
async def test_intelligence_records_survive_reopen_in_same_file(merged_engine):
    eng, db_path = merged_engine
    repo = UserPreferenceRepository(eng)
    await repo.save(UserPreference(user_id="u-reopen", key="privacy", value="strict", source="explicit"))
    await eng.close()

    reopened = StorageEngine(StorageConfig(database_url=f"sqlite:///{db_path}", migrate_on_start=True))
    await reopened.initialize()
    try:
        repo2 = UserPreferenceRepository(reopened)
        pref = await repo2.get("u-reopen", "privacy")
        assert pref is not None and pref.value == "strict"
    finally:
        await reopened.close()


def test_sidecar_db_path_matches_storage_engine_default(shared_db_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DB_PATH", shared_db_path)
    _clear_storage_overrides(monkeypatch)

    sidecar_db = resolve_database_path()
    storage = StorageEngine()
    resolved = storage._resolve_url().replace("sqlite:///", "")
    assert os.path.normcase(resolved) == os.path.normcase(sidecar_db)
