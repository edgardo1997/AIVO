import pytest
from pydantic import ValidationError

from sentinel.v2_operational_observability import (
    ObservationBatchV1,
    ObservationResultV1,
)


def values():
    return {
        "correlation_hash": "d" * 64,
        "legacy_decisions": 1,
        "v2_decisions": 1,
        "canary_active": False,
        "rollback_events": 0,
        "total_events": 1,
        "errors": 0,
        "divergences": 0,
        "critical_divergences": 0,
        "lost_events": 0,
        "average_latency_ms": 1,
        "stable": True,
        "state_corrupted": False,
        "health_failed": False,
        "trial_expired": False,
        "canary_duration_seconds": 0,
    }


def test_observation_rejects_sensitive_fields() -> None:
    for field in (
        "prompt",
        "user",
        "command",
        "path",
        "arguments",
        "payload",
        "secret",
    ):
        with pytest.raises(ValidationError):
            ObservationBatchV1(**values(), **{field: "sensitive"})


def test_result_has_no_authority_or_action_capability() -> None:
    fields = set(ObservationResultV1.model_fields)
    assert ObservationResultV1.model_fields["authority"].default is False
    assert ObservationResultV1.model_fields["execution_requested"].default is False
    assert "action_requested" not in ObservationResultV1.model_fields
    assert fields.isdisjoint({"tool", "grant", "command", "arguments", "payload", "runtime"})
