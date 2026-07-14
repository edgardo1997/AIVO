from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from .operational_memory import PendingActionRecord


@dataclass
class ConfirmationGrant:
    action_id: str
    tool_id: str
    params: Dict[str, Any]
    context: Dict[str, Any]
    user_id: str


class ConfirmationBroker:
    """Persistent, identity-bound, single-use confirmation broker."""

    def __init__(self, memory, ttl_seconds: int = 600):
        self._memory = memory
        self._ttl_seconds = ttl_seconds

    def request(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any], reason: str) -> str:
        identity = context.get("identity") or {}
        user_id = identity.get("user_id")
        if not user_id:
            raise ValueError("Authenticated user is required for confirmation")
        action_id = uuid.uuid4().hex
        safe_context = {"identity": identity, "execution_id": context.get("execution_id")}
        self._memory.store_pending_action(PendingActionRecord(
            action_id=action_id, tool_id=tool_id,
            params={"kind": "tool_confirmation", "tool_id": tool_id, "params": dict(params),
                    "context": safe_context, "user_id": user_id},
            reason=reason, created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ttl_seconds=self._ttl_seconds,
        ))
        return action_id

    def consume(self, action_id: str, user_id: str, approved: bool) -> Optional[ConfirmationGrant]:
        record = self._memory.get_pending_action(action_id)
        if record is None or record.params.get("kind") != "tool_confirmation":
            return None
        if record.params.get("user_id") != user_id:
            raise PermissionError("Confirmation belongs to a different user")
        created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > record.ttl_seconds:
            self._memory.remove_pending_action(action_id)
            return None
        self._memory.remove_pending_action(action_id)
        if not approved:
            return None
        return ConfirmationGrant(action_id, record.params["tool_id"], dict(record.params["params"]),
                                 dict(record.params.get("context") or {}), user_id)
