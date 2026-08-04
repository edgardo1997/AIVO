import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _now_ts() -> float:
    return time.monotonic()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _unjson(value: Any) -> Any:
    if not value:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value


class CloudAuthorityStore:
    """Durable storage for CloudAuthority state, policies and one-time consents.

    This store is the single durable owner for cloud authorization state. It
    stores no API keys, tokens, prompts or responses.
    """

    def __init__(self, db=None):
        self._db = db

    @property
    def _database(self):
        if self._db is not None:
            return self._db
        from repositories.database import DatabaseManager

        return DatabaseManager()

    def _execute(self, sql: str, params: tuple = ()):
        return self._database.execute(sql, params)

    def _transaction(self):
        return self._database.transaction(immediate=True)

    # ── State ──────────────────────────────────────────────────────────────

    def save_state(self, user_id: str, state: Dict[str, Any]) -> None:
        updated_at = _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO cloud_authority_state
                    (user_id, schema_version, onboarding_version, local_only, offline,
                     cloud_authorization_review_required, configured_provider,
                     configured_model, active_execution_state, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       schema_version = excluded.schema_version,
                       onboarding_version = excluded.onboarding_version,
                       local_only = excluded.local_only,
                       offline = excluded.offline,
                       cloud_authorization_review_required = excluded.cloud_authorization_review_required,
                       configured_provider = excluded.configured_provider,
                       configured_model = excluded.configured_model,
                       active_execution_state = excluded.active_execution_state,
                       updated_at = excluded.updated_at""",
                (
                    user_id,
                    int(state.get("schema_version", 1)),
                    state.get("onboarding_version", ""),
                    1 if state.get("local_only") else 0,
                    1 if state.get("offline") else 0,
                    1 if state.get("cloud_authorization_review_required") else 0,
                    state.get("configured_provider", ""),
                    state.get("configured_model", ""),
                    state.get("active_execution_state", "local_setup_required"),
                    updated_at,
                ),
            )

    def load_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self._database.fetchone(
            "SELECT * FROM cloud_authority_state WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return None
        return {
            "user_id": row["user_id"],
            "schema_version": row["schema_version"],
            "onboarding_version": row["onboarding_version"],
            "local_only": bool(row["local_only"]),
            "offline": bool(row["offline"]),
            "cloud_authorization_review_required": bool(row["cloud_authorization_review_required"]),
            "configured_provider": row["configured_provider"],
            "configured_model": row["configured_model"],
            "active_execution_state": row["active_execution_state"],
            "updated_at": row["updated_at"],
        }

    # ── Standing policies ──────────────────────────────────────────────────

    def _policy_row(self, row: Any) -> Dict[str, Any]:
        return {
            "policy_id": row["policy_id"],
            "user_id": row["user_id"],
            "provider_scope": _unjson(row["provider_scope"]),
            "model_scope": _unjson(row["model_scope"]),
            "purpose_scope": _unjson(row["purpose_scope"]),
            "data_classification_scope": _unjson(row["data_classification_scope"]),
            "paid_use_allowed": bool(row["paid_use_allowed"]),
            "automatic_fallback_allowed": bool(row["automatic_fallback_allowed"]),
            "max_cost_per_request": float(row["max_cost_per_request"]),
            "max_cost_per_period": float(row["max_cost_per_period"]),
            "currency": row["currency"],
            "issued_by": row["issued_by"],
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
            "policy_version": row["policy_version"],
            "updated_at": row["updated_at"],
        }

    def add_standing_policy(self, user_id: str, policy: Dict[str, Any]) -> str:
        policy_id = policy.get("policy_id") or f"pol_{uuid.uuid4().hex}"
        updated_at = _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cloud_standing_policies
                    (policy_id, user_id, provider_scope, model_scope, purpose_scope,
                     data_classification_scope, paid_use_allowed, automatic_fallback_allowed,
                     max_cost_per_request, max_cost_per_period, currency, issued_by,
                     issued_at, expires_at, revoked_at, policy_version, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    policy_id,
                    user_id,
                    _json(policy.get("provider_scope")),
                    _json(policy.get("model_scope")),
                    _json(policy.get("purpose_scope")),
                    _json(policy.get("data_classification_scope")),
                    1 if policy.get("paid_use_allowed") else 0,
                    1 if policy.get("automatic_fallback_allowed") else 0,
                    float(policy.get("max_cost_per_request", 0.0)),
                    float(policy.get("max_cost_per_period", 0.0)),
                    policy.get("currency", "USD"),
                    policy.get("issued_by", ""),
                    policy.get("issued_at") or _utc_now(),
                    policy.get("expires_at"),
                    policy.get("revoked_at"),
                    int(policy.get("policy_version", 1)),
                    updated_at,
                ),
            )
        return policy_id

    def revoke_standing_policy(self, user_id: str, policy_id: str, revoked_at: str) -> bool:
        with self._transaction() as conn:
            cursor = conn.execute(
                """UPDATE cloud_standing_policies
                   SET revoked_at = ?, updated_at = ?
                   WHERE user_id = ? AND policy_id = ?""",
                (revoked_at, _utc_now(), user_id, policy_id),
            )
            return cursor.rowcount > 0

    def list_standing_policies(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self._database.fetchall(
            """SELECT * FROM cloud_standing_policies
               WHERE user_id = ?
               ORDER BY updated_at DESC""",
            (user_id,),
        )
        return [self._policy_row(r) for r in rows]

    # ── One-time authorizations ────────────────────────────────────────────

    def _onetime_row(self, row: Any) -> Dict[str, Any]:
        return {
            "authorization_id": row["authorization_id"],
            "user_id": row["user_id"],
            "correlation_id": row["correlation_id"],
            "provider_scope": _unjson(row["provider_scope"]),
            "model_scope": _unjson(row["model_scope"]),
            "purpose_scope": _unjson(row["purpose_scope"]),
            "data_classification_scope": _unjson(row["data_classification_scope"]),
            "paid_use_allowed": bool(row["paid_use_allowed"]),
            "max_cost": float(row["max_cost"]),
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "consumed_at": row["consumed_at"],
            "revoked_at": row["revoked_at"],
            "updated_at": row["updated_at"],
        }

    def issue_one_time(self, user_id: str, auth: Dict[str, Any]) -> str:
        authorization_id = auth.get("authorization_id") or f"auth_{uuid.uuid4().hex}"
        updated_at = _utc_now()
        with self._transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO cloud_one_time_authorizations
                    (authorization_id, user_id, correlation_id, provider_scope, model_scope,
                     purpose_scope, data_classification_scope, paid_use_allowed, max_cost,
                     issued_at, expires_at, consumed_at, revoked_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    authorization_id,
                    user_id,
                    auth.get("correlation_id"),
                    _json(auth.get("provider_scope")),
                    _json(auth.get("model_scope")),
                    _json(auth.get("purpose_scope")),
                    _json(auth.get("data_classification_scope")),
                    1 if auth.get("paid_use_allowed") else 0,
                    float(auth.get("max_cost", 0.0)),
                    auth.get("issued_at") or _utc_now(),
                    auth.get("expires_at") or _iso_in(60),
                    auth.get("consumed_at"),
                    auth.get("revoked_at"),
                    updated_at,
                ),
            )
        return authorization_id

    def consume_one_time(self, user_id: str, authorization_id: str) -> bool:
        now = _utc_now()
        with self._transaction() as conn:
            cursor = conn.execute(
                """UPDATE cloud_one_time_authorizations
                   SET consumed_at = ?, updated_at = ?
                   WHERE user_id = ? AND authorization_id = ?
                         AND consumed_at IS NULL
                         AND revoked_at IS NULL
                         AND expires_at > ?""",
                (now, now, user_id, authorization_id, _utc_now()),
            )
            return cursor.rowcount > 0

    def list_one_time(self, user_id: str, consumed: Optional[bool] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cloud_one_time_authorizations WHERE user_id = ?"
        params: list = [user_id]
        if consumed is True:
            sql += " AND consumed_at IS NOT NULL"
        elif consumed is False:
            sql += " AND consumed_at IS NULL"
        sql += " ORDER BY updated_at DESC"
        rows = self._database.fetchall(sql, tuple(params))
        return [self._onetime_row(r) for r in rows]

    def delete_all_authority_data(self, user_id: str) -> Dict[str, int]:
        with self._transaction() as conn:
            state = conn.execute(
                "DELETE FROM cloud_authority_state WHERE user_id = ?", (user_id,)
            ).rowcount
            policies = conn.execute(
                "DELETE FROM cloud_standing_policies WHERE user_id = ?", (user_id,)
            ).rowcount
            onetimes = conn.execute(
                "DELETE FROM cloud_one_time_authorizations WHERE user_id = ?", (user_id,)
            ).rowcount
            return {"state": state, "policies": policies, "one_time": onetimes}
