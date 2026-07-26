"""Machine-readable shadow-gap and authority-boundary tests."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.contracts import ApplicationDescriptorV1
from sentinel.core.decision_engine import Decision, DecisionEngine
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import (
    ShadowMigrationGapType,
    ShadowMigrationObserver,
)


def _pending() -> PendingActionRecord:
    return PendingActionRecord(
        action_id="pending_notepad",
        tool_id="executor.launch",
        params={"app_name": "Notepad"},
        reason="Consent required",
        created_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=600,
        risk_level="medium",
        plan_id="plan_notepad",
    )


def test_shadow_reports_missing_contract_and_missing_fields():
    result = ShadowMigrationObserver().observe_pending_action(_pending())
    gap_types = {item.gap_type for item in result.diagnostics}

    assert result.conversion_success is False
    assert ShadowMigrationGapType.MISSING_CONTRACT in gap_types
    assert ShadowMigrationGapType.MISSING_FIELD in gap_types
    assert set(result.lost_fields) == {
        "intent_id",
        "step_id",
        "user_id",
    }


def test_shadow_pending_consent_conversion_closes_context_gaps():
    observer = ShadowMigrationObserver()

    result = observer.observe_pending_action(
        _pending(),
        intent_id="intent_notepad",
        step_id="launch",
        user_id="user_local",
    )

    assert result.conversion_success is True
    assert result.lost_fields == ()
    assert all(diagnostic.gap_type is ShadowMigrationGapType.WARNING for diagnostic in result.diagnostics)


def test_shadow_reports_warning_for_missing_policy_context():
    result = ShadowMigrationObserver().observe_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Allowed",
        ),
        plan_id="plan_notepad",
    )

    assert any(
        item.gap_type is ShadowMigrationGapType.WARNING and "PolicyContextV1 was not supplied" in item.message
        for item in result.diagnostics
    )


def test_shadow_plan_reports_no_missing_execution_step_fields():
    intent = Intent(
        action="launch",
        target="executor.launch",
        parameters={"app_name": "Notepad"},
        raw_input="Abrir Notepad",
    )
    plan = Plan(
        intent=intent,
        steps=[
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad"},
                description="Launch resolved application",
                estimated_duration_ms=500,
                model_decision=None,
                estimated_impact="medium",
                is_reversible=True,
                rollback_tool_id="executor.kill",
                rollback_params={"process_name": "notepad.exe"},
                recovery_policy={"mode": "rollback"},
            )
        ],
    )

    result = ShadowMigrationObserver().observe_plan(plan)

    assert result.conversion_success is True
    assert result.lost_fields == ()
    assert not any(item.gap_type is ShadowMigrationGapType.MISSING_FIELD for item in result.diagnostics)


def test_application_descriptor_without_resolver_evidence_is_rejected():
    with pytest.raises(ValidationError, match="Field required"):
        ApplicationDescriptorV1.model_validate(
            {
                "schema_version": "1.0",
                "application_id": "notepad",
                "display_name": "Notepad",
                "aliases": ["notepad"],
                "provider": "user_input",
                "launch_type": "executable",
                "launch_target": r"C:\Windows\notepad.exe",
                "executable": r"C:\Windows\notepad.exe",
                "confidence": 1.0,
                "evidence": [{"source": "user_input"}],
                "resolver_id": "user",
                "resolved_at": datetime.now(timezone.utc),
                "install_state": "installed",
                "verification_level": "verified",
                "source_evidence": [{"source": "user_input"}],
                "metadata_hash": "a" * 64,
            }
        )


def test_decision_engine_and_shadow_observer_cannot_authorize_execution():
    intent = Intent(
        action="launch",
        target="executor.launch",
        parameters={"app_name": "Notepad"},
        raw_input="Abrir Notepad",
    )
    plan = Plan(
        intent=intent,
        steps=[
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad"},
                estimated_impact="medium",
            )
        ],
        risk_score=0.4,
    )
    recommendation = DecisionEngine(get_permission_level=lambda: "admin").evaluate(plan)
    observer = ShadowMigrationObserver()

    assert recommendation.decision == Decision.APPROVE
    assert not hasattr(recommendation, "authorization_grant")
    assert not hasattr(recommendation, "execute")
    assert not hasattr(observer, "authorize")
    assert not hasattr(observer, "execute")
