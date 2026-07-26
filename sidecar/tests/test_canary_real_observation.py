"""Fase 21.5 tests for passive real-event canary observation."""

import ast
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentinel.canary_observation import (
    CANARY_OBSERVATION_ENABLED,
    CanaryAggregateStorage,
    CanaryHealth,
    CanaryHealthStatus,
    CanaryMetricsAggregator,
    CanaryObservationDiagnostic,
    CanaryObserver,
    canary_observation_enabled,
)
from sentinel.core import event_types
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.runtime_canary import RuntimeCanaryInput, RuntimeCanaryResult


class _Pipeline:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.snapshots = []

    def observe(self, snapshot):
        if self.fail:
            raise RuntimeError("isolated canary failure")
        self.snapshots.append(snapshot)
        snapshot.discovery_request["name"] = "mutated-copy"
        return _result()


def _result(
    *,
    latency_ms: float = 5.0,
    difference: bool = False,
) -> RuntimeCanaryResult:
    return RuntimeCanaryResult(
        runtime_id="sanitized",
        timestamp=datetime.now(timezone.utc),
        legacy_summary={"observed": True},
        planner_result={"status": "SUCCESS"},
        discovery_result={"status": "RESOLVED"},
        policy_result={"status": "EVALUATED"},
        authorization_result={"status": "SIMULATED", "authority": False},
        comparison_result={
            "status": "DIVERGENCE" if difference else "MATCH",
            "planner_match": True,
            "discovery_match": not difference,
            "policy_match": True,
            "authorization_match": True,
            "differences": (("provider_difference",) if difference else ()),
        },
        warnings=(),
        schema_gaps=(),
        validation_errors=(),
        execution_time_ms=latency_ms,
    )


def _snapshot() -> RuntimeCanaryInput:
    return RuntimeCanaryInput(
        intent={"prompt": "secret prompt"},
        plan={"command": "secret command"},
        application={"path": r"C:\private\application.exe"},
        policy={"secret": "token"},
        identity=None,
        policy_context=None,
        discovery_request={"action": "lookup", "name": "Notepad"},
        intent_id="private-intent",
        plan_id="private-plan",
    )


def _event(
    event_type: str = event_types.INTENT_DETECTED,
    *,
    tool: str | None = None,
    status: str = "completed",
    details=None,
) -> SentinelEvent:
    return SentinelEvent.new(
        event_type=event_type,
        session_id="private-session",
        request_id="private-request",
        component="private-component",
        status=status,
        tool=tool,
        details=details or {"prompt": "secret prompt"},
    )


def _observer(
    tmp_path,
    *,
    enabled: bool,
    pipeline=None,
    max_recent: int = 8,
):
    storage = CanaryAggregateStorage(tmp_path / "canary-metrics.json")
    aggregator = CanaryMetricsAggregator(
        storage,
        max_recent=max_recent,
    )
    snapshot = _snapshot()
    observer = CanaryObserver(
        pipeline=pipeline or _Pipeline(),
        aggregator=aggregator,
        snapshot_provider=lambda _event: snapshot,
        enabled=enabled,
    )
    return observer, aggregator, storage, snapshot


@pytest.mark.asyncio
async def test_observation_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CANARY_OBSERVATION_ENABLED", raising=False)
    assert CANARY_OBSERVATION_ENABLED is False
    assert canary_observation_enabled() is False
    observer, aggregator, _storage, _snapshot_value = _observer(
        tmp_path,
        enabled=False,
    )
    bus = EventBus()
    assert observer.attach(bus) is False
    await bus.emit(_event())
    await observer.flush()
    assert aggregator.recent_count == 0
    assert observer.health().status is CanaryHealthStatus.OBSERVING


@pytest.mark.asyncio
async def test_real_event_capture(tmp_path):
    observer, aggregator, _storage, _snapshot_value = _observer(
        tmp_path,
        enabled=True,
    )
    bus = EventBus()
    assert observer.attach(bus) is True
    await bus.emit(_event())
    await observer.flush()
    diagnostic = aggregator.recent()[0]
    assert diagnostic.event_type == "intent_received"
    assert diagnostic.component == "intent"
    assert diagnostic.status == "OK"
    assert diagnostic.observation_id.startswith("observation_")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (_event(event_types.INTENT_DETECTED), "intent_received"),
        (_event(event_types.PLANNER_COMPLETED), "plan_created"),
        (_event(event_types.POLICY_VALIDATED), "policy_evaluated"),
        (
            _event(
                event_types.POLICY_VALIDATED,
                status="REQUIRE_CONFIRM",
            ),
            "authorization_requested",
        ),
        (
            _event(
                event_types.TOOL_FINISHED,
                tool="app.discovery",
            ),
            "discovery_completed",
        ),
        (_event(event_types.TOOL_SELECTED), "execution_requested"),
        (
            _event(event_types.EXECUTION_COMPLETED),
            "execution_completed",
        ),
    ],
)
async def test_required_runtime_event_mapping(tmp_path, event, expected):
    observer, aggregator, _storage, _snapshot_value = _observer(
        tmp_path,
        enabled=True,
    )
    bus = EventBus()
    observer.attach(bus)
    await bus.emit(event)
    await observer.flush()
    assert aggregator.recent()[0].event_type == expected


