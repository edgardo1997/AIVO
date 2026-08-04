import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "onboarding_version": "alpha-1",
        "onboarding_completed": False,
        "configured_provider": "",
        "configured_model": "",
        "preferred_model_tier": "",
        "local_only": False,
        "offline_preference": False,
        "automatic_cloud_fallback_preference": False,
        "language": "en",
        "permission_defaults": "confirm",
        "cost_currency": "USD",
        "maximum_cost_per_request": 0.0,
        "maximum_cost_per_period": 0.0,
        "active_execution_state": "setup_required",
        "active_execution_reason": "No explicit runtime preference has been established.",
        "active_execution_at": _utc_now(),
        "updated_at": _utc_now(),
    }


def _validate(state: Dict[str, Any]) -> None:
    if state.get("local_only") and state.get("automatic_cloud_fallback_preference"):
        raise ValueError("local_only and automatic_cloud_fallback_preference cannot both be true")
    if state.get("maximum_cost_per_request", 0.0) < 0:
        raise ValueError("maximum_cost_per_request cannot be negative")
    if state.get("maximum_cost_per_period", 0.0) < 0:
        raise ValueError("maximum_cost_per_period cannot be negative")
    if state.get("permission_defaults") not in ("view", "confirm", "auto", "admin"):
        raise ValueError("permission_defaults must be one of: view, confirm, auto, admin")


class UserPreferencesStore:
    """Durable, versioned, single owner for user preferences and active state.

    Preferences are separate from credentials, cloud authorization and
    conversation history. The store never persists API keys, tokens or secrets.
    """

    def __init__(self, db=None):
        self._db = db

    @property
    def _database(self):
        if self._db is not None:
            return self._db
        from repositories.database import DatabaseManager

        return DatabaseManager()

    def _transaction(self):
        return self._database.transaction(immediate=True)

    def save(self, user_id: str, state: Dict[str, Any]) -> None:
        state = {**_safe_state(), **state, "updated_at": _utc_now()}
        _validate(state)
        updated_at = _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO user_preferences_state
                    (user_id, schema_version, onboarding_version, onboarding_completed,
                     configured_provider, configured_model, preferred_model_tier,
                     local_only, offline_preference, automatic_cloud_fallback_preference,
                     language, permission_defaults, cost_currency,
                     maximum_cost_per_request, maximum_cost_per_period,
                     active_execution_state, active_execution_reason, active_execution_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       schema_version = excluded.schema_version,
                       onboarding_version = excluded.onboarding_version,
                       onboarding_completed = excluded.onboarding_completed,
                       configured_provider = excluded.configured_provider,
                       configured_model = excluded.configured_model,
                       preferred_model_tier = excluded.preferred_model_tier,
                       local_only = excluded.local_only,
                       offline_preference = excluded.offline_preference,
                       automatic_cloud_fallback_preference = excluded.automatic_cloud_fallback_preference,
                       language = excluded.language,
                       permission_defaults = excluded.permission_defaults,
                       cost_currency = excluded.cost_currency,
                       maximum_cost_per_request = excluded.maximum_cost_per_request,
                       maximum_cost_per_period = excluded.maximum_cost_per_period,
                       active_execution_state = excluded.active_execution_state,
                       active_execution_reason = excluded.active_execution_reason,
                       active_execution_at = excluded.active_execution_at,
                       updated_at = excluded.updated_at""",
                (
                    user_id,
                    int(state.get("schema_version", 1)),
                    state.get("onboarding_version", ""),
                    1 if state.get("onboarding_completed") else 0,
                    state.get("configured_provider", ""),
                    state.get("configured_model", ""),
                    state.get("preferred_model_tier", ""),
                    1 if state.get("local_only") else 0,
                    1 if state.get("offline_preference") else 0,
                    1 if state.get("automatic_cloud_fallback_preference") else 0,
                    state.get("language", "en"),
                    state.get("permission_defaults", "confirm"),
                    state.get("cost_currency", "USD"),
                    float(state.get("maximum_cost_per_request", 0.0)),
                    float(state.get("maximum_cost_per_period", 0.0)),
                    state.get("active_execution_state", "setup_required"),
                    state.get("active_execution_reason", ""),
                    state.get("active_execution_at") or _utc_now(),
                    updated_at,
                ),
            )

    def load(self, user_id: str) -> Dict[str, Any]:
        row = self._database.fetchone(
            "SELECT * FROM user_preferences_state WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return _safe_state()
        return {
            "schema_version": row["schema_version"],
            "onboarding_version": row["onboarding_version"],
            "onboarding_completed": bool(row["onboarding_completed"]),
            "configured_provider": row["configured_provider"],
            "configured_model": row["configured_model"],
            "preferred_model_tier": row["preferred_model_tier"],
            "local_only": bool(row["local_only"]),
            "offline_preference": bool(row["offline_preference"]),
            "automatic_cloud_fallback_preference": bool(row["automatic_cloud_fallback_preference"]),
            "language": row["language"],
            "permission_defaults": row["permission_defaults"],
            "cost_currency": row["cost_currency"],
            "maximum_cost_per_request": float(row["maximum_cost_per_request"]),
            "maximum_cost_per_period": float(row["maximum_cost_per_period"]),
            "active_execution_state": row["active_execution_state"],
            "active_execution_reason": row["active_execution_reason"],
            "active_execution_at": row["active_execution_at"],
            "updated_at": row["updated_at"],
        }

    def patch(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        current = self.load(user_id)
        new_state = {**current, **updates, "updated_at": _utc_now()}
        self.save(user_id, new_state)
        return self.load(user_id)

    def reset(self, user_id: str) -> Dict[str, Any]:
        defaults = _safe_state()
        self.save(user_id, defaults)
        return self.load(user_id)
