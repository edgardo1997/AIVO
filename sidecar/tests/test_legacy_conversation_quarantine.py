import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

from sentinel.storage.database import StorageConfig, StorageEngine
from sentinel.storage.models import ConversationRecord
from sentinel.storage.repositories.conversation_repository import ConversationRepository


@pytest_asyncio.fixture
async def isolated_storage_engine():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cfg = StorageConfig(database_url=f"sqlite:///{db_path}", migrate_on_start=True)
    engine = StorageEngine(cfg)
    await engine.initialize()
    try:
        yield engine
    finally:
        await engine.close()
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
class TestLegacyConversationQuarantine:
    async def test_legacy_repository_raises_on_production_construction(
        self, isolated_storage_engine
    ):
        """The legacy ConversationRepository cannot be constructed in production."""
        with pytest.raises(RuntimeError, match="legacy / quarantined"):
            ConversationRepository(isolated_storage_engine)

    async def test_legacy_repository_not_exported_from_public_package(self):
        """ConversationRepository is removed from the public sentinel.storage API."""
        import sentinel.storage

        assert "ConversationRepository" not in sentinel.storage.__all__
        assert not hasattr(sentinel.storage, "ConversationRepository")

    async def test_legacy_repository_can_be_opted_into_for_migration_tests(
        self, isolated_storage_engine
    ):
        """Explicit opt-in still works for migration evidence / compatibility."""
        repo = ConversationRepository(isolated_storage_engine, allow_legacy=True)
        await repo.save_message(
            ConversationRecord(
                session_id="legacy-test",
                role="user",
                content="quarantine check",
            )
        )
