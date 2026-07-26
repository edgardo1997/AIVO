"""Characterize the opt-in runtime shadow conversion facade."""

import ast
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ExecutionPlanV2,
    IntentV2,
    PendingConsentV1,
    PolicyDecisionV2,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.shadow import (
    RuntimeShadowAdapter,
    RuntimeShadowConversionStatus,
    ShadowDecisionComparison,
    ShadowMigrationObserver,
)


def _intent() -> Intent:
    return Intent(
        action="launch",
        target="executor.launch",
        parameters={"app_name": "Notepad", "nested": {"safe": True}},
        confidence=0.95,
        raw_input="Abrir Notepad",
    )


def _plan() -> Plan:
    return Plan(
        intent=_intent(),
        description="Launch resolved app",
        steps=[
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad"},
                estimated_impact="medium",
            )
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


def _pending() -> PendingActionRecord:
    return PendingActionRecord(
        action_id="pending_launch",
        tool_id="executor.launch",
        params={"app_name": "Notepad"},
        reason="Confirmation required",
        created_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=300,
        risk_level="medium",
        plan_id="plan_notepad",
        params_hash="a" * 16,
        identity_hash="b" * 16,
        redacted=True,
    )


def test_runtime_shadow_converts_supported_legacy_models():
    adapter = RuntimeShadowAdapter()

    intent = adapter.convert_intent(_intent(), intent_id="intent_notepad")
    plan = adapter.convert_plan(_plan(), intent_id="intent_notepad")
    policy = adapter.convert_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Allowed",
        ),
        plan_id="plan_notepad",
    )
    application = adapter.convert_application(_profile())
    pending = adapter.convert_pending_action(
        _pending(),
        intent_id="intent_notepad",
        step_id="launch",
        user_id="user_local",
    )

    assert isinstance(intent.converted, IntentV2)
    assert isinstance(plan.converted, ExecutionPlanV2)
    assert isinstance(policy.converted, PolicyDecisionV2)
    assert isinstance(application.converted, ApplicationDescriptorV1)
    assert isinstance(pending.converted, PendingConsentV1)
    assert policy.conversion_status is RuntimeShadowConversionStatus.WARNING


def test_runtime_shadow_preserves_data_and_does_not_mutate_originals():
    adapter = RuntimeShadowAdapter()
    legacy = _plan()
    before = deepcopy(legacy)

    conversion = adapter.convert_plan(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )

    assert conversion.conversion_status is RuntimeShadowConversionStatus.SUCCESS
    assert conversion.converted.description == legacy.description
    assert conversion.converted.steps[0].parameters == legacy.steps[0].params
    assert legacy == before


def test_runtime_shadow_reports_missing_context_without_raising():
    conversion = RuntimeShadowAdapter().convert_pending_action(_pending())

    assert conversion.conversion_status is RuntimeShadowConversionStatus.WARNING
    assert conversion.converted is None
    assert conversion.warnings == (
        "missing_field: intent_id",
        "missing_field: step_id",
        "missing_field: user_id",
    )

    result = ShadowMigrationObserver().observe_runtime_conversion(conversion)
    assert result.conversion_success is False
    assert result.conversion_status == "WARNING"
    assert result.lost_fields == ("intent_id", "step_id", "user_id")


def test_runtime_shadow_observer_records_comparison_status():
    conversion = RuntimeShadowAdapter().convert_policy(
        PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Allowed",
        ),
        plan_id="plan_notepad",
    )
    comparison = ShadowDecisionComparison.compare(
        component="executor.launch",
        legacy_decision="ALLOW",
        shadow_decision="REQUIRE_CONSENT",
    )

    result = ShadowMigrationObserver().observe_runtime_conversion(
        conversion,
        comparison=comparison,
    )

    assert result.conversion_status == "WARNING"
    assert result.comparison_status == "DIVERGENCE"


def test_runtime_shadow_reports_unsupported_input_as_error():
    conversion = RuntimeShadowAdapter().convert(object())
    assert conversion.conversion_status is RuntimeShadowConversionStatus.ERROR
    assert conversion.validation_errors


def test_runtime_shadow_adapter_has_no_execution_imports():
    path = Path(__file__).resolve().parents[2] / "sentinel/shadow/runtime_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imported.isdisjoint(
        {
            "sentinel.core.orchestrator",
            "sentinel.core.tool_gateway",
            "sidecar.services.executor_service",
            "sidecar.modules.executor",
        }
    )
