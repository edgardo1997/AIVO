import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from repositories.cloud_authority_store import CloudAuthorityStore
from repositories.data_control_store import DataControlStore
from repositories.database import DatabaseManager
from repositories.user_preferences_store import UserPreferencesStore


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return f"u-c7-{uuid.uuid4().hex}"


@pytest.mark.alpha_constitutional_gate
class TestDataControl:
    def test_inventory_lists_user_data_categories(self):
        uid = _uid()
        db = DatabaseManager()
        store = DataControlStore(db)

        UserPreferencesStore(db).save(
            uid, {"configured_provider": "openrouter", "onboarding_completed": True}
        )
        CloudAuthorityStore(db).add_standing_policy(uid, {"provider_scope": ["openrouter"]})

        inv = store.inventory(uid)
        assert inv["user_id"] == uid
        assert inv["categories"]["user_preferences"]["present"] is True
        assert inv["categories"]["cloud_standing_policies"]["count"] == 1
        assert inv["categories"]["audit_records"]["deletable"] is False
        assert inv["categories"]["provider_side_data"]["deletable"] is False

    def test_export_contains_manifest_and_safe_metadata(self):
        uid = _uid()
        db = DatabaseManager()
        store = DataControlStore(db)

        UserPreferencesStore(db).save(uid, {"configured_provider": "openrouter"})
        CloudAuthorityStore(db).add_standing_policy(uid, {"provider_scope": ["openrouter"], "paid_use_allowed": True})

        export = store.export(uid, include_messages=False)
        assert export["export_schema_version"] == "1.0"
        assert "generated_at" in export
        assert "user_preferences" in export["data"]
        assert "cloud_standing_policies" in export["data"]

    def test_export_redacts_secrets(self):
        uid = _uid()
        db = DatabaseManager()
        store = DataControlStore(db)

        # Simulate a secret entering a conversation message via content.
        db.upsert_conversation(
            uid,
            "s1",
            "Test",
            [{"prompt": "hello", "response": "bearer sk-test-secret-value", "role": "assistant"}],
            _now(),
        )

        export = store.export(uid, include_messages=True)
        package_json = str(export)
        assert "sk-test-secret-value" not in package_json
        assert "REDACTED" in package_json

    def test_reset_removes_conversations_and_preferences(self):
        uid = _uid()
        db = DatabaseManager()
        store = DataControlStore(db)

        db.upsert_conversation(uid, "s1", "Test", [{"prompt": "hello", "response": "hi"}], _now())
        UserPreferencesStore(db).save(uid, {"configured_provider": "openrouter"})
        CloudAuthorityStore(db).add_standing_policy(uid, {"provider_scope": ["openrouter"]})

        result = store.reset(uid, ["conversations", "preferences", "cloud_authority"])
        assert "conversations" in result["deleted"]
        assert "user_preferences" in result["deleted"]
        assert "cloud_authority" in result["deleted"]
        assert "audit_records" in result["retained"]

        inv = store.inventory(uid)
        assert inv["categories"]["conversations"]["count"] == 0
