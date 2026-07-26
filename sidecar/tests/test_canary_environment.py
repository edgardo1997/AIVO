from datetime import datetime, timezone

from sentinel.canary_environment import (
    CANARY_ENVIRONMENT_ENABLED,
    CanaryEnvironmentControl,
    CanaryEnvironmentLifecycle,
    CanaryEnvironmentMetrics,
    CanaryEnvironmentReport,
    CanaryHealthStatus,
)


def test_disabled_by_default_does_not_initialize() -> None:
    assert CANARY_ENVIRONMENT_ENABLED is False
    lifecycle = CanaryEnvironmentLifecycle(CanaryEnvironmentControl(environ={}))
    assert lifecycle.create(runtime_v2_version="2.0") is None
    assert lifecycle.create_session(correlation_id="corr_1") is None


def test_isolated_creation_has_deterministic_identity() -> None:
    created_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
    first = CanaryEnvironmentLifecycle(CanaryEnvironmentControl(enabled=True)).create(
        runtime_v2_version="2.0", created_at=created_at
    )
    second = CanaryEnvironmentLifecycle(CanaryEnvironmentControl(enabled=True)).create(
        runtime_v2_version="2.0", created_at=created_at
    )
    assert first is not None and second is not None
    assert first.environment_id == second.environment_id
    assert first.authority is False
    assert first.created_at.utcoffset() is not None


def test_session_has_own_metrics_and_sanitized_identity() -> None:
    lifecycle = CanaryEnvironmentLifecycle(CanaryEnvironmentControl(enabled=True))
    lifecycle.create(runtime_v2_version="2.0")
    lifecycle.start()
    one = lifecycle.create_session(correlation_id="corr_one")
    two = lifecycle.create_session(correlation_id="corr_two")
    assert one is not None and two is not None
    one.metrics.record(
        latency_ms=10,
        matched=True,
        conversion_succeeded=True,
    )
    assert one.metrics.snapshot().processed_events == 1
    assert two.metrics.snapshot().processed_events == 0
    assert not hasattr(one, "prompt")
    assert not hasattr(one, "command")
    assert not hasattr(one, "user")


def test_aggregate_report() -> None:
    lifecycle = CanaryEnvironmentLifecycle(CanaryEnvironmentControl(enabled=True))
    environment = lifecycle.create(runtime_v2_version="2.0")
    assert environment is not None
    metrics = CanaryEnvironmentMetrics().snapshot()
    report = CanaryEnvironmentReport.build(
        environment,
        active_duration_seconds=15,
        health=CanaryHealthStatus.HEALTHY,
        metrics=metrics,
    )
    assert report.human_readable().startswith("SENTINEL CONTROLLED CANARY ENVIRONMENT REPORT")
