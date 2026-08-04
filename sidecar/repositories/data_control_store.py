import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_value(value: Any, found: List[str]) -> Any:
    if isinstance(value, dict):
        return _redact(value, found)
    if isinstance(value, list):
        return [_redact_value(item, found) for item in value]
    if isinstance(value, str):
        if _looks_secret(value):
            found.append(type(value).__name__)
            return "REDACTED"
    return value


_SECRET_KEYS = {
    "api_key", "api-key", "apikey",
    "token", "access_token", "refresh_token",
    "secret", "client_secret", "api_secret",
    "password", "passphrase",
    "bearer", "authorization",
    "cookie", "session_cookie",
    "connection_string", "dsn", "uri",
    "private_key", "signing_key",
    "credential", "credentials",
    "vault_key", "vault_secret",
}


_SECRET_PATTERNS = [
    re.compile(r"^[a-zA-Z0-9_-]*key.*=.*", re.IGNORECASE),
    re.compile(r"^[Bb]earer\s+"),
    re.compile(r"^sk-"),
    re.compile(r"^sk_"),
]


def _looks_secret(value: str) -> bool:
    if len(value) > 1000:
        return False
    for pat in _SECRET_PATTERNS:
        if pat.match(value):
            return True
    return False


def _redact(obj: Any, found: Optional[List[str]] = None) -> Any:
    found = found if found is not None else []
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            lowered = k.lower().replace("-", "_")
            if lowered in _SECRET_KEYS or "key" in lowered or "token" in lowered or "secret" in lowered or "password" in lowered:
                if v:
                    found.append(k)
                    result[k] = "REDACTED"
                else:
                    result[k] = v
            else:
                result[k] = _redact_value(v, found)
        return result
    if isinstance(obj, list):
        return [_redact_value(item, found) for item in obj]
    if isinstance(obj, str) and _looks_secret(obj):
        found.append("inline")
        return "REDACTED"
    return obj


