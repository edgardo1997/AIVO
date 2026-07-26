import hashlib
from datetime import datetime, timezone

import pytest

from sentinel.controlled_runtime_activation import (
    CanaryRoutingEvidenceV1,
    ControlledActivationControl,
    ControlledRuntimeActivation,
    ControlledRuntimeRouter,
    RuntimeSelection,
)


def request_for_bucket(minimum, maximum=99):
    for index in range(1000):
        request_id = f"request_{index}"
        bucket = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16) % 100
        if minimum <= bucket <= maximum:
            return request_id
    raise AssertionError("bucket not found")


def evidence(request_id, **updates):
    values = {
        "request_id": request_id,
        "gateway_eligibility": "V2_ELIGIBLE_CANARY",
        "readiness_approved": True,
        "safety_healthy": True,
        "rollback_available": True,
        "requested_scope": "application.lookup",
        "allowed_scopes": ("application.lookup",),
        "trial_started_at": datetime.now(timezone.utc),
        "maximum_trial_seconds": 3600,
        "critical_divergences": 0,
    }
    values.update(updates)
    return CanaryRoutingEvidenceV1(**values)


def router(percentage=5):
    activation = ControlledRuntimeActivation(
        ControlledActivationControl(
            enabled=True,
            canary_enabled=True,
            traffic_percentage=percentage,
        )
    )
    activation.start()
    return ControlledRuntimeRouter(activation=activation)


def test_deterministic_canary_and_legacy_routing() -> None:
    target = router()
    v2_evidence = evidence(request_for_bucket(95))
    legacy_evidence = evidence(request_for_bucket(0, 94))
    first = target.route(v2_evidence)
    second = target.route(v2_evidence)
    assert first is second
    assert first.selected_runtime is RuntimeSelection.V2_CANARY
    assert target.route(legacy_evidence).selected_runtime is RuntimeSelection.LEGACY


def test_v2_is_blocked_without_readiness() -> None:
    result = router().route(evidence(request_for_bucket(95), readiness_approved=False))
    assert result.selected_runtime is RuntimeSelection.LEGACY
    assert "READINESS_NOT_APPROVED" in result.reason_codes


def test_maximum_canary_percentage_is_five() -> None:
    with pytest.raises(ValueError):
        ControlledActivationControl(
            enabled=True,
            canary_enabled=True,
            traffic_percentage=6,
        )


def test_route_result_is_non_authoritative_and_non_executing() -> None:
    result = router().route(evidence(request_for_bucket(95)))
    assert result.authority is False
    assert result.execution_requested is False
