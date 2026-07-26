from types import SimpleNamespace

import pytest

from sentinel.contract_adapters import adapt_health, adapt_readiness
from sentinel.contracts import (
    HealthStateV1,
    HealthStatusV1,
    ReadinessStateV1,
    ReadinessStateValueV1,
)


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("HEALTHY", HealthStateV1.HEALTHY),
        ("OBSERVING", HealthStateV1.OBSERVING),
        ("UNSTABLE", HealthStateV1.DEGRADED),
        ("CRITICAL", HealthStateV1.CRITICAL),
    ],
)
def test_health_vocabulary_conversion(legacy, expected):
    result = adapt_health(
        SimpleNamespace(state=legacy),
        correlation_id="correlation-1",
    )

    assert isinstance(result.contract, HealthStatusV1)
    assert result.contract.state is expected


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("BLOCKED", ReadinessStateValueV1.BLOCKED),
        ("NOT_READY", ReadinessStateValueV1.INSUFFICIENT_EVIDENCE),
        ("READY_FOR_REVIEW", ReadinessStateValueV1.READY_FOR_HUMAN_REVIEW),
        ("APPROVED_FOR_MIGRATION", ReadinessStateValueV1.HIGH_CONFIDENCE_REVIEW),
    ],
)
def test_readiness_vocabulary_conversion(legacy, expected):
    result = adapt_readiness(
        SimpleNamespace(status=legacy),
        correlation_id="correlation-1",
    )

    assert isinstance(result.contract, ReadinessStateV1)
    assert result.contract.state is expected
    assert result.contract.authority is False
    assert result.contract.execution_requested is False


def test_unknown_vocabularies_fail_closed():
    with pytest.raises(ValueError):
        adapt_health("ACTIVE", correlation_id="correlation-1")
    with pytest.raises(ValueError):
        adapt_readiness("CUTOVER_READY", correlation_id="correlation-1")
