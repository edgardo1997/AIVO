"""Migration-readiness audit tests for versioned contracts and adapters.

Passing tests cover information that is representable today. Strict xfails
record integration blockers where the current contracts cannot preserve or
enforce a required invariant without a future design change.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.adapters import (
    app_profile_to_v1,
    intent_to_v2,
    plan_to_v2,
    policy_result_to_v2,
)
from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationVerificationLevelV1,
    AuthorizationGrantV1,
    AuthorizedStepV1,
    ExecutionPlanV2,
    ExecutionStepV2,
    LaunchErrorCodeV1,
    LaunchReceiptV1,
    LaunchStateV1,
    PolicyContextV1,
    PolicyDecisionValueV2,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.capability_registry import RiskLevel
from sentinel.core.goals import GoalDefinition
from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult


def _intent(*, grounding_requirements=None) -> Intent:
    return Intent(
        action="launch",
        target="executor.launch",
        parameters={
            "app_name": "Notepad",
            "nested": {
                "args": ["--safe-mode"],
                "opaque_reference": "secret-ref-123",
            },
        },
        confidence=0.94,
        raw_input="Abrir Notepad",
        grounding_requirements=grounding_requirements or [],
    )


def _plan() -> Plan:
    return Plan(
        intent=_intent(),
        description="Launch Notepad after discovery",
        goal=GoalDefinition(
            id="goal_launch_application",
            name="Launch application",
            description="Resolve and launch a trusted application",
            related_intents=["executor.launch"],
            possible_capabilities=[
                "app.discovery",
                "executor.launch",
            ],
            base_risk=RiskLevel.MEDIUM,
        ),
        risk_score=0.42,
        estimated_duration_ms=1250,
        steps=[
            PlanStep(
                id="discover",
                tool_id="app.discovery",
                params={
                    "action": "lookup",
                    "name": "Notepad",
                    "opaque_reference": "secret-ref-123",
                },
                description="Resolve trusted launch metadata",
                estimated_duration_ms=250,
                recovery_policy={"mode": "stop"},
            ),
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad", "args": ""},
                description="Launch resolved application",
                is_reversible=True,
                rollback_tool_id="executor.kill",
                rollback_params={"process_name": "notepad.exe"},
                estimated_impact="medium",
                estimated_duration_ms=1000,
                depends_on=["discover"],
                recovery_policy={"mode": "rollback"},
            ),
        ],
    )


def _versioned_plan() -> ExecutionPlanV2:
    step = ExecutionStepV2(
        schema_version="2.0",
        step_id="launch",
        tool_id="executor.launch",
        parameters={"application_id": "notepad"},
    )
    params_hash = ExecutionPlanV2.calculate_params_hash(
        intent_id="intent_notepad",
        steps=(step,),
    )
    return ExecutionPlanV2(
        schema_version="2.0",
        plan_id="plan_notepad",
        intent_id="intent_notepad",
        steps=(step,),
        params_hash=params_hash,
    )


def test_legacy_intent_preserves_all_representable_information():
    legacy = _intent()
    converted = intent_to_v2(legacy, intent_id="intent_notepad")

    assert converted.action == legacy.action
    assert converted.target == legacy.target
    assert converted.parameters == legacy.parameters
    assert converted.confidence == legacy.confidence
    assert converted.raw_input == legacy.raw_input
    assert converted.intent_id == "intent_notepad"


def test_legacy_intent_does_not_silently_drop_grounding_requirements():
    grounding = [{"category": "application", "required": True}]
    converted = intent_to_v2(
        _intent(grounding_requirements=grounding),
        intent_id="intent_grounded",
    )

    assert converted.grounding_requirements == tuple(grounding)


def test_legacy_plan_preserves_executable_parameters_and_dependencies():
    legacy = _plan()
    converted = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )

    assert converted.plan_id == "plan_notepad"
    assert converted.intent_id == "intent_notepad"
    assert len(converted.steps) == len(legacy.steps)
    for source, target in zip(legacy.steps, converted.steps):
        assert target.step_id == source.id
        assert target.tool_id == source.tool_id
        assert target.parameters == source.params
        assert target.depends_on == tuple(source.depends_on)


def test_legacy_plan_does_not_silently_drop_operational_metadata():
    legacy = _plan()
    converted = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )
    serialized = converted.model_dump(mode="json")

    assert serialized["description"] == legacy.description
    assert serialized["risk_score"] == legacy.risk_score
    assert serialized["goal"] == legacy.goal.to_dict()
    assert serialized["estimated_duration_ms"] == legacy.estimated_duration_ms
    launch = serialized["steps"][1]
    assert launch["is_reversible"] is True
    assert launch["rollback_tool_id"] == "executor.kill"
    assert launch["rollback_params"] == {"process_name": "notepad.exe"}
    assert launch["recovery_policy"] == {"mode": "rollback"}


def test_plan_hash_and_injected_identity_are_stable():
    legacy = _plan()

    first = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )
    second = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )

    assert first.plan_id == second.plan_id
    assert first.intent_id == second.intent_id
    assert first.params_hash == second.params_hash


@pytest.mark.parametrize(
    ("effect", "decision"),
    [
        (PolicyEffect.ALLOW, PolicyDecisionValueV2.ALLOW),
        (
            PolicyEffect.REQUIRE_CONFIRM,
            PolicyDecisionValueV2.REQUIRE_CONSENT,
        ),
        (PolicyEffect.DENY, PolicyDecisionValueV2.DENY),
    ],
)
def test_legacy_policy_preserves_complete_decision_information(
    effect,
    decision,
):
    timestamp = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    legacy = PolicyResult(
        effect=effect,
        policy_id="identity,application.launch",
        reason="Policy evaluation result",
        context={
            "risk": {"level": "medium"},
            "opaque_reference": "secret-ref-123",
        },
    )

    converted = policy_result_to_v2(
        legacy,
        plan_id="plan_notepad",
        decision_id="decision_notepad",
        timestamp=timestamp,
    )

    assert converted.decision == decision
    assert converted.policy_ids == ("identity", "application.launch")
    assert converted.reason == legacy.reason
    assert converted.risk_context == legacy.context
    assert converted.timestamp == timestamp
    assert converted.timestamp.utcoffset() is not None


def test_legacy_application_profile_is_preserved_as_evidence():
    legacy = AppProfile(
        app_id="notepad",
        name="Notepad",
        executable=r"C:\Windows\System32\notepad.exe",
        category="utility",
        capabilities=["text.edit"],
        required_permissions=["executor.launch"],
        source="app_paths",
        confidence=0.99,
        discovered_at="2026-07-24T12:00:00Z",
        expires_at="2026-07-24T12:05:00Z",
    )

    converted = app_profile_to_v1(legacy)
    snapshot = converted.evidence[-1]["legacy_data"]

    assert converted.application_id == legacy.app_id
    assert converted.display_name == legacy.name
    assert converted.provider == legacy.source
    assert converted.executable == legacy.executable
    assert snapshot == legacy.to_dict()


def test_application_adapter_does_not_expose_sensitive_source_fields():
    converted = app_profile_to_v1(
        {
            "app_id": "private-app",
            "name": "Private App",
            "provider": "enterprise",
            "executable": r"C:\Private\app.exe",
            "confidence": 0.9,
            "api_token": "must-not-be-serialized",
        }
    )

    assert "must-not-be-serialized" not in converted.model_dump_json()


def _grant(
    plan: ExecutionPlanV2,
    *,
    created_at: datetime | None = None,
) -> AuthorizationGrantV1:
    created = created_at or datetime.now(timezone.utc)
    step = AuthorizedStepV1(
        step_id=plan.steps[0].step_id,
        tool_id=plan.steps[0].tool_id,
        params_hash=plan.params_hash,
    )
    return AuthorizationGrantV1.issue(
        authorization_id="authorization_notepad",
        plan_id=plan.plan_id,
        user_id="user_local",
        policy_decision_id="decision_notepad",
        issuer="sentinel.policy-engine",
        nonce="nonce-notepad",
        authorized_steps=(step,),
        params_hash=plan.params_hash,
        expires_at=created + timedelta(minutes=5),
        created_at=created,
    )


def test_authorization_grant_binds_declared_plan_and_hash_and_validates_dates():
    plan = _versioned_plan()
    created_at = datetime.now(timezone.utc)
    grant = _grant(plan, created_at=created_at)

    assert grant.plan_id == plan.plan_id
    assert grant.params_hash == plan.params_hash
    with pytest.raises(ValidationError, match="later than created_at"):
        AuthorizationGrantV1.model_validate(
            {
                **grant.model_dump(),
                "expires_at": created_at - timedelta(seconds=1),
            }
        )


def test_grant_requires_single_use():
    plan = _versioned_plan()
    grant = _grant(plan)
    payload = grant.model_dump()
    payload["single_use"] = False

    with pytest.raises(ValidationError, match="Input should be True"):
        AuthorizationGrantV1.model_validate(payload)


def test_grant_requires_policy_origin():
    plan = _versioned_plan()
    grant = _grant(plan)
    payload = grant.model_dump()
    payload["policy_decision_id"] = ""

    with pytest.raises(ValidationError, match="at least 1 character"):
        AuthorizationGrantV1.model_validate(payload)


def test_grant_detects_parameter_change():
    plan = _versioned_plan()
    grant = _grant(plan)
    payload = grant.model_dump()
    payload["authorized_steps"][0]["params_hash"] = "f" * 64

    with pytest.raises(ValidationError, match="grant_hash does not match"):
        AuthorizationGrantV1.model_validate(payload)


def test_grant_hash_is_deterministic():
    plan = _versioned_plan()
    created_at = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    assert _grant(plan, created_at=created_at).grant_hash == _grant(plan, created_at=created_at).grant_hash


def test_grant_cannot_replay():
    plan = _versioned_plan()
    grant = _grant(plan)
    consumed = grant.mark_consumed(grant.created_at + timedelta(seconds=1))

    with pytest.raises(PermissionError, match="already been consumed"):
        consumed.assert_usable(at=grant.created_at + timedelta(seconds=2))
    with pytest.raises(PermissionError, match="already been consumed"):
        consumed.mark_consumed(grant.created_at + timedelta(seconds=2))


def test_launch_target_without_origin_rejected():
    with pytest.raises(ValidationError, match="Field required"):
        ApplicationDescriptorV1(
            schema_version="1.0",
            application_id="user-supplied",
            display_name="User supplied target",
            aliases=("user supplied target",),
            provider="user_input",
            launch_type="executable",
            launch_target=r"C:\Untrusted\user-supplied.exe",
            executable=r"C:\Untrusted\user-supplied.exe",
            confidence=1.0,
            evidence=(),
        )


def test_unverified_descriptor_cannot_be_verified():
    converted = app_profile_to_v1(
        {
            "app_id": "notepad",
            "name": "Notepad",
            "provider": "app_paths",
            "executable": r"C:\Windows\notepad.exe",
            "confidence": 0.9,
        }
    )
    payload = converted.model_dump()
    payload["verification_level"] = ApplicationVerificationLevelV1.VERIFIED
    payload["source_evidence"] = ()

    with pytest.raises(ValidationError, match="at least 1 item"):
        ApplicationDescriptorV1.model_validate(payload)


def test_missing_source_evidence_rejected():
    converted = app_profile_to_v1(
        {
            "app_id": "notepad",
            "name": "Notepad",
            "provider": "app_paths",
            "executable": r"C:\Windows\notepad.exe",
            "confidence": 0.9,
        }
    )
    payload = converted.model_dump()
    payload.pop("source_evidence")

    with pytest.raises(ValidationError, match="Field required"):
        ApplicationDescriptorV1.model_validate(payload)


def test_application_descriptor_detects_metadata_change():
    converted = app_profile_to_v1(
        {
            "app_id": "notepad",
            "name": "Notepad",
            "provider": "app_paths",
            "executable": r"C:\Windows\notepad.exe",
            "confidence": 0.9,
        }
    )
    payload = converted.model_dump()
    payload["launch_target"] = r"C:\Untrusted\replacement.exe"

    with pytest.raises(
        ValidationError,
        match="metadata_hash does not match",
    ):
        ApplicationDescriptorV1.model_validate(payload)


def test_policy_context_v1_is_strict_frozen_and_timezone_aware():
    user_id = "user_local"
    context = PolicyContextV1(
        schema_version="1.0",
        user_id=user_id,
        identity_hash=PolicyContextV1.calculate_identity_hash(user_id),
        plan_id="plan_notepad",
        intent_id="intent_notepad",
        risk_level="medium",
        evaluated_policies=("identity", "application.launch"),
        evaluated_policy_versions={
            "identity": "1.0.0",
            "application.launch": "2.0.0",
        },
        evaluated_at=datetime.now(timezone.utc),
        policy_engine_version="1.0.0",
        decision_origin="shadow-test",
    )

    with pytest.raises(ValidationError, match="frozen"):
        context.user_id = "another-user"
    with pytest.raises(ValidationError, match="Extra inputs"):
        PolicyContextV1.model_validate(
            {
                **context.model_dump(),
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError, match="timezone"):
        PolicyContextV1.model_validate(
            {
                **context.model_dump(),
                "evaluated_at": datetime(2026, 7, 24, 12, 0),
            }
        )


def test_launch_receipt_validates_states_evidence_errors_and_timestamps():
    started_at = datetime.now(timezone.utc)
    running = LaunchReceiptV1(
        schema_version="1.0",
        receipt_id="receipt_notepad",
        authorization_id="authorization_notepad",
        plan_id="plan_notepad",
        step_id="launch",
        application_id="notepad",
        state=LaunchStateV1.RUNNING,
        pid=4242,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
        evidence=({"process_id": 4242, "window_detected": True},),
        error_code=None,
    )

    assert running.state is LaunchStateV1.RUNNING
    with pytest.raises(ValidationError, match="running state requires"):
        LaunchReceiptV1.model_validate(
            {
                **running.model_dump(),
                "evidence": (),
            }
        )
    with pytest.raises(ValidationError, match="failed state requires"):
        LaunchReceiptV1.model_validate(
            {
                **running.model_dump(),
                "state": LaunchStateV1.FAILED,
                "evidence": (),
                "error_code": None,
            }
        )
    failed = LaunchReceiptV1.model_validate(
        {
            **running.model_dump(),
            "state": LaunchStateV1.FAILED,
            "evidence": (),
            "error_code": LaunchErrorCodeV1.LAUNCH_TIMEOUT,
        }
    )
    assert failed.error_code is LaunchErrorCodeV1.LAUNCH_TIMEOUT
    with pytest.raises(ValidationError, match="earlier than started_at"):
        LaunchReceiptV1.model_validate(
            {
                **failed.model_dump(),
                "completed_at": started_at - timedelta(seconds=1),
            }
        )
    with pytest.raises(ValidationError, match="launch_requested"):
        LaunchReceiptV1.model_validate(
            {
                **running.model_dump(),
                "state": "not-a-state",
            }
        )


def test_versioned_models_reject_invalid_versions_and_naive_timestamps():
    with pytest.raises(ValidationError, match="Input should be '2.0'"):
        ExecutionStepV2(
            schema_version="1.0",
            step_id="launch",
            tool_id="executor.launch",
            parameters={},
        )

    with pytest.raises(ValidationError, match="timezone"):
        policy_result_to_v2(
            PolicyResult(
                effect=PolicyEffect.ALLOW,
                policy_id="application.launch",
                reason="Allowed",
            ),
            plan_id="plan_notepad",
            timestamp=datetime(2026, 7, 24, 12, 0),
        )