class DataControlStore:
    """Inspect, export, delete and reset Alpha user data truthfully."""

    EXPORT_SCHEMA_VERSION = "1.0"

    def __init__(self, db=None):
        self._db = db

    @property
    def _database(self):
        if self._db is not None:
            return self._db
        from repositories.database import DatabaseManager

        return DatabaseManager()

    def _count(self, sql: str, params: tuple = ()) -> int:
        row = self._database.fetchone(sql, params)
        if row is None:
            return 0
        return next(iter(row.values())) or 0

    # ── Inventory ──────────────────────────────────────────────────────────

    def inventory(self, user_id: str) -> Dict[str, Any]:
        conversation_count = self._count(
            "SELECT COUNT(*) FROM conversation_threads WHERE user_id = ?", (user_id,)
        )
        message_count = self._count(
            "SELECT COUNT(*) FROM conversation_messages_v2 WHERE user_id = ?", (user_id,)
        )
        policy_count = self._count(
            "SELECT COUNT(*) FROM cloud_standing_policies WHERE user_id = ?", (user_id,)
        )
        onetime_count = self._count(
            "SELECT COUNT(*) FROM cloud_one_time_authorizations WHERE user_id = ?", (user_id,)
        )
        audit_count = self._count("SELECT COUNT(*) FROM audit_log")

        has_preferences = self._database.fetchone(
            "SELECT 1 FROM user_preferences_state WHERE user_id = ?", (user_id,)
        ) is not None

        return {
            "user_id": user_id,
            "generated_at": _utc_now(),
            "categories": {
                "conversations": {
                    "count": conversation_count,
                    "source": "conversation_threads",
                    "deletable": True,
                },
                "conversation_messages": {
                    "count": message_count,
                    "source": "conversation_messages_v2",
                    "deletable": True,
                },
                "user_preferences": {
                    "present": has_preferences,
                    "source": "user_preferences_state",
                    "deletable": True,
                },
                "cloud_standing_policies": {
                    "count": policy_count,
                    "source": "cloud_standing_policies",
                    "deletable": True,
                },
                "cloud_one_time_authorizations": {
                    "count": onetime_count,
                    "source": "cloud_one_time_authorizations",
                    "deletable": True,
                },
                "audit_records": {
                    "count": audit_count,
                    "source": "audit_log",
                    "deletable": False,
                    "reason": "security and governance evidence retained by policy",
                },
                "diagnostic_logs": {
                    "present": True,
                    "deletable": False,
                    "reason": "application logs and diagnostics are outside Alpha user-deletion scope",
                },
                "backups": {
                    "present": True,
                    "deletable": False,
                    "reason": "migration and database backups may retain historical records",
                },
                "provider_side_data": {
                    "present": True,
                    "deletable": False,
                    "reason": "Sentinel cannot guarantee deletion from external providers; governed by provider terms",
                },
            },
        }

    # ── Export ─────────────────────────────────────────────────────────────

    def export(self, user_id: str, include_messages: bool = True) -> Dict[str, Any]:
        from repositories.cloud_authority_store import CloudAuthorityStore
        from repositories.user_preferences_store import UserPreferencesStore

        manifest = {
            "export_schema_version": self.EXPORT_SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "platform": "sentinel-alpha",
            "user_id": user_id,
        }

        redactions: List[str] = []

        conversations = self._database.list_conversations(user_id, limit=10000)
        if not include_messages:
            for c in conversations:
                c.pop("messages", None)
        else:
            for c in conversations:
                c["messages"] = _redact(c.get("messages", []), redactions)
        conversations = _redact(conversations, redactions)

        messages_v2 = self._database.fetchall(
            """SELECT * FROM conversation_messages_v2
               WHERE user_id = ? ORDER BY sequence""",
            (user_id,),
        )
        for m in messages_v2:
            if m.get("audit_refs") and isinstance(m["audit_refs"], str):
                try:
                    m["audit_refs"] = json.loads(m["audit_refs"])
                except json.JSONDecodeError:
                    m["audit_refs"] = []
        messages_v2 = _redact(messages_v2, redactions)

        pref_store = UserPreferencesStore(self._database)
        preferences = _redact(pref_store.load(user_id), redactions)

        ca_store = CloudAuthorityStore(self._database)
        cloud_policies = _redact(ca_store.list_standing_policies(user_id), redactions)
        cloud_onetime = _redact(ca_store.list_one_time(user_id), redactions)

        package = {
            **manifest,
            "included_categories": [
                "conversations", "conversation_messages_v2", "user_preferences",
                "cloud_standing_policies", "cloud_one_time_authorizations",
            ],
            "excluded_categories": ["diagnostic_logs", "backups", "provider_side_data"],
            "retained_categories": ["audit_records"],
            "redaction_summary": list(set(redactions)),
            "data": {
                "conversations": conversations,
                "conversation_messages_v2": messages_v2,
                "user_preferences": preferences,
                "cloud_standing_policies": cloud_policies,
                "cloud_one_time_authorizations": cloud_onetime,
            },
        }

        # Final defensive redaction pass over the whole package.
        return _redact(package, redactions)

    # ── Delete/reset ───────────────────────────────────────────────────────

    def _delete_all_conversations_v2(self, conn, user_id: str) -> int:
        cursor = conn.execute(
            "DELETE FROM conversation_threads_v2 WHERE user_id = ?", (user_id,)
        )
        cursor2 = conn.execute(
            "DELETE FROM conversation_messages_v2 WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount + cursor2.rowcount

    def reset(self, user_id: str, scopes: Optional[List[str]] = None) -> Dict[str, Any]:
        from repositories.cloud_authority_store import CloudAuthorityStore
        from repositories.user_preferences_store import UserPreferencesStore

        scopes = set(scopes or [])
        if "factory" in scopes:
            scopes = {"conversations", "preferences", "cloud_authority", "onboarding"}

        deleted: List[str] = []
        retained: List[str] = []

        if "conversations" in scopes:
            with self._database.transaction(immediate=True) as conn:
                v1 = conn.execute(
                    "DELETE FROM conversation_threads WHERE user_id = ?", (user_id,)
                ).rowcount
                self._delete_all_conversations_v2(conn, user_id)
            deleted.append("conversations")
            if v1:
                logger.info("Deleted %d v1 conversations for user %s", v1, user_id)
        else:
            retained.append("conversations")

        if "preferences" in scopes:
            UserPreferencesStore(self._database).reset(user_id)
            deleted.append("user_preferences")
        else:
            retained.append("user_preferences")

        if "cloud_authority" in scopes:
            CloudAuthorityStore(self._database).delete_all_authority_data(user_id)
            deleted.append("cloud_authority")
        else:
            retained.append("cloud_authority")

        if "onboarding" in scopes:
            with self._database.transaction(immediate=True) as conn:
                conn.execute(
                    """UPDATE user_preferences_state
                       SET onboarding_completed = 0,
                           onboarding_version = '',
                           active_execution_state = 'setup_required',
                           active_execution_reason = 'Onboarding reset by user.',
                           updated_at = ?
                       WHERE user_id = ?""",
                    (_utc_now(), user_id),
                )
            deleted.append("onboarding")
        else:
            retained.append("onboarding")

        # Audit, logs and backups remain by design.
        retained.extend(["audit_records", "diagnostic_logs", "backups", "provider_side_data"])

        return {
            "user_id": user_id,
            "requested_scopes": sorted(scopes),
            "deleted": sorted(set(deleted)),
            "retained": sorted(set(retained)),
            "retention_reasons": {
                "audit_records": "security and governance evidence retained by policy",
                "diagnostic_logs": "application logs are outside Alpha user-deletion scope",
                "backups": "historical database backups may retain records",
                "provider_side_data": "Sentinel cannot guarantee deletion from external providers",
            },
        }
