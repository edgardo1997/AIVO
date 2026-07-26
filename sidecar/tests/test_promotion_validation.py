"""Fase 23 tests for evidence-only shadow-to-canary promotion."""

import ast
import json
from dataclasses import asdict, replace
from pathlib import Path

from sentinel.promotion_validation import (
    PROMOTION_VALIDATION_ENABLED,
    BoundaryGate,
    ContractGate,
    PromotionEvidence,
    PromotionMetrics,
    PromotionPlanV1,
    PromotionValidationEngine,
    PromotionValidationState,
    SecurityGate,
    ShadowGate,
    StabilityGate,
    promotion_validation_enabled,
)


CONTRACTS = frozenset(
    {
        "IntentV2",
        "ExecutionPlanV2",
        "PolicyDecisionV2Strict",
        "AuthorizationGrantV1",
        "ApplicationDescriptorV1",
    }
)


def _plan() -> PromotionPlanV1:
    return PromotionPlanV1(
        schema_version="1.0",
        candidate_component="application_discovery_v2",
        current_version="shadow-1.0",
        target_version="canary-1.0",
        required_dependencies=("runtime_canary", "cutover_validation"),
        known_risks=("provider_ambiguity",),
        approval_requirements=("security_review", "release_owner"),
        rollback_plan=(
            "disable_feature_flag",
            "continue_legacy_discovery",
        ),
    )


def _evidence(**overrides) -> PromotionEvidence:
    values = {
        "available_contracts": CONTRACTS,
        "contract_versions": {
            "IntentV2": "2.0",
            "ExecutionPlanV2": "2.0",
            "PolicyDecisionV2Strict": "2.0",
            "AuthorizationGrantV1": "1.0",
            "ApplicationDescriptorV1": "1.0",
        },
        "compatibility_validated": True,
        "information_loss_detected": False,
        "available_dependencies": frozenset({"runtime_canary", "cutover_validation"}),
        "shadow_observations": 10_000,
        "minimum_shadow_observations": 1_000,
        "divergences_total": 2,
        "divergences_classified": True,
        "critical_errors": 0,
        "identity_present": True,
        "policy_context_valid": True,
        "authorization_canary_valid": True,
        "replay_detected": False,
        "stability_status": "HEALTHY",
        "error_rate": 0.001,
        "error_rate_limit": 0.01,
        "max_latency_ms": 100.0,
        "latency_limit_ms": 250.0,
        "boundary_clean": True,
        "approvals": frozenset(),
    }
    values.update(overrides)
    return PromotionEvidence(**values)


def test_promotion_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PROMOTION_VALIDATION_ENABLED", raising=False)
    assert PROMOTION_VALIDATION_ENABLED is False
    assert promotion_validation_enabled() is False
    engine = PromotionValidationEngine()
    report = engine.validate(_plan(), _evidence())
    assert engine.enabled is False
    assert report.state is PromotionValidationState.BLOCKED
    assert report.blocked_gates == ("promotion_validation_disabled",)


def test_contract_gate():
    assert ContractGate().evaluate(_plan(), _evidence()).passed is True
    failed = ContractGate().evaluate(
        _plan(),
        _evidence(
            available_contracts=CONTRACTS - {"AuthorizationGrantV1"},
            information_loss_detected=True,
        ),
    )
    assert failed.passed is False
    assert "missing_contract:AuthorizationGrantV1" in failed.reasons
    assert "information_loss_detected" in failed.reasons


def test_shadow_gate():
    assert ShadowGate().evaluate(_plan(), _evidence()).passed is True
    failed = ShadowGate().evaluate(
        _plan(),
        _evidence(
            shadow_observations=5,
            divergences_classified=False,
            critical_errors=1,
        ),
    )
    assert failed.passed is False
    assert failed.reasons == (
        "insufficient_shadow_observations",
        "unclassified_divergences",
        "critical_shadow_errors",
    )


