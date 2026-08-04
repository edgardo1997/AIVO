import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from repositories.database import DatabaseManager
from repositories.user_preferences_store import UserPreferencesStore


@pytest.mark.alpha_constitutional_gate
class TestUserPreferencesPersistence:
    def test_preferences_survive_reconnection(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        state = {
            "onboarding_version": "alpha-1",
            "onboarding_completed": True,
            "configured_provider": "openrouter",
            "configured_model": "deepseek/deepseek-v4-flash",
            "preferred_model_tier": "free",
            "local_only": False,
            "offline_preference": False,
            "automatic_cloud_fallback_preference": False,
            "language": "es",
            "permission_defaults": "confirm",
            "cost_currency": "EUR",
            "maximum_cost_per_request": 0.05,
            "maximum_cost_per_period": 1.0,
            "active_execution_state": "cloud_authorization_required",
            "active_execution_reason": "Cloud provider configured but not authorized.",
        }

        store.save("u1", state)

        store2 = UserPreferencesStore(db)
        loaded = store2.load("u1")
        assert loaded["configured_provider"] == "openrouter"
        assert loaded["configured_model"] == "deepseek/deepseek-v4-flash"
        assert loaded["language"] == "es"
        assert loaded["cost_currency"] == "EUR"
        assert loaded["maximum_cost_per_request"] == 0.05
        assert loaded["active_execution_state"] == "cloud_authorization_required"

    def test_safe_defaults_for_new_user(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        loaded = store.load("new-user")
        assert loaded["configured_provider"] == ""
        assert loaded["configured_model"] == ""
        assert loaded["local_only"] is False
        assert loaded["automatic_cloud_fallback_preference"] is False
        assert loaded["maximum_cost_per_request"] == 0.0
        assert loaded["active_execution_state"] == "setup_required"

    def test_invalid_combinations_rejected(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        bad = {
            "local_only": True,
            "automatic_cloud_fallback_preference": True,
        }
        with pytest.raises(ValueError):
            store.save("u1", bad)

        bad2 = {
            "maximum_cost_per_request": -1.0,
        }
        with pytest.raises(ValueError):
            store.save("u1", bad2)

    def test_reset_restores_safe_defaults(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        store.save(
            "u1",
            {
                "configured_provider": "openrouter",
                "local_only": False,
                "maximum_cost_per_request": 0.1,
            },
        )

        store.reset("u1")
        loaded = store.load("u1")
        assert loaded["configured_provider"] == ""
        assert loaded["maximum_cost_per_request"] == 0.0
        assert loaded["active_execution_state"] == "setup_required"

    def test_local_only_survives_restart(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        store.patch("u1", {"local_only": True, "active_execution_state": "local_only"})

        store2 = UserPreferencesStore(db)
        loaded = store2.load("u1")
        assert loaded["local_only"] is True
        assert loaded["active_execution_state"] == "local_only"

    def test_cloud_rejection_survives_restart(self):
        db = DatabaseManager()
        store = UserPreferencesStore(db)

        store.patch(
            "u1",
            {
                "configured_provider": "",
                "active_execution_state": "cloud_authorization_required",
                "active_execution_reason": "User rejected cloud execution.",
            },
        )

        store2 = UserPreferencesStore(db)
        loaded = store2.load("u1")
        assert loaded["active_execution_reason"] == "User rejected cloud execution."
