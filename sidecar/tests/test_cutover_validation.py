"""Fase 22 tests for isolated cutover evidence validation."""

import ast
import json
from dataclasses import asdict, replace
from pathlib import Path

from sentinel.canary_observation import CanaryHealthStatus
from sentinel.cutover_validation import (
    CUTOVER_VALIDATION_ENABLED,
    CutoverHistoricalMetrics,
    CutoverReadinessState,
    CutoverValidationEngine,
    CutoverValidationInput,
    DivergenceClassification,
)


REQUIRED_CONTRACTS = frozenset(
    {
        "IntentV2",
        "ExecutionPlanV2",
        "PolicyDecisionV2Strict",
        "AuthorizationGrantV1",
        "ApplicationDescriptorV1",
        "LaunchReceiptV1",
    }
)


def _evidence(**overrides) -> CutoverValidationInput:
    values = {
        "runtime_canary_metrics": {
            "matched_decisions": 997,
            "divergent_decisions": 3,
        },
        "observation_metrics": {
            "total_events": 1000,
            "average_latency": 15.0,
            "max_latency": 40.0,
        },
        "policy_shadow_metrics": {"match_rate": 99.7},
        "discovery_metrics": {"match_rate": 100.0},
        "authorization_metrics": {"match_rate": 100.0},
        "health_status": CanaryHealthStatus.HEALTHY,
        "available_contracts": REQUIRED_CONTRACTS,
    }
    values.update(overrides)
    return CutoverValidationInput(**values)


def test_readiness_ready():
    history = CutoverHistoricalMetrics()
    report = CutoverValidationEngine(
        enabled=True,
        history=history,
    ).validate(_evidence())

    assert report.overall_state is CutoverReadinessState.READY
    assert report.blockers == ()
    assert report.warnings == ()
    assert report.timestamp.utcoffset() is not None
    assert all(all(section.values()) for section in report.checklist.values())
    assert history.snapshot().validation_runs == 1
    assert "Requerir revisión independiente" in report.human_readable()


def test_readiness_warning():
    report = CutoverValidationEngine(enabled=True).validate(
        _evidence(
            health_status=CanaryHealthStatus.WARNING,
            divergences=("expected_require_confirm_mapping",),
        )
    )
    assert report.overall_state is CutoverReadinessState.WARNING
    assert report.blockers == ()
    assert "canary_health:warning" in report.warnings
    assert report.divergences[0].classification is (DivergenceClassification.EXPECTED)


def test_readiness_blocked():
    history = CutoverHistoricalMetrics()
    report = CutoverValidationEngine(
        enabled=True,
        history=history,
    ).validate(
        _evidence(
            identity_present=False,
            policy_context_present=False,
            no_critical_errors=False,
        )
    )
    assert report.overall_state is CutoverReadinessState.BLOCKED
    assert "missing_identity" in report.blockers
    assert "missing_policy_context" in report.blockers
    assert "critical_canary_errors" in report.blockers
    assert history.snapshot().blocked_runs == 1


def test_divergence_classified_correctly():
    report = CutoverValidationEngine(enabled=True).validate(
        _evidence(
            divergences=(
                "legacy_allow_v2_deny",
                "missing_policy_context",
            )
        )
    )
    assert report.overall_state is CutoverReadinessState.BLOCKED
    assert all(item.classification is DivergenceClassification.DATA_GAP for item in report.divergences)


def test_metrics_sanitized():
    history = CutoverHistoricalMetrics()
    evidence = _evidence(
        observation_metrics={
            "total_events": 10,
            "average_latency": 4.0,
            "max_latency": 8.0,
            "username": "private-user",
        }
    )
    report = CutoverValidationEngine(
        enabled=True,
        history=history,
    ).validate(evidence)
    snapshot = history.snapshot()
    assert snapshot.total_events == 10
    assert snapshot.policy_match_rate == 99.7
    assert not hasattr(snapshot, "users")
    assert "username" not in report.metrics_summary


def test_absence_of_sensitive_data():
    secret_values = (
        "private-user",
        "secret prompt",
        "powershell command",
        r"C:\private\path",
        "--token=secret",
    )
    report = CutoverValidationEngine(enabled=True).validate(
        _evidence(
            runtime_canary_metrics={
                "matched_decisions": 1,
                "divergent_decisions": 0,
                "prompt": secret_values[1],
                "command": secret_values[2],
            },
            observation_metrics={
                "total_events": 1,
                "average_latency": 1,
                "max_latency": 1,
                "path": secret_values[3],
                "arguments": secret_values[4],
                "user": secret_values[0],
            },
        )
    )
    serialized = json.dumps(asdict(report), default=str)
    assert all(value not in serialized for value in secret_values)


def test_missing_contracts_block_cutover():
    report = CutoverValidationEngine(enabled=True).validate(
        _evidence(available_contracts=REQUIRED_CONTRACTS - {"LaunchReceiptV1"})
    )
    assert report.overall_state is CutoverReadinessState.BLOCKED
    assert "missing_contract:LaunchReceiptV1" in report.blockers


def test_authorization_inconsistent_blocks():
    report = CutoverValidationEngine(enabled=True).validate(
        _evidence(
            authorization_consistent=False,
            replay_possible=True,
        )
    )
    assert report.overall_state is CutoverReadinessState.BLOCKED
    assert "authorization_inconsistent" in report.blockers
    assert "replay_possible" in report.blockers


def test_cutover_validation_ast_boundaries():
    forbidden_imports = {
        "sentinel.core.planner",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.tool_gateway",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
        "subprocess",
    }
    forbidden_calls = {
        "execute",
        "launch",
        "run",
        "popen",
        "system",
        "AuthorizationGrantV1",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if any(module == item or module.startswith(f"{item}.") for item in forbidden_imports):
                    violations.append((path.name, node.lineno, module))
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if called.casefold() in {item.casefold() for item in forbidden_calls}:
                    violations.append((path.name, node.lineno, called))
    assert violations == []


def test_runtime_remains_unchanged():
    evidence = _evidence()
    before = replace(evidence)
    CutoverValidationEngine(enabled=True).validate(evidence)
    assert evidence == before

    legacy_paths = (
        ROOT / "sentinel/core/planner.py",
        ROOT / "sentinel/core/policy_engine.py",
        ROOT / "sentinel/core/decision_engine.py",
        ROOT / "sentinel/core/tool_gateway.py",
        ROOT / "sentinel/core/orchestrator.py",
        ROOT / "sidecar/services/executor_service.py",
    )
    forbidden_runtime_imports = (
        "sentinel.cutover_validation",
        "sentinel.runtime_canary",
        "sentinel.authorization_canary",
        "sentinel.policy_v2_shadow",
        "sentinel.application_discovery_v2",
    )
    for path in legacy_paths:
        source = path.read_text(encoding="utf-8")
        assert all(forbidden not in source for forbidden in forbidden_runtime_imports)


def test_validation_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CUTOVER_VALIDATION_ENABLED", raising=False)
    assert CUTOVER_VALIDATION_ENABLED is False
    engine = CutoverValidationEngine()
    report = engine.validate(_evidence())
    assert engine.enabled is False
    assert report.overall_state is CutoverReadinessState.BLOCKED
    assert report.blockers == ("cutover_validation_disabled",)


def _trees():
    for path in (ROOT / "sentinel/cutover_validation").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


ROOT = Path(__file__).resolve().parents[2]
