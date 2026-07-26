"""Characterization tests for passive shadow runtime validation."""

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentinel.contracts import (
    PolicyDecisionV2,
    PolicyDecisionValueV2,
    ShadowExecutionTraceV1,
)
from sentinel.core import event_types
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import (
    RuntimeEventCapture,
    RuntimeShadowAdapter,
    ShadowDecisionComparison,
    ShadowDecisionComparisonStatus,
    ShadowMetricsStore,
)


def _event(
    event_type: str,
    *,
    status: str = "completed",
    details=None,
) -> SentinelEvent:
    return SentinelEvent.new(
        event_type=event_type,
        session_id="user-edgar-secret-session",
        request_id="request-secret",
        component="legacy_runtime",
        status=status,
        tool="executor.launch",
        details=details,
    )


@pytest.mark.asyncio
async def test_runtime_event_capture():
    bus = EventBus()
    capture = RuntimeEventCapture(enabled=True)
    assert capture.attach(bus) is True

    for event in (
        _event(event_types.INTENT_DETECTED),
        _event(event_types.PLANNER_COMPLETED),
        _event(event_types.POLICY_VALIDATED),
        _event(
            event_types.POLICY_VALIDATED,
            status="REQUIRE_CONFIRM",
        ),
        _event(event_types.TOOL_STARTED),
        _event(event_types.EXECUTION_COMPLETED),
        _event(event_types.PIPELINE_FAILED, status="failed"),
    ):
        await bus.emit(event)

    assert [event.event_name for event in capture.events()] == [
        "intent_received",
        "plan_created",
        "policy_evaluated",
        "consent_requested",
        "tool_requested",
        "execution_completed",
        "execution_failed",
    ]


@pytest.mark.asyncio
async def test_shadow_trace_creation():
    bus = EventBus()
    capture = RuntimeEventCapture(enabled=True)
    capture.attach(bus)
    await bus.emit(_event(event_types.INTENT_DETECTED))

    trace = RuntimeShadowAdapter().convert_event(capture.events()[0])

    assert isinstance(trace, ShadowExecutionTraceV1)
    assert trace.schema_version == "1.0"
    assert trace.conversion_status == "WARNING"
    assert trace.warnings == ("schema_gap: legacy model unavailable",)


@pytest.mark.asyncio
async def test_shadow_never_changes_runtime():
    details = {
        "command": "powershell secret-command",
        "params": {"path": r"C:\Users\edgar\private.txt"},
    }
    event = _event(event_types.TOOL_STARTED, details=details)
    before = event.to_dict()
    bus = EventBus()
    capture = RuntimeEventCapture(enabled=True)
    capture.attach(bus)

    await bus.emit(event)
    RuntimeShadowAdapter().convert_event(capture.events()[0])

    assert event.to_dict() == before


def test_shadow_never_creates_grant():
    violations = []
    for path in Path("sentinel/shadow").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if called == "AuthorizationGrantV1":
                violations.append((path.name, node.lineno))
    assert violations == []


def test_policy_difference_detection():
    legacy = PolicyResult(
        effect=PolicyEffect.ALLOW,
        policy_id="application.launch",
        reason="Legacy allows",
        context={"risk": "medium"},
    )
    shadow = PolicyDecisionV2(
        schema_version="2.0",
        decision_id="decision_shadow",
        plan_id="plan_other",
        decision=PolicyDecisionValueV2.DENY,
        policy_ids=("application.launch",),
        reason="Shadow denies",
        risk_context={"risk": "medium"},
        timestamp=datetime.now(timezone.utc),
    )

    comparison = ShadowDecisionComparison.compare_policy(
        legacy=legacy,
        shadow=shadow,
        expected_plan_id="plan_expected",
    )

    assert comparison.status is ShadowDecisionComparisonStatus.DIVERGENCE
    assert "decision_changed:ALLOW->DENY" in comparison.differences
    assert "plan_different" in comparison.differences


def test_missing_context_warning():
    conversion = RuntimeShadowAdapter().convert_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Allowed",
        ),
        plan_id="plan_x",
    )
    assert conversion.warnings == ("missing_policy_context: identity and policy versions cannot be verified",)


@pytest.mark.asyncio
async def test_sensitive_data_redaction():
    secret_values = (
        "edgar",
        r"C:\Users\edgar\private.txt",
        "powershell secret-command",
        "--token=secret",
    )
    event = _event(
        event_types.TOOL_STARTED,
        details={
            "username": secret_values[0],
            "path": secret_values[1],
            "command": secret_values[2],
            "arguments": [secret_values[3]],
        },
    )
    bus = EventBus()
    capture = RuntimeEventCapture(enabled=True)
    capture.attach(bus)
    await bus.emit(event)

    trace = RuntimeShadowAdapter().convert_event(capture.events()[0])
    serialized = trace.model_dump_json()

    assert all(secret not in serialized for secret in secret_values)
    assert event.session_id not in serialized
    assert event.request_id not in serialized


@pytest.mark.asyncio
async def test_runtime_disabled_by_default():
    bus = EventBus()
    capture = RuntimeEventCapture()

    assert capture.enabled is False
    assert capture.attach(bus) is False
    await bus.emit(_event(event_types.INTENT_DETECTED))
    assert capture.events() == ()


def test_shadow_metrics_persist_aggregates_only():
    trace = ShadowExecutionTraceV1(
        schema_version="1.0",
        trace_id="trace_x",
        timestamp=datetime.now(timezone.utc),
        component="policy",
        legacy_type="PolicyResult",
        versioned_type="PolicyDecisionV2",
        conversion_status="WARNING",
        warnings=("missing_context", "missing_identity"),
        differences=("decision_changed:ALLOW->DENY", "schema_gap"),
        correlation_ids={"request_id": "hash_only"},
    )
    store = ShadowMetricsStore()
    store.record(trace)

    snapshot = store.snapshot()
    assert snapshot.conversion_success == 1
    assert snapshot.schema_gap == 1
    assert snapshot.decision_difference == 1
    assert snapshot.missing_identity == 1
    assert snapshot.missing_context == 1
    assert not hasattr(store, "traces")
