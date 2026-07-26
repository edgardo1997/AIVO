from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from sentinel.contracts import (
    AuthorizationScopeV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.tool_gateway import (
    ToolParameterValueV1,
    VerifiedToolCatalog,
    builtin_verified_catalog,
    canonical_parameters_hash,
)
from sentinel.tool_gateway.catalog import sign_catalog
from test_tool_gateway_v2 import _gateway, _inputs


def _evaluate(gateway, request, grant, consent, evidence, policy):
    return gateway.evaluate(
        request=request,
        grant=grant,
        consent=consent,
        evidence=evidence,
        policy=policy,
        now=request.timestamp,
    )


def test_builtin_catalog_is_signed_and_pinned():
    catalog = builtin_verified_catalog()
    specification = catalog.resolve("sentinel.file.metadata", "1.0.0")
    assert specification is not None
    assert specification.specification_hash
    assert catalog.catalog.catalog_hash
    assert catalog.catalog.authority is False
    assert catalog.catalog.execution_requested is False


def test_catalog_tampering_breaks_ed25519_verification():
    trusted = builtin_verified_catalog()
    tampered = trusted.catalog.model_copy(update={"catalog_hash": "0" * 64})
    with pytest.raises(ValueError, match="catalog hash mismatch"):
        VerifiedToolCatalog(tampered, trusted_public_key=b"\0" * 32)

    attacker = Ed25519PrivateKey.generate()
    resigned = sign_catalog(
        catalog_id=trusted.catalog.catalog_id,
        version=trusted.catalog.version,
        issuer_id=trusted.catalog.issuer_id,
        entries=trusted.catalog.entries,
        private_key=attacker,
        created_at=trusted.catalog.created_at,
    )
    with pytest.raises(ValueError, match="catalog signature invalid"):
        VerifiedToolCatalog(
            resigned,
            trusted_public_key=bytes.fromhex("fe2ccda4a2b7651afbe493cef48b32b4baa863a329538e055a051399e42e490d"),
        )


def test_tool_outside_catalog_is_blocked(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    unknown = request.model_copy(update={"tool_id": "sentinel.unknown.tool"})
    try:
        result = _evaluate(
            gateway,
            unknown,
            grant,
            consent,
            evidence,
            policy,
        )
        assert result.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        assert "TOOL_NOT_IN_CATALOG" in result.reason_codes
    finally:
        telemetry.close()


def test_free_command_parameter_is_blocked(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    unsafe = request.model_copy(
        update={
            "parameters": (ToolParameterValueV1(name="command", value="whoami"),),
            "params_hash": canonical_parameters_hash({}),
        }
    )
    try:
        result = _evaluate(
            gateway,
            unsafe,
            grant,
            consent,
            evidence,
            policy,
        )
        assert result.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
        assert "UNSAFE_PARAMETER" in result.reason_codes
    finally:
        telemetry.close()


def test_schema_scope_and_parameter_hash_are_enforced(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    malformed = request.model_copy(
        update={
            "parameters": (ToolParameterValueV1(name="include_system", value=True),),
            "requested_scope": AuthorizationScopeV1.SIMULATION_ONLY,
            "params_hash": canonical_parameters_hash({"include_system": True}),
        }
    )
    try:
        result = _evaluate(
            gateway,
            malformed,
            grant,
            consent,
            evidence,
            policy,
        )
        assert "TOOL_SCOPE_MISMATCH" in result.reason_codes
        assert "UNKNOWN_PARAMETER" in result.reason_codes
        assert "GRANT_BINDING_MISMATCH" in result.reason_codes
    finally:
        telemetry.close()


def test_grant_plan_step_tool_and_parameters_are_hash_bound(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    mutations = (
        ({"plan_id": "plan:other"}, "PLAN_MISMATCH"),
        ({"step_id": "step:other"}, "STEP_NOT_AUTHORIZED"),
        ({"tool_id": "sentinel.system.information"}, "GRANT_BINDING_MISMATCH"),
        ({"params_hash": "f" * 64}, "GRANT_BINDING_MISMATCH"),
    )
    try:
        for index, (update, expected) in enumerate(mutations):
            changed = request.model_copy(update={"request_id": f"tool-request:binding:{index}", **update})
            result = _evaluate(
                gateway,
                changed,
                grant,
                consent,
                evidence,
                policy,
            )
            assert expected in result.reason_codes
            assert result.decision.decision is (ToolGatewayDecisionValueV1.TOOL_BLOCKED)
    finally:
        telemetry.close()


def test_each_request_has_complete_audit_and_telemetry(tmp_path):
    request, grant, consent, evidence, policy, verifier = _inputs(tmp_path)
    gateway, telemetry = _gateway(tmp_path, verifier)
    try:
        result = _evaluate(
            gateway,
            request,
            grant,
            consent,
            evidence,
            policy,
        )
        assert result.audit_event.correlation_id == request.correlation_id
        assert result.audit_event.evidence_hash == request.evidence_hash
        assert result.operational_event.issuer_id == request.issuer_id
        assert result.telemetry_snapshot is not None
        assert telemetry.timeline.latest() == (result.operational_event,)
    finally:
        telemetry.close()
