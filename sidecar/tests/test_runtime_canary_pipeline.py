"""Fase 21 characterization tests for the parallel runtime canary."""

import ast
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentinel.application_discovery_v2 import (
    ApplicationResolverV2,
    ResolverRegistry,
    Win32Resolver,
)
from sentinel.contracts import IdentityContextV1, PolicyContextV1
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.runtime_canary import (
    RUNTIME_CANARY_ENABLED,
    RuntimeCanaryDispatcher,
    RuntimeCanaryInput,
    RuntimeCanaryMetrics,
    RuntimeCanaryPipeline,
    runtime_canary_enabled,
)
from sentinel.shadow import CapturedRuntimeEvent


def _intent() -> Intent:
    return Intent(
        action="execute",
        target="executor.launch",
        parameters={
            "application_id": "win32.notepad",
            "private_path": r"C:\Users\edgar\secret.txt",
        },
        confidence=0.96,
        raw_input="Abrir Notepad secret prompt",
    )


def _plan() -> Plan:
    return Plan(
        intent=_intent(),
        description="Launch resolved application",
        risk_score=0.4,
        steps=[
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"application_id": "win32.notepad"},
                estimated_impact="medium",
            )
        ],
    )


def _application(*, source: str = "win32") -> AppProfile:
    return AppProfile(
        app_id="win32.notepad",
        name="Notepad",
        executable=r"C:\Windows\System32\notepad.exe",
        category="utility",
        capabilities=["text.edit"],
        required_permissions=["executor.launch"],
        source=source,
        confidence=0.99,
        discovered_at="2026-07-24T12:00:00Z",
        expires_at="2026-07-24T12:05:00Z",
    )


def _identity() -> IdentityContextV1:
    return IdentityContextV1.create(
        user_id="private-user",
        session_id="private-session",
        roles=("user",),
        authentication_method="local",
        created_at=datetime.now(timezone.utc),
    )


def _policy_context() -> PolicyContextV1:
    return PolicyContextV1(
        schema_version="1.0",
        user_id="private-user",
        identity_hash=PolicyContextV1.calculate_identity_hash("private-user"),
        plan_id="plan_notepad",
        intent_id="intent_notepad",
        risk_level="medium",
        evaluated_policies=("application.launch",),
        evaluated_policy_versions={"application.launch": "1.0"},
        evaluated_at=datetime.now(timezone.utc),
        policy_engine_version="shadow-2.0",
        decision_origin="runtime_canary",
    )


def _snapshot(*, source: str = "win32") -> RuntimeCanaryInput:
    return RuntimeCanaryInput(
        intent=_intent(),
        plan=_plan(),
        application=_application(source=source),
        policy=PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="application.launch",
            reason="Legacy allow",
            context={"secret": "must-not-leak"},
        ),
        identity=_identity(),
        policy_context=_policy_context(),
        discovery_request={"action": "lookup", "name": "Notepad"},
        intent_id="intent_notepad",
        plan_id="plan_notepad",
    )


def _resolver() -> ApplicationResolverV2:
    return ApplicationResolverV2(
        ResolverRegistry(
            (
                Win32Resolver(
                    (
                        {
                            "application_id": "win32.notepad",
                            "display_name": "Notepad",
                            "aliases": ("Bloc de notas",),
                            "launch_type": "executable",
                            "launch_target": (r"C:\Windows\System32\notepad.exe"),
                            "executable": (r"C:\Windows\System32\notepad.exe"),
                            "confidence": 0.99,
                        },
                    )
                ),
            )
        )
    )


def _pipeline(
    *,
    enabled: bool | None = True,
    metrics: RuntimeCanaryMetrics | None = None,
) -> RuntimeCanaryPipeline:
    return RuntimeCanaryPipeline(
        application_resolver=_resolver(),
        enabled=enabled,
        metrics=metrics,
    )


def test_pipeline_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RUNTIME_CANARY_ENABLED", raising=False)
    assert RUNTIME_CANARY_ENABLED is False
    assert runtime_canary_enabled() is False
    pipeline = _pipeline(enabled=None)
    result = pipeline.observe(_snapshot())
    assert pipeline.enabled is False
    assert result.runtime_id == "runtime_canary_disabled"
    assert result.authorization_result["authority"] is False