def test_security_gate():
    assert SecurityGate().evaluate(_plan(), _evidence()).passed is True
    failed = SecurityGate().evaluate(
        _plan(),
        _evidence(
            identity_present=False,
            policy_context_valid=False,
            authorization_canary_valid=False,
            replay_detected=True,
        ),
    )
    assert failed.passed is False
    assert "missing_identity" in failed.reasons
    assert "replay_detected" in failed.reasons


def test_stability_gate():
    assert StabilityGate().evaluate(_plan(), _evidence()).passed is True
    failed = StabilityGate().evaluate(
        _plan(),
        _evidence(
            stability_status="UNSTABLE",
            error_rate=0.1,
            max_latency_ms=500.0,
        ),
    )
    assert failed.passed is False
    assert failed.reasons == (
        "stability_not_healthy",
        "error_rate_above_limit",
        "latency_above_limit",
    )


def test_boundary_gate():
    result = BoundaryGate().evaluate(_plan(), _evidence())
    assert result.passed is True
    failed = BoundaryGate().evaluate(
        _plan(),
        _evidence(boundary_clean=False),
    )
    assert failed.passed is False
    assert failed.reasons == ("external_boundary_check_failed",)


def test_blocked_without_requirements():
    report = PromotionValidationEngine(enabled=True).validate(
        _plan(),
        _evidence(
            available_contracts=frozenset(),
            identity_present=False,
            stability_status="FAILED",
        ),
    )
    assert report.state is PromotionValidationState.BLOCKED
    assert {"contract", "security", "stability"} <= set(report.blocked_gates)
    assert "No promover a canary." in report.recommendations


def test_ready_when_all_requirements_pass():
    metrics = PromotionMetrics()
    plan = _plan()
    evidence = _evidence()
    before_plan = plan.model_copy(deep=True)
    before_evidence = replace(evidence)
    report = PromotionValidationEngine(
        enabled=True,
        metrics=metrics,
    ).validate(plan, evidence)

    assert report.state is PromotionValidationState.READY_FOR_CANARY
    assert report.blocked_gates == ()
    assert set(report.approved_gates) == {
        "contract",
        "shadow",
        "security",
        "stability",
        "boundary",
    }
    assert report.timestamp.utcoffset() is not None
    assert plan == before_plan
    assert evidence == before_evidence
    snapshot = metrics.snapshot()
    assert snapshot.validation_count == 1
    assert snapshot.gates_passed == 5
    assert snapshot.divergences == 2
    assert "considerar una promoción futura" in report.human_readable()


def test_documentary_approval_never_activates_canary():
    report = PromotionValidationEngine(enabled=True).validate(
        _plan(),
        _evidence(approvals=frozenset({"security_review", "release_owner"})),
    )
    assert report.state is PromotionValidationState.CANARY_APPROVED
    assert "requiere una fase separada" in report.recommendations[1]


def test_no_runtime_authority():
    legacy_paths = (
        ROOT / "sentinel/core/planner.py",
        ROOT / "sentinel/core/policy_engine.py",
        ROOT / "sentinel/core/decision_engine.py",
        ROOT / "sentinel/core/tool_gateway.py",
        ROOT / "sentinel/core/orchestrator.py",
        ROOT / "sidecar/services/executor_service.py",
    )
    assert all("sentinel.promotion_validation" not in path.read_text(encoding="utf-8") for path in legacy_paths)
    report = PromotionValidationEngine(enabled=True).validate(
        _plan(),
        _evidence(
            contract_versions={
                **_evidence().contract_versions,
                "user": "private-user",
                "IntentV2": "secret prompt with spaces",
            }
        ),
    )
    serialized = json.dumps(asdict(report), default=str)
    assert "private-user" not in serialized
    assert "secret prompt" not in serialized


def test_no_execution_capability():
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


def _trees():
    for path in (ROOT / "sentinel/promotion_validation").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


ROOT = Path(__file__).resolve().parents[2]
