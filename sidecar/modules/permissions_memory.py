import logging
from collections.abc import MutableMapping
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentinel.core.operational_memory import MemoryBackend

log = logging.getLogger("sentinel.permissions_memory")


class PendingActionsDict(MutableMapping):
    """Dict-like adapter that bridges PENDING_ACTIONS global to OperationalMemory.

    Falls back to a local dict when no memory backend is available (early imports).
    Once OperationalMemory is wired via set_memory(), all access goes through
    InMemoryBackend's RLock for thread-safe centralized state.
    """

    def __init__(self) -> None:
        self._memory: Optional[MemoryBackend] = None
        self._fallback: Dict[str, Any] = {}

    def set_memory(self, memory: "MemoryBackend") -> None:
        self._memory = memory
        if self._fallback:
            from sentinel.core.operational_memory import PendingActionRecord
            from datetime import datetime, timezone

            for action_id, data in self._fallback.items():
                try:
                    rec = PendingActionRecord(
                        action_id=action_id,
                        tool_id=data.get("classification", "unknown"),
                        params=data,
                        reason="migrated",
                        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        ttl_seconds=600,
                    )
                    memory.store_pending_action(rec)
                except Exception as e:
                    log.warning("Failed to migrate pending action %s: %s", action_id, e)
            self._fallback.clear()

    def _get_from_memory(self, action_id: str) -> Any:
        rec = self._memory.get_pending_action(action_id)
        if rec is None:
            raise KeyError(action_id)
        return rec.params

    def __getitem__(self, action_id: str) -> Any:
        if self._memory:
            return self._get_from_memory(action_id)
        if action_id not in self._fallback:
            raise KeyError(action_id)
        return self._fallback[action_id]

    def __setitem__(self, action_id: str, value: Any) -> None:
        if self._memory:
            from sentinel.core.operational_memory import PendingActionRecord
            from datetime import datetime, timezone

            rec = PendingActionRecord(
                action_id=action_id,
                tool_id=value.get("classification", "unknown"),
                params=value,
                reason="pending_confirmation",
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ttl_seconds=600,
            )
            self._memory.store_pending_action(rec)
        else:
            self._fallback[action_id] = value

    def __delitem__(self, action_id: str) -> None:
        if self._memory:
            removed = self._memory.remove_pending_action(action_id)
            if removed is None:
                raise KeyError(action_id)
        else:
            if action_id not in self._fallback:
                raise KeyError(action_id)
            del self._fallback[action_id]

    def __len__(self) -> int:
        if self._memory:
            return len(self._memory.list_pending_actions())
        return len(self._fallback)

    def __iter__(self):
        if self._memory:
            for rec in self._memory.list_pending_actions():
                yield rec.action_id
        else:
            yield from self._fallback

    def pop(self, action_id: str, *args: Any) -> Any:
        if self._memory:
            rec = self._memory.remove_pending_action(action_id)
            if rec is None:
                if args:
                    return args[0]
                raise KeyError(action_id)
            return rec.params
        return self._fallback.pop(action_id, *args)

    def clear(self) -> None:
        if self._memory:
            for rec in self._memory.list_pending_actions():
                self._memory.remove_pending_action(rec.action_id)
        self._fallback.clear()


class EmergencyStopFlag:
    """List-like adapter that bridges EMERGENCY_STOP global to OperationalMemory.

    Provides EMERGENCY_STOP[0] read/write interface for backward compatibility.
    Delegates to InMemoryBackend.get_emergency_stop/set_emergency_stop when available.
    """

    def __init__(self) -> None:
        self._memory: Optional[MemoryBackend] = None
        self._fallback: bool = False

    def set_memory(self, memory: "MemoryBackend") -> None:
        self._memory = memory
        if self._fallback:
            memory.set_emergency_stop(self._fallback)
            self._fallback = False

    def __getitem__(self, index: int) -> bool:
        if index != 0:
            raise IndexError("EmergencyStopFlag only supports index 0")
        if self._memory:
            return self._memory.get_emergency_stop()
        return self._fallback

    def __setitem__(self, index: int, value: bool) -> None:
        if index != 0:
            raise IndexError("EmergencyStopFlag only supports index 0")
        if self._memory:
            self._memory.set_emergency_stop(value)
        else:
            self._fallback = value

    def __repr__(self) -> str:
        return f"[{self[0]!r}]"
