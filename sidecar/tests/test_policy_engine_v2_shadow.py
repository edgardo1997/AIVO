"""Characterization tests for the non-authoritative policy V2 shadow."""

import ast
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from sentinel.application_discovery_v2 import (
    ApplicationResolverV2,
    ResolverRegistry,
    Win32Resolver,
)
from sentinel.contracts import (
    ExecutionPlanV2,
    ExecutionStepV2,
    IdentityContextV1,
    IntentV2,
    PolicyContextV1,
    PolicyDecisionValueV2,
)
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.policy_v2_shadow import (
    PolicyEngineV2Shadow,
    PolicyRuleAdapter,
    PolicyShadowComparison,
    PolicyShadowMetrics,
    policy_shadow_enabled,
)


def _intent() -> IntentV2:
    return IntentV2(
        schema_version="2.0",
        intent_id="intent_notepad",
        action="execute",
        target="executor.launch",
        parameters={},
        confidence=0.95,
        raw_input="Abrir Notepad",
    )


def _plan() -> ExecutionPlanV2:
    step = ExecutionStepV2(
        schema_version="2.0",
        step_id="launch",
        tool_id="executor.launch",
        parameters={"application_id": "win32.notepad"},
    )
    return ExecutionPlanV2(
        schema_version="2.0",
        plan_id="plan_notepad",
        intent_id="intent_notepad",
        steps=(step,),
        params_hash=ExecutionPlanV2.calculate_params_hash(
            intent_id="intent_notepad",
            steps=(step,),
        ),
    )


def _identity() -> IdentityContextV1:
    return IdentityContextV1.create(
        user_id="local-user",
        session_id="session-shadow",
        roles=("user",),
        authentication_method="local",
        created_at=datetime.now(timezone.utc),
    )


def _policy_context(
    *,
    version: str = "1.0",
) -> PolicyContextV1:
    now = datetime.now(timezone.utc)
    return PolicyContextV1(
        schema_version="1.0",
        user_id="local-user",
        identity_hash=PolicyContextV1.calculate_identity_hash("local-user"),
        plan_id="plan_notepad",
        intent_id="intent_notepad",
        risk_level="medium",
        evaluated_policies=("application.launch",),
        evaluated_policy_versions={"application.launch": version},
        evaluated_at=now,
        policy_engine_version="shadow-2.0",
        decision_origin="policy_v2_shadow",
    )


def _application():
    resolver = ApplicationResolverV2(
        ResolverRegistry(
            (
                Win32Resolver(
                    (
                        {
                            "application_id": "win32.notepad",
                            "display_name": "Notepad",
                            "launch_type": "executable",
                            "launch_target": (r"C:\Windows\System32\notepad.exe"),
                            "executable": (r"C:\Windows\System32\notepad.exe"),
                        },
                    )
                ),
            )
        )
    )
    return resolver.resolve({"action": "lookup", "name": "Notepad"})


def _legacy(
    effect: PolicyEffect = PolicyEffect.ALLOW,
) -> PolicyResult:
    return PolicyResult(
        effect=effect,
        policy_id="application.launch",
        reason="Legacy result",
        context={"risk": "medium"},
    )


def _evaluate(
    *,
    effect: PolicyEffect = PolicyEffect.ALLOW,
    identity=True,
    context=True,
    version: str = "1.0",
):
    rules = PolicyRuleAdapter.adapt(_legacy(effect), version=version)
    return PolicyEngineV2Shadow(enabled=True).evaluate(
        intent=_intent(),
        plan=_plan(),
        identity=_identity() if identity else None,
        policy_context=(_policy_context(version=version) if context else None),
        application=_application(),
        rules=rules,
    )


def test_policy_shadow_disabled_default(monkeypatch):
    monkeypatch.delenv("POLICY_ENGINE_V2_SHADOW_ENABLED", raising=False)
    assert policy_shadow_enabled() is False
    engine = PolicyEngineV2Shadow()
    assert engine.enabled is False
    result = engine.evaluate(
        intent=_intent(),
        plan=_plan(),
        identity=_identity(),
        policy_context=_policy_context(),
        application=_application(),
        rules=PolicyRuleAdapter.adapt(_legacy(), version="1.0"),
    )
    assert result.decision is None


def test_policy_shadow_creates_decision():
    result = _evaluate()
    assert result.decision is not None
    assert result.decision.plan_id == "plan_notepad"
    assert result.decision.policy_context is not None
    assert result.decision.policy_context.intent_id == "intent_notepad"
    assert result.decision.policy_context.evaluated_policy_versions == {"application.launch": "1.0"}
    assert result.evaluated_policies == ("application.launch",)
    assert result.warnings == ()


def test_policy_effect_mapping():
    expected = {
        PolicyEffect.ALLOW: PolicyDecisionValueV2.ALLOW,
        PolicyEffect.DENY: PolicyDecisionValueV2.DENY,
        PolicyEffect.REQUIRE_CONFIRM: (PolicyDecisionValueV2.REQUIRE_CONSENT),
    }
    for legacy_effect, shadow_effect in expected.items():
        rules = PolicyRuleAdapter.adapt(
            _legacy(legacy_effect),
            version="1.0",
        )
        assert rules[0].decision is shadow_effect


def test_policy_difference_detection():
    shadow = _evaluate(effect=PolicyEffect.DENY).decision
    comparison = PolicyShadowComparison.compare(
        legacy=_legacy(PolicyEffect.ALLOW),
        shadow=shadow,
    )
    assert comparison.match is False
    assert "decision_changed:ALLOW->DENY" in comparison.differences


def test_missing_identity_warning():
    result = _evaluate(identity=False)
    assert "missing_identity" in result.warnings
    assert result.decision.policy_context is None


def test_missing_context_warning():
    result = _evaluate(context=False)
    assert "missing_context" in result.warnings
    comparison = PolicyShadowComparison.compare(
        legacy=_legacy(),
        shadow=result.decision,
    )
    assert "missing_context" in comparison.differences


def test_policy_never_changes_runtime():
    legacy = _legacy(PolicyEffect.REQUIRE_CONFIRM)
    before = deepcopy(legacy)
    rules = PolicyRuleAdapter.adapt(legacy, version="1.0")
    PolicyEngineV2Shadow(enabled=True).evaluate(
        intent=_intent(),
        plan=_plan(),
        identity=_identity(),
        policy_context=_policy_context(),
        application=_application(),
        rules=rules,
    )
    assert legacy == before


def test_policy_never_creates_grant():
    violations = _forbidden_calls({"AuthorizationGrantV1"})
    assert violations == []


def test_policy_no_tool_execution():
    violations = _forbidden_calls({"execute", "launch", "run", "popen", "start"})
    assert violations == []


def test_policy_metrics_are_aggregate_only():
    comparison = PolicyShadowComparison.compare(
        legacy=_legacy(PolicyEffect.ALLOW),
        shadow=_evaluate(effect=PolicyEffect.DENY).decision,
        legacy_policy_versions={"application.launch": "legacy-1"},
    )
    metrics = PolicyShadowMetrics()
    metrics.record(comparison)
    snapshot = metrics.snapshot()
    assert snapshot.policy_difference == 1
    assert snapshot.missing_policy_version == 1
    assert not hasattr(metrics, "users")
    assert not hasattr(metrics, "parameters")


def _forbidden_calls(names: set[str]):
    violations = []
    for path in Path("sentinel/policy_v2_shadow").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if called.casefold() in {name.casefold() for name in names}:
                violations.append((path.name, node.lineno, called))
    return violations
