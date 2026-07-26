from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sentinel.contracts import EvidenceIntegrityStatusV1, HealthStateV1
from sentinel.operational_telemetry_hub import OperationalEventV1


def _values():
    return {
        "event_id": "event-1",
        "correlation_id": "correlation-1",
        "evidence_hash": "a" * 64,
        "issuer_id": "issuer.telemetry.v1",
        "timestamp": datetime.now(UTC),
        "event_type": "POLICY_DECISION",
        "health_state": HealthStateV1.HEALTHY,
        "decision_state": "MATCH",
        "integrity_status": EvidenceIntegrityStatusV1.VERIFIED,
    }


def test_operational_event_is_immutable_and_non_authoritative():
    event = OperationalEventV1(**_values())

    assert event.authority is False
    assert event.execution_requested is False
    assert len(event.canonical_hash()) == 64
    with pytest.raises(ValidationError):
        event.decision_state = "FAILED"


@pytest.mark.parametrize(
    "field",
    ["payload", "prompt", "command", "path", "secret", "tool_arguments"],
)
def test_operational_event_rejects_sensitive_or_unknown_fields(field):
    values = _values()
    values[field] = "not-allowed"
    with pytest.raises(ValidationError):
        OperationalEventV1(**values)


@pytest.mark.parametrize("field", ["authority", "execution_requested"])
def test_operational_event_rejects_authority_and_execution(field):
    values = _values()
    values[field] = True
    with pytest.raises(ValidationError):
        OperationalEventV1(**values)