@pytest.mark.asyncio
async def test_event_redaction(tmp_path):
    observer, _aggregator, storage, _snapshot_value = _observer(
        tmp_path,
        enabled=True,
    )
    bus = EventBus()
    observer.attach(bus)
    await bus.emit(_event())
    await observer.flush()
    serialized = (tmp_path / "canary-metrics.json").read_text(encoding="utf-8")
    forbidden = (
        "private-session",
        "private-request",
        "private-component",
        "secret prompt",
        "secret command",
        r"C:\private\application.exe",
        "Notepad",
    )
    assert all(value not in serialized for value in forbidden)
    assert storage.daily(datetime.now(timezone.utc).date().isoformat())


def test_metrics_persistence(tmp_path):
    path = tmp_path / "metrics.json"
    storage = CanaryAggregateStorage(path)
    storage.update(
        "2026-07-24",
        {
            "events_total": 2,
            "planner_matches": 2,
            "planner_total": 2,
            "latency_total_ms": 30.0,
            "maximum_latency_ms": 20.0,
        },
    )
    restored = CanaryAggregateStorage(path).daily("2026-07-24")
    assert restored["events_total"] == 2
    assert restored["planner_match"] == 100.0
    assert restored["average_latency_ms"] == 15.0


def test_metrics_aggregation(tmp_path):
    storage = CanaryAggregateStorage(tmp_path / "metrics.json")
    aggregator = CanaryMetricsAggregator(storage)
    diagnostic = _diagnostic(latency_ms=12.0)
    aggregator.record(diagnostic, _result(difference=True))
    daily = storage.daily("2026-07-24")
    assert daily["events_total"] == 1
    assert daily["differences"] == 1
    assert daily["policy_match"] == 100.0
    assert daily["authorization_match"] == 100.0


@pytest.mark.asyncio
async def test_runtime_unchanged(tmp_path):
    pipeline = _Pipeline()
    observer, _aggregator, _storage, snapshot = _observer(
        tmp_path,
        enabled=True,
        pipeline=pipeline,
    )
    before = deepcopy(snapshot)
    bus = EventBus()
    observer.attach(bus)
    event = _event()
    event_before = deepcopy(event)
    await bus.emit(event)
    await observer.flush()
    assert snapshot == before
    assert event == event_before
    assert pipeline.snapshots[0] is not snapshot


@pytest.mark.asyncio
async def test_canary_failure_isolated(tmp_path):
    observer, aggregator, storage, _snapshot_value = _observer(
        tmp_path,
        enabled=True,
        pipeline=_Pipeline(fail=True),
    )
    bus = EventBus()
    observer.attach(bus)
    event = _event()
    await bus.emit(event)
    await observer.flush()
    assert event.status == "completed"
    diagnostic = aggregator.recent()[0]
    assert diagnostic.result_code == "CANARY_FAILURE"
    day = diagnostic.timestamp.astimezone(timezone.utc).date().isoformat()
    assert storage.daily(day)["errors"] == 1
    isolated_health = CanaryHealth(max_consecutive_errors=1)
    isolated_health.record(failed=True, latency_ms=1.0)
    assert (
        isolated_health.evaluate(
            enabled=True,
            aggregator=aggregator,
        ).status
        is CanaryHealthStatus.CRITICAL
    )


def test_storage_recovery(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not-json", encoding="utf-8")
    storage = CanaryAggregateStorage(path)
    assert storage.recovered_from_corruption is True
    assert storage.healthy is False
    storage.update("2026-07-24", {"events_total": 1})
    assert storage.healthy is True
    assert storage.daily("2026-07-24")["events_total"] == 1


def test_memory_boundaries(tmp_path):
    storage = CanaryAggregateStorage()
    aggregator = CanaryMetricsAggregator(storage, max_recent=2)
    for index in range(5):
        aggregator.record(
            _diagnostic(latency_ms=float(index)),
            _result(),
        )
    assert aggregator.recent_count == 2
    assert aggregator.events_dropped == 3
    health = CanaryHealth().evaluate(
        enabled=True,
        aggregator=aggregator,
    )
    assert health.status is CanaryHealthStatus.WARNING
    assert "event_loss" in health.reasons
    assert "memory_growth" in health.reasons


def test_latency_tracking(tmp_path):
    storage = CanaryAggregateStorage()
    aggregator = CanaryMetricsAggregator(storage)
    health = CanaryHealth(latency_warning_ms=10.0)
    health.record(failed=False, latency_ms=25.0)
    report = health.evaluate(enabled=True, aggregator=aggregator)
    assert report.status is CanaryHealthStatus.WARNING
    assert report.reasons == ("abnormal_latency",)


def test_no_execution_capability():
    forbidden = {"execute", "launch", "run", "popen", "system"}
    assert _call_violations(forbidden) == []


def test_ast_security_boundaries():
    forbidden_imports = {
        "sentinel.core.planner",
        "sentinel.core.decision_engine",
        "sentinel.core.policy_engine",
        "sentinel.core.tool_gateway",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
        "subprocess",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if any(module == item or module.startswith(f"{item}.") for item in forbidden_imports):
                    violations.append((path.name, node.lineno, module))
    assert violations == []
    assert _call_violations({"execute", "launch", "run", "popen", "system"}) == []


def _diagnostic(*, latency_ms: float) -> CanaryObservationDiagnostic:
    return CanaryObservationDiagnostic(
        observation_id="observation_test",
        timestamp=datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
        event_type="plan_created",
        component="planner",
        status="OK",
        latency_ms=latency_ms,
        result_code="MATCH",
    )


def _trees():
    for path in Path("sentinel/canary_observation").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


def _call_violations(names: set[str]):
    lowered = {name.casefold() for name in names}
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if called.casefold() in lowered:
                violations.append((path.name, node.lineno, called))
    return violations
