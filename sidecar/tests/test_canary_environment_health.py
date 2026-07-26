import pytest

from sentinel.canary_environment import (
    CanaryEnvironmentMetrics,
    CanaryHealthEvaluator,
    CanaryHealthStatus,
    CanarySessionV1,
)


def snapshot(*, errors=0, latency=10, failed=0):
    metrics = CanaryEnvironmentMetrics()
    total = max(errors, failed, 1)
    for index in range(total):
        metrics.record(
            latency_ms=latency,
            matched=True,
            conversion_succeeded=index >= failed,
            error=index < errors,
        )
    return metrics.snapshot()


@pytest.mark.parametrize(
    ("expected", "kwargs"),
    [
        (CanaryHealthStatus.HEALTHY, {}),
        (CanaryHealthStatus.WARNING, {"memory_mb": 110}),
        (CanaryHealthStatus.DEGRADED, {"critical_divergences": 1}),
        (CanaryHealthStatus.CRITICAL, {"consecutive_errors": 10}),
    ],
)
def test_health_classification(expected, kwargs) -> None:
    status, reasons = CanaryHealthEvaluator().evaluate(snapshot(), **kwargs)
    assert status is expected
    assert bool(reasons) is (expected is not CanaryHealthStatus.HEALTHY)


def test_memory_limit() -> None:
    session = CanarySessionV1.create(
        environment_id="canary_1",
        correlation_id="corr_1",
        memory_limit_mb=64,
        timeout_seconds=30,
    )
    assert session.within_memory_limit(64)
    assert not session.within_memory_limit(65)
    with pytest.raises(ValueError):
        CanarySessionV1.create(
            environment_id="canary_1",
            correlation_id="corr_1",
            memory_limit_mb=0,
        )


def test_metrics_are_sanitized_aggregates() -> None:
    metrics = CanaryEnvironmentMetrics()
    metrics.record(
        latency_ms=25,
        matched=False,
        conversion_succeeded=False,
        error=True,
    )
    result = metrics.snapshot()
    assert result.processed_events == 1
    assert result.divergences == 1
    assert result.failed_conversions == 1
    assert not hasattr(metrics, "events")
    assert not hasattr(metrics, "payloads")
