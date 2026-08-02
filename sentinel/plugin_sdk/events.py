"""Product-level event system for plugins.

Plugins react to what happens on the machine instead of polling. The SDK
defines a small, curated set of event types; the manager forwards these to
the handlers registered by active plugins.
"""

from __future__ import annotations

import time as time_mod
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .manifest import EVENT_TYPES

EventHandler = Callable[[Dict[str, Any]], Any]


@dataclass
class PluginEvent:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=lambda: time_mod.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "payload": dict(self.payload),
            "source": self.source,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
        }


class UnknownEventError(ValueError):
    pass


class PluginEventBus:
    """Lightweight pub/sub bus.

    Handlers are plain callables. The plugin manager subscribes one dispatch
    handler per subscribed event type so this bus stays decoupled from how
    plugins are loaded or sandboxed.
    """

    def __init__(self, clock=None) -> None:
        self._clock = clock or time_mod.time
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._history: List[Dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in EVENT_TYPES:
            raise UnknownEventError(f"unknown plugin event type: {event_type}")
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def handlers_for(self, event_type: str) -> List[EventHandler]:
        return list(self._subscribers.get(event_type, []))

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None, source: str = "") -> List[Dict[str, Any]]:
        if event_type not in EVENT_TYPES:
            raise UnknownEventError(f"unknown plugin event type: {event_type}")
        event = PluginEvent(type=event_type, payload=payload or {}, source=source, timestamp=self._clock())
        results: List[Dict[str, Any]] = []
        for handler in self.handlers_for(event_type):
            try:
                result = handler(event.to_dict())
                results.append({"handler": getattr(handler, "__name__", "anonymous"), "ok": True, "result": result})
            except Exception as exc:
                results.append({"handler": getattr(handler, "__name__", "anonymous"), "ok": False, "error": str(exc)})
        self._history.append(event.to_dict())
        self._history = self._history[-200:]
        return results

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._history[-limit:])

    def subscriber_count(self, event_type: str) -> int:
        return len(self._subscribers.get(event_type, []))
