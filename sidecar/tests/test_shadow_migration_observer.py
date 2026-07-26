"""Tests for isolated, non-authoritative shadow migration observation."""

from datetime import datetime, timezone

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ExecutionPlanV2,
    IntentV2,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import (
    ShadowMigrationGapType,
    ShadowMigrationObserver,
)


def _intent() -> Intent:
    return Intent(
        action="launch",
        target="executor.launch",
        parameters={
            "app_name": "Notepad",
            "nested": {"args": ["--safe-mode"]},
        },
        confidence=0.96,
        raw_input="Abrir Notepad",
        grounding_requirements=({"category": "application", "required": True},),
    )


def _plan(*, step_description: str = "") -> Plan:
    return Plan(
        intent=_intent(),
        description="Launch a resolved application",
        risk_score=0.4,
        estimated_duration_ms=750,
        steps=[
            PlanStep(
                id="discover",
                tool_id="app.discovery",
                params={"action": "lookup", "name": "Notepad"},
                description=step_description,
                estimated_impact="low",
                recovery_policy={"mode": "stop"},
            ),
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad"},
                is_reversible=True,
                rollback_tool_id="executor.kill",
                rollback_params={"process_name": "notepad.exe"},
                estimated_impact="medium",
                depends_on=["discover"],
                recovery_policy={"mode": "rollback"},
            ),
        ],
    )


def _profile() -> AppProfile:
    return AppProfile(
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


def test_shadow_intent_conversion():
    observer = ShadowMigrationObserver()
    legacy = _intent()

    first = observer.observe_intent(legacy)
    second = observer.observe_intent(legacy)
    converted = observer.get_versioned(first.migration_id)
    converted_again = observer.get_versioned(second.migration_id)

    assert first.conversion_success is True
    assert first.component == "intent"
    assert first.legacy_type == "Intent"
    assert first.versioned_type == "IntentV2"
    assert first.lost_fields == ()
    assert first.validation_errors == ()
    assert isinstance(converted, IntentV2)
    assert converted.parameters == legacy.parameters
    assert converted.grounding_requirements == tuple(legacy.grounding_requirements)
    assert converted.intent_id == converted_again.intent_id


def test_shadow_plan_conversion():
    observer = ShadowMigrationObserver()
    legacy = _plan()

    result = observer.observe_plan(legacy)
    converted = observer.get_versioned(result.migration_id)

    assert result.conversion_success is True
    assert result.component == "planner"
    assert result.versioned_type == "ExecutionPlanV2"
    assert result.lost_fields == ()
    assert isinstance(converted, ExecutionPlanV2)
    assert converted.description == legacy.description
    assert converted.risk_score == legacy.risk_score
    assert converted.estimated_duration_ms == 750
    assert converted.steps[1].reversible is True
    assert converted.steps[1].rollback_tool_id == "executor.kill"
    assert converted.steps[1].recovery_policy == {"mode": "rollback"}


def test_shadow_policy_conversion():
    observer = ShadowMigrationObserver()
    legacy = PolicyResult(
        effect=PolicyEffect.REQUIRE_CONFIRM,
        policy_id="identity,application.launch",
        reason="Interactive launch requires confirmation",
        context={"level": "medium", "interactive": True},
    )

    result = observer.observe_policy(
        legacy,
        plan_id="plan_notepad",
    )
    converted = observer.get_versioned(result.migration_id)

    assert result.conversion_success is True
    assert result.lost_fields == ()
    assert isinstance(converted, PolicyDecisionV2)
    assert converted.decision is PolicyDecisionValueV2.REQUIRE_CONSENT
    assert converted.policy_ids == ("identity", "application.launch")
    assert converted.reason == legacy.reason
    assert converted.risk_context == legacy.context
    assert any("REQUIRE_CONFIRM" in warning for warning in result.warnings)


def test_shadow_application_conversion():
    observer = ShadowMigrationObserver()
    legacy = _profile()

    result = observer.observe_application(legacy)
    converted = observer.get_versioned(result.migration_id)

    assert result.conversion_success is True
    assert result.lost_fields == ()
    assert isinstance(converted, ApplicationDescriptorV1)
    assert converted.application_id == legacy.app_id
    assert converted.display_name == legacy.name
    assert converted.executable == legacy.executable
    assert converted.source_evidence[-1]["legacy_data"] == legacy.to_dict()
    assert any("not cryptographically verified" in warning for warning in result.warnings)


def test_shadow_detects_loss():
    observer = ShadowMigrationObserver()

    result = observer.observe_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Allowed",
        ),
        plan_id="plan_notepad",
    )

    assert result.conversion_success is True
    assert any(
        diagnostic.gap_type is ShadowMigrationGapType.WARNING
        and "PolicyContextV1 was not supplied" in diagnostic.message
        for diagnostic in result.diagnostics
    )
    assert any("PolicyContextV1 was not supplied" in warning for warning in result.warnings)


def test_shadow_pending_action_reports_unmapped_consent_contract():
    observer = ShadowMigrationObserver()
    pending = PendingActionRecord(
        action_id="pending_launch",
        tool_id="executor.launch",
        params={"app_name": "Notepad"},
        reason="Confirmation required",
        created_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=600,
        risk_level="medium",
        plan_id="plan_notepad",
        params_hash="a" * 16,
        identity_hash="b" * 16,
        redacted=True,
    )

    result = observer.observe(pending)

    assert result.conversion_success is False
    assert result.component == "consent"
    assert result.versioned_type == "PendingConsentV1"
    assert result.lost_fields == (
        "intent_id",
        "step_id",
        "user_id",
    )
    assert result.validation_errors
    assert any(diagnostic.gap_type is ShadowMigrationGapType.MISSING_CONTRACT for diagnostic in result.diagnostics)
    assert observer.get_versioned(result.migration_id) is None


def test_shadow_validation_failure_is_reported_not_raised():
    observer = ShadowMigrationObserver()
    invalid = Intent(
        action="",
        target="executor.launch",
        confidence=2.0,
        raw_input="",
    )

    result = observer.observe(invalid)

    assert result.conversion_success is False
    assert result.versioned_type == "IntentV2"
    assert result.validation_errors
    assert len(observer.results()) == 1
