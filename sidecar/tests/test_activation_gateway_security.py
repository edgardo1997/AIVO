import pytest
from pydantic import ValidationError

from sentinel.activation_gateway import (
    ActivationGateway,
    ActivationGatewayControl,
    GatewayEvidenceV1,
    RuntimeContextV1,
    SelectedAuthority,
)


def evidence(context=None, **updates):
    values = {
        "request_id": "request_safe",
        "runtime_context": context
        or RuntimeContextV1(
            identity_valid=True,
            policy_context_valid=True,
            rollback_available=True,
        ),
        "readiness_status": "APPROVED_FOR_MIGRATION",
        "migration_status": "LIMITED_CANARY",
        "equivalence_status": "EQUIVALENT",
        "safety_status": "HEALTHY",
        "scope": ("safe.operation",),
        "risk_level": "LOW",
    }
    values.update(updates)
    return GatewayEvidenceV1(**values)


def gateway():
    return ActivationGateway(control=ActivationGatewayControl(enabled=True, v2_allowed=True))


def test_critical_divergence_blocks_selection() -> None:
    result = gateway().evaluate(evidence(equivalence_status="CRITICAL_DIVERGENCE"))
    assert result.selected_authority is SelectedAuthority.BLOCKED


@pytest.mark.parametrize(
    "context",
    [
        RuntimeContextV1(
            identity_valid=False,
            policy_context_valid=True,
            rollback_available=True,
        ),
        RuntimeContextV1(
            identity_valid=True,
            policy_context_valid=True,
            rollback_available=False,
        ),
    ],
)
def test_identity_or_rollback_failure_blocks(context) -> None:
    result = gateway().evaluate(evidence(context=context))
    assert result.selected_authority is SelectedAuthority.BLOCKED


def test_evidence_rejects_sensitive_or_executable_fields() -> None:
    base = evidence().model_dump()
    for field in (
        "prompt",
        "command",
        "arguments",
        "path",
        "payload",
        "tool",
        "process",
    ):
        with pytest.raises(ValidationError):
            GatewayEvidenceV1(**base, **{field: "sensitive"})


def test_result_is_immutable() -> None:
    result = gateway().evaluate(evidence())
    try:
        result.authority = True
    except Exception:
        pass
    assert result.authority is False
    assert result.execution_requested is False
