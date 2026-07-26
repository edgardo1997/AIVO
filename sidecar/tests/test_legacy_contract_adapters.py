"""Tests for isolated legacy-to-versioned contract adapters."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.adapters import (
    app_profile_to_v1,
    intent_to_v2,
    plan_to_v2,
    policy_result_to_v2,
)
from sentinel.contracts import (
    ApplicationLaunchTypeV1,
    PolicyDecisionValueV2,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult


def _legacy_intent() -> Intent:
    return Intent(
        action="launch",
        target="executor.launch",
        parameters={
            "app_name": "Notepad",
            "credentials": {
                "token": "sensitive-value",
                "scopes": ["application.launch"],
            },
        },
        confidence=0.95,
        raw_input="Abrir Notepad",
    )


def _legacy_plan() -> Plan:
    intent = _legacy_intent()
    return Plan(
        steps=[
            PlanStep(
                id="discover",
                tool_id="app.discovery",
                params={
                    "action": "lookup",
                    "name": "Notepad",
                    "auth": {"token": "sensitive-value"},
                },
            ),
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Notepad", "args": ""},
                depends_on=["discover"],
                estimated_impact="medium",
            ),
        ],
        intent=intent,
        risk_score=0.4,
        description="Launch Notepad",
    )


def _legacy_profile() -> AppProfile:
    return AppProfile(
        app_id="notepad",
        name="Notepad",
        executable=r"C:\Windows\System32\notepad.exe",
        category="utility",
        capabilities=["text.edit"],
        required_permissions=["executor.launch"],
        source="app_paths",
        confidence=0.98,
        discovered_at="2026-07-24T12:00:00Z",
        expires_at="2026-07-24T12:05:00Z",
    )


def test_intent_adapter_converts_legacy_intent_without_data_loss():
    legacy = _legacy_intent()

    converted = intent_to_v2(legacy, intent_id="intent_notepad")

    assert converted.schema_version == "2.0"
    assert converted.intent_id == "intent_notepad"
    assert converted.action == legacy.action
    assert converted.target == legacy.target
    assert converted.confidence == legacy.confidence
    assert converted.raw_input == legacy.raw_input
    assert converted.parameters == legacy.parameters
    assert converted.parameters["credentials"]["token"] == "sensitive-value"


def test_intent_adapter_generates_prefixed_identifier():
    converted = intent_to_v2(_legacy_intent())

    assert converted.intent_id.startswith("intent_")


def test_plan_adapter_converts_steps_and_produces_stable_hash():
    legacy = _legacy_plan()

    first = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_first",
    )
    second = plan_to_v2(
        legacy,
        intent_id="intent_notepad",
        plan_id="plan_second",
    )

    assert first.schema_version == "2.0"
    assert first.plan_id == "plan_first"
    assert first.intent_id == "intent_notepad"
    assert [step.step_id for step in first.steps] == ["discover", "launch"]
    assert first.steps[1].depends_on == ("discover",)
    assert first.params_hash == second.params_hash
    assert first.params_hash == first.calculate_params_hash(
        intent_id=first.intent_id,
        steps=first.steps,
    )
    assert first.steps[0].parameters["auth"]["token"] == "sensitive-value"


@pytest.mark.parametrize(
    ("legacy_effect", "expected"),
    [
        (PolicyEffect.ALLOW, PolicyDecisionValueV2.ALLOW),
        (
            PolicyEffect.REQUIRE_CONFIRM,
            PolicyDecisionValueV2.REQUIRE_CONSENT,
        ),
        (PolicyEffect.DENY, PolicyDecisionValueV2.DENY),
    ],
)
def test_policy_adapter_maps_all_legacy_effects(
    legacy_effect,
    expected,
):
    legacy = PolicyResult(
        effect=legacy_effect,
        policy_id="policy.application,policy.identity",
        reason="Legacy policy result",
        context={
            "risk": "medium",
            "authorization_token": "sensitive-value",
        },
    )
    timestamp = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

    converted = policy_result_to_v2(
        legacy,
        plan_id="plan_notepad",
        decision_id="decision_notepad",
        timestamp=timestamp,
    )

    assert converted.decision is expected
    assert converted.policy_ids == (
        "policy.application",
        "policy.identity",
    )
    assert converted.risk_context == legacy.context
    assert converted.risk_context["authorization_token"] == "sensitive-value"
    assert converted.timestamp == timestamp


def test_app_profile_adapter_preserves_legacy_profile_as_evidence():
    legacy = _legacy_profile()

    converted = app_profile_to_v1(legacy)

    assert converted.schema_version == "1.0"
    assert converted.application_id == legacy.app_id
    assert converted.display_name == legacy.name
    assert converted.provider == legacy.source
    assert converted.launch_type is ApplicationLaunchTypeV1.EXECUTABLE
    assert converted.launch_target == legacy.executable
    assert converted.executable == legacy.executable
    assert converted.confidence == legacy.confidence
    snapshot = converted.evidence[-1]["legacy_data"]
    assert snapshot["capabilities"] == ["text.edit"]
    assert snapshot["required_permissions"] == ["executor.launch"]
    assert snapshot["discovered_at"] == legacy.discovered_at
    assert snapshot["expires_at"] == legacy.expires_at


def test_app_discovery_mapping_supports_non_executable_launch_target():
    discovery = {
        "app_id": "forza-horizon",
        "name": "Forza Horizon",
        "aliases": ["forza", "fh"],
        "provider": "xbox",
        "aumid": "Microsoft.ForzaHorizon_8wekyb3d8bbwe!Game",
        "confidence": 0.91,
        "evidence": [{"source": "start_apps"}],
    }

    converted = app_profile_to_v1(discovery)

    assert converted.launch_type is ApplicationLaunchTypeV1.AUMID
    assert converted.launch_target == discovery["aumid"]
    assert converted.executable is None
    assert converted.aliases == ("forza", "fh")
    assert converted.evidence[0] == {"source": "start_apps"}


def test_adapters_do_not_modify_or_share_mutable_legacy_data():
    intent = _legacy_intent()
    plan = _legacy_plan()
    policy = PolicyResult(
        effect=PolicyEffect.ALLOW,
        policy_id="policy.application",
        reason="Allowed",
        context={"nested": {"secret": "keep"}},
    )
    discovery = {
        "app_id": "calculator",
        "name": "Calculator",
        "provider": "windows_store",
        "aumid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
        "confidence": 1.0,
        "evidence": [{"source": "start_apps", "secret": "keep"}],
    }
    originals = (
        deepcopy(intent),
        deepcopy(plan),
        deepcopy(policy),
        deepcopy(discovery),
    )

    converted_intent = intent_to_v2(intent, intent_id="intent_x")
    converted_plan = plan_to_v2(plan, intent_id="intent_x")
    converted_policy = policy_result_to_v2(
        policy,
        plan_id="plan_x",
    )
    converted_app = app_profile_to_v1(discovery)

    converted_intent.parameters["credentials"]["token"] = "changed"
    converted_policy.risk_context["nested"]["secret"] = "changed"
    converted_app.evidence[0]["secret"] = "changed"

    assert intent == originals[0]
    assert plan == originals[1]
    assert policy == originals[2]
    assert discovery == originals[3]
    assert converted_plan.steps[0].parameters["auth"]["token"] == "sensitive-value"


@pytest.mark.parametrize(
    ("adapter", "value", "kwargs", "message"),
    [
        (
            intent_to_v2,
            object(),
            {},
            "intent must be a sentinel.core.intent.Intent",
        ),
        (
            plan_to_v2,
            object(),
            {"intent_id": "intent_x"},
            "plan must be a sentinel.core.planner.Plan",
        ),
        (
            policy_result_to_v2,
            object(),
            {"plan_id": "plan_x"},
            "result must be a sentinel.core.policy.PolicyResult",
        ),
        (
            app_profile_to_v1,
            object(),
            {},
            "profile must be an AppProfile or AppDiscovery mapping",
        ),
    ],
)
def test_adapters_reject_wrong_legacy_model_with_clear_error(
    adapter,
    value,
    kwargs,
    message,
):
    with pytest.raises(TypeError, match=message):
        adapter(value, **kwargs)


def test_plan_and_policy_adapters_require_missing_relationship_ids():
    with pytest.raises(
        ValueError,
        match="intent_id is required because the legacy model does not contain it",
    ):
        plan_to_v2(_legacy_plan(), intent_id="")

    legacy_policy = PolicyResult(
        effect=PolicyEffect.ALLOW,
        policy_id="policy.application",
        reason="Allowed",
    )
    with pytest.raises(
        ValueError,
        match="plan_id is required because the legacy model does not contain it",
    ):
        policy_result_to_v2(legacy_policy, plan_id="")


def test_app_adapter_reports_missing_launch_target_clearly():
    discovery = {
        "app_id": "unknown",
        "name": "Unknown application",
        "provider": "unknown",
        "confidence": 0.5,
    }

    with pytest.raises(
        ValueError,
        match="application launch target is required",
    ):
        app_profile_to_v1(discovery)


def test_adapter_surfaces_missing_required_contract_fields():
    incomplete = {
        "name": "Protocol application",
        "provider": "protocol",
        "protocol_uri": "sample://open",
        "confidence": 0.8,
    }

    with pytest.raises(ValidationError, match="application_id"):
        app_profile_to_v1(incomplete)
