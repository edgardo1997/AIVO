from sentinel.activation_gateway import (
    ACTIVATION_GATEWAY_ENABLED,
    V2_ACTIVATION_ALLOWED,
    ActivationGateway,
    ActivationGatewayControl,
    GatewayEvidenceV1,
    RuntimeContextV1,
    SelectedAuthority,
)


def evidence(**updates):
    values = {
        "request_id": "request_1",
        "runtime_context": RuntimeContextV1(
            identity_valid=True,
            policy_context_valid=True,
            rollback_available=True,
        ),
        "readiness_status": "APPROVED_FOR_MIGRATION",
        "migration_status": "LIMITED_CANARY",
        "equivalence_status": "EQUIVALENT",
        "safety_status": "HEALTHY",
        "scope": ("application.lookup",),
        "risk_level": "LOW",
    }
    values.update(updates)
    return GatewayEvidenceV1(**values)


def test_gateway_disabled_by_default() -> None:
    assert ACTIVATION_GATEWAY_ENABLED is False
    assert V2_ACTIVATION_ALLOWED is False
    gateway = ActivationGateway(control=ActivationGatewayControl(environ={}))
    assert gateway.evaluate(evidence()) is None
    assert gateway.metrics.snapshot().total_evaluations == 0
    assert gateway.audit.snapshot() == ()


def test_legacy_is_selected_by_default_when_v2_not_allowed() -> None:
    gateway = ActivationGateway(control=ActivationGatewayControl(enabled=True, v2_allowed=False))
    result = gateway.evaluate(evidence())
    assert result.selected_authority is SelectedAuthority.LEGACY_ONLY
    assert result.authority is False
    assert result.execution_requested is False


def test_v2_canary_is_only_eligible_when_all_gates_pass() -> None:
    gateway = ActivationGateway(control=ActivationGatewayControl(enabled=True, v2_allowed=True))
    result = gateway.evaluate(evidence())
    assert result.selected_authority is SelectedAuthority.V2_ELIGIBLE_CANARY
    assert result.reason_codes == ("ALL_GATES_APPROVED",)
    assert result.authority is False
    assert result.execution_requested is False


def test_v2_shadow_eligibility() -> None:
    gateway = ActivationGateway(control=ActivationGatewayControl(enabled=True, v2_allowed=True))
    result = gateway.evaluate(evidence(migration_status="SHADOW_ONLY"))
    assert result.selected_authority is SelectedAuthority.V2_ELIGIBLE_SHADOW
