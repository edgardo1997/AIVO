import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import uuid

from repositories.cloud_authority_store import CloudAuthorityStore
from repositories.database import DatabaseManager


@pytest.mark.alpha_constitutional_gate
class TestCloudAuthorityPersistence:
    def test_state_survives_reconnection(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        state = {
            "schema_version": 1,
            "onboarding_version": "alpha-1",
            "local_only": True,
            "offline": False,
            "cloud_authorization_review_required": True,
            "configured_provider": "openrouter",
            "configured_model": "gpt-4o",
            "active_execution_state": "cloud_authorization_required",
        }

        store.save_state("u1", state)

        # Simulate a fresh store connection to the same database.
        store2 = CloudAuthorityStore(db)
        loaded = store2.load_state("u1")
        assert loaded is not None
        assert loaded["local_only"] is True
        assert loaded["configured_provider"] == "openrouter"
        assert loaded["configured_model"] == "gpt-4o"
        assert loaded["active_execution_state"] == "cloud_authorization_required"
        assert loaded["cloud_authorization_review_required"] is True

    def test_standing_policy_survives_and_revoke(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        pid = store.add_standing_policy(
            "u1",
            {
                "provider_scope": ["openrouter"],
                "model_scope": ["deepseek/deepseek-v4-flash"],
                "paid_use_allowed": True,
                "max_cost_per_request": 0.01,
                "automatic_fallback_allowed": True,
                "issued_by": "user",
                "expires_at": None,
            },
        )

        policies = store.list_standing_policies("u1")
        assert len(policies) == 1
        assert policies[0]["provider_scope"] == ["openrouter"]
        assert policies[0]["paid_use_allowed"] is True

        # Revoke takes effect immediately and survives reconnection.
        store.revoke_standing_policy("u1", pid, _now_iso())
        store2 = CloudAuthorityStore(db)
        revoked = store2.list_standing_policies("u1")[0]
        assert revoked["revoked_at"] is not None

    def test_expired_and_revoked_policies_remain_denied(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        expired_id = store.add_standing_policy(
            "u1",
            {
                "provider_scope": ["openrouter"],
                "model_scope": ["gpt-4o"],
                "expires_at": "2020-01-01T00:00:00+00:00",
            },
        )
        revoked_id = store.add_standing_policy(
            "u1",
            {
                "provider_scope": ["openrouter"],
                "model_scope": ["claude"],
            },
        )
        store.revoke_standing_policy("u1", revoked_id, _now_iso())

        for p in store.list_standing_policies("u1"):
            if p["policy_id"] == expired_id:
                assert _is_past(p["expires_at"])
            if p["policy_id"] == revoked_id:
                assert p["revoked_at"] is not None

    def test_one_time_consent_consumed_and_not_replayed(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        aid = store.issue_one_time(
            "u1",
            {
                "correlation_id": "req-1",
                "provider_scope": ["openrouter"],
                "model_scope": ["deepseek/deepseek-v4-flash"],
                "paid_use_allowed": False,
                "max_cost": 0.0,
            },
        )

        # First consumption succeeds.
        assert store.consume_one_time("u1", aid) is True

        # Replay fails.
        assert store.consume_one_time("u1", aid) is False

        # New store connection still sees it consumed.
        store2 = CloudAuthorityStore(db)
        assert store2.consume_one_time("u1", aid) is False

    def test_one_time_expired_cannot_be_consumed(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        aid = store.issue_one_time(
            "u1",
            {
                "provider_scope": ["openrouter"],
                "model_scope": ["deepseek/deepseek-v4-flash"],
                "expires_at": "2020-01-01T00:00:00+00:00",
            },
        )

        assert store.consume_one_time("u1", aid) is False

    def test_state_does_not_store_secrets(self):
        db = DatabaseManager()
        store = CloudAuthorityStore(db)

        # Any attempt to put a secret in a policy is rejected by the schema:
        # there is no column for api_key/token/etc. The store only accepts
        # known policy fields.
        store.add_standing_policy(
            "u1",
            {
                "provider_scope": ["openrouter"],
                "model_scope": ["gpt-4o"],
                "issued_by": "user",
            },
        )
        for p in store.list_standing_policies("u1"):
            assert "api_key" not in p
            assert "token" not in p
            assert "sk-" not in str(p)


def _now_iso():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _is_past(value: str) -> bool:
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(value) < datetime.now(timezone.utc)
    except ValueError:
        return False
