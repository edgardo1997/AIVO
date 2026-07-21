import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .operational_memory import PendingActionRecord


_SECRET_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "api-key", "x-api-key", "auth_token",
    "access_key", "secret_key", "private_key",
})


@dataclass
class ConfirmationGrant:
    action_id: str
    tool_id: str
    params: Dict[str, Any]
    context: Dict[str, Any]
    user_id: str
    risk_level: str = "unknown"
    plan_id: str = ""


class ConfirmationBroker:
    """Persistent, identity-bound, single-use confirmation broker.

    Binds each approval to: user, tool, params, risk, plan, expiration,
    single-use identifier. Rejects expired, replayed, or tampered approvals.
    """

    def __init__(self, memory, ttl_seconds: int = 600):
        self._memory = memory
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _hash(obj: Any) -> str:
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _redact_context(context: Dict[str, Any]) -> Dict[str, Any]:
        safe = {}
        for key, value in context.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in _SECRET_KEYS):
                safe[key] = "<REDACTED>"
            elif isinstance(value, dict):
                safe[key] = ConfirmationBroker._redact_context(value)
            elif isinstance(value, str):
                safe[key] = ConfirmationBroker._redact(value)
            else:
                safe[key] = value
        return safe

    @staticmethod
    def _redact(value: str) -> str:
        result = str(value)
        for pattern in _SECRET_KEYS:
            marker_lower = pattern.replace("_", "").replace("-", "")
            result_lower = result.lower().replace("_", "").replace("-", "")
            if marker_lower in result_lower:
                return "<REDACTED>"
        return result

    def request(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        reason: str,
        risk_level: str = "unknown",
        plan_id: str = "",
    ) -> str:
        identity = context.get("identity") or {}
        user_id = identity.get("user_id")
        if not user_id:
            raise ValueError("Authenticated user is required for confirmation")
        action_id = uuid.uuid4().hex

        params_redacted = self._redact_context({"p": params}).get("p", params)
        params_hash = self._hash(params_redacted)

        safe_context = {
            "identity": {"user_id": user_id, "role": identity.get("role")},
            "execution_id": context.get("execution_id"),
        }
        identity_hash = self._hash(user_id)

        self._memory.store_pending_action(
            PendingActionRecord(
                action_id=action_id,
                tool_id=tool_id,
                params={
                    "kind": "tool_confirmation",
                    "tool_id": tool_id,
                    "params": dict(params_redacted),
                    "context": safe_context,
                    "user_id": user_id,
                },
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ttl_seconds=self._ttl_seconds,
                risk_level=risk_level,
                plan_id=plan_id,
                params_hash=params_hash,
                identity_hash=identity_hash,
                redacted=True,
            )
        )
        return action_id

    def consume(self, action_id: str, user_id: str, approved: bool) -> Optional[ConfirmationGrant]:
        record = self._memory.get_pending_action(action_id)
        if record is None or record.params.get("kind") != "tool_confirmation":
            return None

        if approved:
            stored_params = dict(record.params["params"])
            stored_hash = self._hash(stored_params)
            if record.params_hash and stored_hash != record.params_hash:
                raise PermissionError("Params hash mismatch — approval tampered with")
            if record.identity_hash:
                current_identity_hash = self._hash(user_id)
                if record.identity_hash != current_identity_hash:
                    raise PermissionError("Identity hash mismatch — replay detected")

        if record.params.get("user_id") != user_id:
            raise PermissionError("Confirmation belongs to a different user")

        created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > record.ttl_seconds:
            self._memory.remove_pending_action(action_id)
            return None

        self._memory.remove_pending_action(action_id)
        if not approved:
            return None

        return ConfirmationGrant(
            action_id=action_id,
            tool_id=record.params["tool_id"],
            params=dict(record.params["params"]),
            context=dict(record.params.get("context") or {}),
            user_id=user_id,
            risk_level=record.risk_level,
            plan_id=record.plan_id,
        )

    def peek(self, action_id: str) -> Optional[Dict[str, Any]]:
        record = self._memory.get_pending_action(action_id)
        if record is None:
            return None
        return {
            "action_id": record.action_id,
            "tool_id": record.tool_id,
            "reason": record.reason,
            "risk_level": record.risk_level,
            "plan_id": record.plan_id,
            "created_at": record.created_at,
            "ttl_seconds": record.ttl_seconds,
            "redacted": record.redacted,
        }