def test_runtime_canary_shadow_execution_only():
    result = _pipeline().observe(_snapshot())
    assert result.legacy_summary["observed"] is True
    assert result.planner_result["status"] == "SUCCESS"
    assert result.discovery_result["status"] == "RESOLVED"
    assert result.policy_result["status"] == "EVALUATED"
    assert result.authorization_result == {
        "status": "VALIDATED_SIMULATION",
        "authority": False,
        "single_use": True,
    }


def test_runtime_canary_comparison_correct():
    result = _pipeline().observe(_snapshot())
    comparison = result.comparison_result
    assert comparison["planner_match"] is True
    assert comparison["discovery_match"] is True
    assert comparison["policy_match"] is True
    assert comparison["authorization_match"] is True
    assert comparison["status"] == "MATCH"


def test_runtime_canary_detects_divergence():
    result = _pipeline().observe(_snapshot(source="legacy_registry"))
    assert result.comparison_result["status"] == "DIVERGENCE"
    assert result.comparison_result["discovery_match"] is False
    assert "provider_difference" in result.comparison_result["differences"]


def test_runtime_canary_metrics_are_aggregate():
    metrics = RuntimeCanaryMetrics()
    pipeline = _pipeline(metrics=metrics)
    pipeline.observe(_snapshot())
    pipeline.observe(_snapshot(source="legacy_registry"))
    snapshot = metrics.snapshot()
    assert snapshot.planner_matches == 2
    assert snapshot.discovery_matches == 1
    assert snapshot.policy_matches == 2
    assert snapshot.authorization_matches == 2
    assert snapshot.average_runtime_ms > 0
    assert snapshot.maximum_runtime_ms >= snapshot.average_runtime_ms
    assert not hasattr(metrics, "payloads")
    assert not hasattr(metrics, "users")


def test_runtime_canary_result_has_no_sensitive_data():
    result = _pipeline().observe(_snapshot())
    serialized = json.dumps(asdict(result), default=str)
    forbidden = (
        "private-user",
        "private-session",
        "secret prompt",
        r"C:\Users\edgar\secret.txt",
        "must-not-leak",
        "executor.launch",
        "win32.notepad",
        r"C:\Windows\System32\notepad.exe",
    )
    assert all(value not in serialized for value in forbidden)


def test_runtime_canary_preserves_legacy_objects_and_uses_copy():
    snapshot = _snapshot()
    before = deepcopy(snapshot)
    result = _pipeline().observe(snapshot)
    assert snapshot == before
    assert result.legacy_summary["intent_type"] == "Intent"
    assert result.legacy_summary["plan_type"] == "Plan"


def test_runtime_canary_has_no_authority():
    result = _pipeline().observe(_snapshot())
    assert result.authorization_result["authority"] is False
    serialized = json.dumps(asdict(result), default=str)
    assert "authorization_id" not in serialized
    assert "grant_hash" not in serialized
    assert "nonce" not in serialized


def test_runtime_canary_feature_flag(monkeypatch):
    monkeypatch.setenv("RUNTIME_CANARY_ENABLED", "true")
    pipeline = _pipeline(enabled=None)
    assert pipeline.enabled is True
    assert pipeline.observe(_snapshot()).legacy_summary["observed"] is True


@pytest.mark.parametrize(
    "event_name",
    [
        "intent_received",
        "plan_created",
        "policy_evaluated",
        "consent_requested",
        "tool_requested",
        "execution_completed",
        "execution_failed",
    ],
)
def test_runtime_canary_dispatches_legacy_events(event_name):
    event = CapturedRuntimeEvent(
        event_name=event_name,
        source_event_type="legacy.event",
        timestamp=datetime.now(timezone.utc),
        component="legacy",
        status="observed",
        tool_id="",
        correlation_ids={"request_id": "hashed"},
    )
    dispatched = RuntimeCanaryDispatcher(_pipeline()).dispatch(
        event,
        _snapshot(),
    )
    assert dispatched.event_name == event_name
    assert dispatched.result.authorization_result["authority"] is False


def test_runtime_canary_ast_boundaries():
    forbidden_imports = {
        "sentinel.core.executor",
        "sentinel.core.tool_gateway",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.planner",
        "sentinel.core.orchestrator",
        "subprocess",
    }
    forbidden_calls = {
        "execute",
        "launch",
        "run",
        "popen",
        "system",
        "start-process",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for module in modules
                for forbidden in forbidden_imports
            ):
                violations.append((path.name, node.lineno, "import"))
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if called.casefold() in forbidden_calls:
                    violations.append((path.name, node.lineno, called))
    assert violations == []


def _trees():
    for path in Path("sentinel/runtime_canary").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))
