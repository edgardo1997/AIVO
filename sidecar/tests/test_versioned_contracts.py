"""Unit tests for the isolated versioned-contract transition layer."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationInstallStateV1,
    ApplicationLaunchTypeV1,
    ApplicationVerificationLevelV1,
    AuthorizationGrantV1,
    AuthorizedStepV1,
    ExecutionPlanV2,
    ExecutionStepV2,
    IntentV2,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
    ResolverEvidenceV1,
    ResolverVerificationStateV1,
)


def _round_trip(model):
    return type(model).model_validate_json(model.model_dump_json())


def _step(**overrides) -> ExecutionStepV2:
    values = {
        "schema_version": "2.0",
        "step_id": "step_discover",
        "tool_id": "app.discovery",
        "parameters": {
            "action": "lookup",
            "name": "Notepad",
            "sources": ["app_paths", "start_menu"],
        },
        "depends_on": (),
    }
    values.update(overrides)
    return ExecutionStepV2.model_validate(values)


def _plan(**overrides) -> ExecutionPlanV2:
    intent_id = overrides.pop("intent_id", "intent_notepad")
    steps = overrides.pop("steps", (_step(),))
    values = {
        "schema_version": "2.0",
        "plan_id": "plan_notepad",
        "intent_id": intent_id,
        "steps": steps,
        "params_hash": ExecutionPlanV2.calculate_params_hash(
            intent_id=intent_id,
            steps=steps,
        ),
    }
    values.update(overrides)
    return ExecutionPlanV2.model_validate(values)


def _grant(**overrides) -> AuthorizationGrantV1:
    created_at = overrides.pop(
        "created_at",
        datetime.now(timezone.utc),
    )
    step = AuthorizedStepV1(
        step_id="launch",
        tool_id="executor.launch",
        params_hash="b" * 64,
    )
    values = {
        "authorization_id": "authorization_notepad",
        "plan_id": "plan_notepad",
        "user_id": "user_local",
        "policy_decision_id": "decision_notepad",
        "issuer": "sentinel.policy-engine",
        "nonce": "nonce-notepad",
        "authorized_steps": (step,),
        "params_hash": "a" * 64,
        "expires_at": created_at + timedelta(minutes=5),
        "created_at": created_at,
    }
    values.update(overrides)
    return AuthorizationGrantV1.issue(**values)


def _descriptor(
    launch_type,
    launch_target,
    executable,
) -> ApplicationDescriptorV1:
    resolved_at = datetime.now(timezone.utc)
    values = {
        "application_id": f"app_{launch_type.value}",
        "display_name": "Application",
        "aliases": ("app",),
        "provider": "windows",
        "launch_type": launch_type,
        "launch_target": launch_target,
        "executable": executable,
        "confidence": 0.9,
        "resolver_id": "test.resolver",
        "resolved_at": resolved_at,
        "install_state": ApplicationInstallStateV1.INSTALLED,
        "verification_level": (ApplicationVerificationLevelV1.VERIFIED),
        "source_evidence": ({"source": "characterization"},),
    }
    resolver_evidence = (
        ResolverEvidenceV1(
            schema_version="1.0",
            resolver_id=values["resolver_id"],
            resolver_version="1.0.0",
            resolver_identity="test-resolver-identity",
            source_type="characterization",
            source_reference=launch_target,
            discovered_at=resolved_at,
            metadata_hash="c" * 64,
            confidence=0.9,
            verification_state=ResolverVerificationStateV1.VERIFIED,
            verification_method="test-attestation",
            verified_at=resolved_at,
        ),
    )
    values["resolver_evidence"] = resolver_evidence
    metadata_hash = ApplicationDescriptorV1.calculate_metadata_hash(**values)
    return ApplicationDescriptorV1(
        schema_version="1.0",
        evidence=values["source_evidence"],
        metadata_hash=metadata_hash,
        **values,
    )


def test_intent_v2_serialization_round_trip():
    intent = IntentV2(
        schema_version="2.0",
        intent_id="intent_notepad",
        action="execute",
        target="executor.launch",
        parameters={"application_name": "Notepad"},
        confidence=0.95,
        raw_input="Abrir Notepad",
    )

    assert _round_trip(intent) == intent
    assert intent.model_dump(mode="json")["raw_input"] == "Abrir Notepad"


def test_execution_plan_v2_round_trip_hash_and_deep_parameter_immutability():
    plan = _plan()

    restored = _round_trip(plan)

    assert restored == plan
    assert len(plan.params_hash) == 64
    with pytest.raises(TypeError, match="immutable"):
        plan.steps[0].parameters["name"] = "Calculator"
    with pytest.raises(TypeError):
        plan.steps[0].parameters["sources"][0] = "registry"


def test_execution_step_v2_complete_round_trip_without_loss():
    step = _step(
        description="Resolve application metadata",
        estimated_duration_ms=250,
        model_decision={
            "provider_id": "sentinel_local",
            "strategy": "deterministic",
        },
        estimated_impact="medium",
        is_reversible=True,
        rollback_tool_id="app.discovery.rollback",
        rollback_params={"discovery_id": "discovery_x"},
        recovery_policy={"max_retries": 1},
    )

    restored = ExecutionStepV2.model_validate_json(step.model_dump_json())

    assert restored == step
    assert restored.description == "Resolve application metadata"
    assert restored.estimated_duration_ms == 250
    assert restored.model_decision["strategy"] == "deterministic"
    assert restored.estimated_impact == "medium"
    assert restored.is_reversible is True
    assert restored.reversible is True
    assert restored.rollback_params == {"discovery_id": "discovery_x"}
    assert restored.rollback_parameters == restored.rollback_params
    assert restored.recovery_policy == {"max_retries": 1}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimated_duration_ms", -1),
        ("estimated_impact", "catastrophic"),
    ],
)
def test_execution_step_v2_rejects_invalid_operational_values(
    field,
    value,
):
    with pytest.raises(ValidationError):
        _step(**{field: value})


def test_execution_plan_v2_rejects_tampered_hash():
    with pytest.raises(ValidationError, match="params_hash does not match"):
        _plan(params_hash="0" * 64)


def test_policy_decision_v2_serialization_round_trip():
    decision = PolicyDecisionV2(
        schema_version="2.0",
        decision_id="decision_notepad",
        plan_id="plan_notepad",
        decision=PolicyDecisionValueV2.REQUIRE_CONSENT,
        policy_ids=("application.launch", "interactive.consent"),
        reason="Interactive launch requires user consent",
        risk_context={"level": "medium", "interactive": True},
        timestamp=datetime.now(timezone.utc),
    )

    restored = _round_trip(decision)

    assert restored == decision
    assert restored.decision is PolicyDecisionValueV2.REQUIRE_CONSENT


def test_authorization_grant_v1_serialization_round_trip():
    grant = _grant()

    assert _round_trip(grant) == grant


@pytest.mark.parametrize(
    ("launch_type", "launch_target", "executable"),
    [
        (ApplicationLaunchTypeV1.EXECUTABLE, r"C:\Windows\notepad.exe", r"C:\Windows\notepad.exe"),
        (ApplicationLaunchTypeV1.AUMID, "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App", None),
        (ApplicationLaunchTypeV1.STEAM_APP_ID, "1551360", None),
        (ApplicationLaunchTypeV1.EPIC_CATALOG_ITEM, "catalog-item-id", None),
        (ApplicationLaunchTypeV1.PROTOCOL_URI, "xbox://game/forza", None),
    ],
)
def test_application_descriptor_v1_supports_all_launch_types(
    launch_type,
    launch_target,
    executable,
):
    descriptor = _descriptor(
        launch_type,
        launch_target,
        executable,
    )

    assert _round_trip(descriptor) == descriptor
    assert descriptor.launch_type is launch_type


def test_resolver_evidence_requires_hash_and_bounded_confidence():
    base = {
        "schema_version": "1.0",
        "resolver_id": "resolver.windows",
        "resolver_version": "1.0.0",
        "resolver_identity": "resolver.windows.local",
        "source_type": "app_paths",
        "source_reference": r"C:\Windows\notepad.exe",
        "discovered_at": datetime.now(timezone.utc),
        "metadata_hash": "a" * 64,
        "confidence": 0.95,
        "verification_state": "DISCOVERED",
        "verification_method": None,
        "verified_at": None,
    }
    evidence = ResolverEvidenceV1.model_validate(base)

    assert evidence.confidence == 0.95
    missing_hash = dict(base)
    missing_hash.pop("metadata_hash")
    with pytest.raises(ValidationError, match="Field required"):
        ResolverEvidenceV1.model_validate(missing_hash)
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        ResolverEvidenceV1.model_validate({**base, "confidence": 1.01})


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            IntentV2,
            {
                "schema_version": "2.0",
                "action": "execute",
                "target": "executor.launch",
                "parameters": {},
                "confidence": 0.95,
                "raw_input": "Abrir Notepad",
            },
        ),
        (
            PolicyDecisionV2,
            {
                "schema_version": "2.0",
                "decision_id": "decision_x",
                "decision": "ALLOW",
                "policy_ids": [],
                "reason": "Allowed",
                "risk_context": {},
                "timestamp": datetime.now(timezone.utc),
            },
        ),
        (
            AuthorizationGrantV1,
            {
                "schema_version": "1.0",
                "authorization_id": "authorization_x",
                "plan_id": "plan_x",
                "authorized_tools": ["executor.launch"],
                "params_hash": "a" * 64,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                "single_use": True,
                "created_at": datetime.now(timezone.utc),
            },
        ),
        (
            ApplicationDescriptorV1,
            {
                "schema_version": "1.0",
                "application_id": "app_x",
                "display_name": "Application",
                "aliases": [],
                "provider": "windows",
                "launch_type": "protocol_uri",
                "executable": None,
                "confidence": 0.9,
                "evidence": [],
            },
        ),
    ],
)
def test_versioned_contracts_reject_missing_required_fields(model, payload):
    with pytest.raises(ValidationError, match="Field required"):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            IntentV2,
            {
                "schema_version": "1.0",
                "intent_id": "intent_x",
                "action": "execute",
                "target": "executor.launch",
                "parameters": {},
                "confidence": 0.95,
                "raw_input": "Abrir Notepad",
            },
        ),
        (
            PolicyDecisionV2,
            {
                "schema_version": "1.0",
                "decision_id": "decision_x",
                "plan_id": "plan_x",
                "decision": "ALLOW",
                "policy_ids": [],
                "reason": "Allowed",
                "risk_context": {},
                "timestamp": datetime.now(timezone.utc),
            },
        ),
        (
            AuthorizationGrantV1,
            {
                "schema_version": "2.0",
                "authorization_id": "authorization_x",
                "plan_id": "plan_x",
                "user_id": "user_x",
                "authorized_tools": ["executor.launch"],
                "params_hash": "a" * 64,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                "single_use": True,
                "created_at": datetime.now(timezone.utc),
            },
        ),
        (
            ApplicationDescriptorV1,
            {
                "schema_version": "2.0",
                "application_id": "app_x",
                "display_name": "Application",
                "aliases": [],
                "provider": "windows",
                "launch_type": "protocol_uri",
                "launch_target": "xbox://game/example",
                "executable": None,
                "confidence": 0.9,
                "evidence": [],
            },
        ),
    ],
)
def test_versioned_contracts_reject_wrong_schema_version(model, payload):
    with pytest.raises(ValidationError, match="Input should be"):
        model.model_validate(payload)


def test_policy_decision_v2_rejects_non_policy_outcomes():
    payload = {
        "schema_version": "2.0",
        "decision_id": "decision_x",
        "plan_id": "plan_x",
        "decision": "APPROVE",
        "policy_ids": (),
        "reason": "Legacy recommendation",
        "risk_context": {},
        "timestamp": datetime.now(timezone.utc),
    }

    with pytest.raises(ValidationError, match="ALLOW"):
        PolicyDecisionV2.model_validate(payload)


def test_authorization_grant_v1_requires_future_expiration():
    with pytest.raises(ValidationError, match="later than created_at"):
        _grant(expires_at=datetime.now(timezone.utc))


def test_application_descriptor_v1_requires_executable_for_executable_launch():
    with pytest.raises(ValidationError, match="executable is required"):
        _descriptor(
            ApplicationLaunchTypeV1.EXECUTABLE,
            r"C:\Windows\notepad.exe",
            None,
        )
