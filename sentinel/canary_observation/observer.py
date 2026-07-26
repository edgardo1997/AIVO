"""Passive EventBus observer forwarding deep copies to Runtime Canary."""

import asyncio
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable

from sentinel.core import event_types
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.runtime_canary import RuntimeCanaryInput, RuntimeCanaryPipeline

from .aggregation import CanaryMetricsAggregator
from .control import canary_observation_enabled
from .diagnostics import CanaryObservationDiagnostic
from .health import CanaryHealth, CanaryHealthReport


SnapshotProvider = Callable[[SentinelEvent], RuntimeCanaryInput | None]


_EVENT_MAP = {
    event_types.INTENT_DETECTED: ("intent_received", "intent"),
    event_types.PLANNER_COMPLETED: ("plan_created", "planner"),
    event_types.POLICY_VALIDATED: ("policy_evaluated", "policy"),
    event_types.TOOL_SELECTED: ("execution_requested", "execution"),
    event_types.EXECUTION_COMPLETED: (
        "execution_completed",
        "execution",
    ),
}


class CanaryObserver:
    """Observe events asynchronously; failures never propagate to runtime."""

    def __init__(
        self,
        *,
        pipeline: RuntimeCanaryPipeline,
        aggregator: CanaryMetricsAggregator,
        snapshot_provider: SnapshotProvider,
        enabled: bool | None = None,
        health: CanaryHealth | None = None,
    ) -> None:
        self._enabled = canary_observation_enabled() if enabled is None else enabled
        self._pipeline = pipeline
        self._aggregator = aggregator
        self._snapshot_provider = snapshot_provider
        self._health = health or CanaryHealth()
        self._bus: EventBus | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def attach(self, bus: EventBus) -> bool:
        if not self._enabled:
            return False
        if self._bus is bus:
            return True
        if self._bus is not None:
            self.detach()
        bus.subscribe("*", self._receive)
        self._bus = bus
        return True

    def detach(self) -> None:
        if self._bus is not None:
            self._bus.unsubscribe("*", self._receive)
            self._bus = None

    async def flush(self) -> None:
        tasks = tuple(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def health(self) -> CanaryHealthReport:
        return self._health.evaluate(
            enabled=self._enabled,
            aggregator=self._aggregator,
        )

    async def _receive(self, event: SentinelEvent) -> None:
        if not self._enabled:
            return
        copied = deepcopy(event)
        task = asyncio.create_task(self._process(copied))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process(self, event: SentinelEvent) -> None:
        mapped = _map_event(event)
        if mapped is None:
            self._aggregator.record_ignored(day=datetime.now(timezone.utc).date().isoformat())
            return
        event_name, component = mapped
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc)
        try:
            snapshot = self._snapshot_provider(deepcopy(event))
            if snapshot is None:
                raise ValueError("snapshot_unavailable")
            result = self._pipeline.observe(deepcopy(snapshot))
            latency_ms = (time.perf_counter() - started) * 1000
            diagnostic = CanaryObservationDiagnostic(
                observation_id=f"observation_{uuid.uuid4().hex}",
                timestamp=timestamp,
                event_type=event_name,
                component=component,
                status="OK",
                latency_ms=latency_ms,
                result_code=str(result.comparison_result.get("status", "OBSERVED")),
            )
            self._aggregator.record(diagnostic, result)
            self._health.record(failed=False, latency_ms=latency_ms)
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000
            diagnostic = CanaryObservationDiagnostic(
                observation_id=f"observation_{uuid.uuid4().hex}",
                timestamp=timestamp,
                event_type=event_name,
                component=component,
                status="ERROR",
                latency_ms=latency_ms,
                result_code="CANARY_FAILURE",
            )
            self._aggregator.record_failure(diagnostic)
            self._health.record(failed=True, latency_ms=latency_ms)


def _map_event(event: SentinelEvent) -> tuple[str, str] | None:
    if event.event_type == event_types.POLICY_VALIDATED and _requires_authorization(event):
        return "authorization_requested", "authorization"
    if event.event_type == event_types.TOOL_FINISHED and event.tool == "app.discovery":
        return "discovery_completed", "discovery"
    return _EVENT_MAP.get(event.event_type)


def _requires_authorization(event: SentinelEvent) -> bool:
    values = (
        event.status,
        str((event.details or {}).get("effect", "")),
        str((event.details or {}).get("decision", "")),
    )
    return any(value.upper() in {"REQUIRE_CONFIRM", "REQUIRE_CONSENT"} for value in values)
