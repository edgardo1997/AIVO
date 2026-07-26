"""Optional, non-blocking capture of redacted legacy runtime events."""

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from sentinel.core import event_types
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent


_EVENT_MAP: Final = {
    event_types.INTENT_DETECTED: "intent_received",
    event_types.PLANNER_COMPLETED: "plan_created",
    event_types.POLICY_VALIDATED: "policy_evaluated",
    event_types.POLICY_DENIED: "policy_evaluated",
    event_types.TOOL_SELECTED: "tool_requested",
    event_types.TOOL_STARTED: "tool_requested",
    event_types.EXECUTION_COMPLETED: "execution_completed",
    event_types.PIPELINE_FAILED: "execution_failed",
}


def _correlation_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class CapturedRuntimeEvent:
    event_name: str
    source_event_type: str
    timestamp: datetime
    component: str
    status: str
    tool_id: str
    correlation_ids: dict[str, str]


class RuntimeEventCapture:
    """Attach explicitly and retain only bounded, redacted metadata."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        max_events: int = 256,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self.enabled = enabled
        self._events: deque[CapturedRuntimeEvent] = deque(maxlen=max_events)
        self._bus: EventBus | None = None

    def attach(self, event_bus: EventBus) -> bool:
        if not self.enabled:
            return False
        if self._bus is event_bus:
            return True
        if self._bus is not None:
            self.detach()
        event_bus.subscribe("*", self._capture)
        self._bus = event_bus
        return True

    def detach(self) -> None:
        if self._bus is not None:
            self._bus.unsubscribe("*", self._capture)
            self._bus = None

    def events(self) -> tuple[CapturedRuntimeEvent, ...]:
        return tuple(self._events)

    async def _capture(self, event: SentinelEvent) -> None:
        event_name = _EVENT_MAP.get(event.event_type)
        if event_name is None:
            return
        if event.event_type == event_types.POLICY_VALIDATED and _requires_consent(event):
            event_name = "consent_requested"
        captured = CapturedRuntimeEvent(
            event_name=event_name,
            source_event_type=event.event_type,
            timestamp=datetime.fromtimestamp(
                event.timestamp,
                tz=timezone.utc,
            ),
            component=event.component or "runtime",
            status=event.status or "unknown",
            tool_id=event.tool or "",
            correlation_ids={
                key: _correlation_hash(value)
                for key, value in (
                    ("event_id", event.event_id),
                    ("session_id", event.session_id),
                    ("request_id", event.request_id),
                )
                if value
            },
        )
        self._events.append(captured)


def _requires_consent(event: SentinelEvent) -> bool:
    values = (
        event.status,
        str((event.details or {}).get("effect", "")),
        str((event.details or {}).get("decision", "")),
    )
    return any(value.upper() in {"REQUIRE_CONFIRM", "REQUIRE_CONSENT"} for value in values)
