import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.final_control_plane_readiness import (
    ConsolidatedSignalsV1,
    FinalReadinessDecision,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "final_control_plane_readiness"
FORBIDDEN_IMPORTS = {
    "subprocess",
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sentinel.core.planner",
    "sentinel.core.policy_engine",
    "sentinel.core.decision_engine",
    "sidecar.services.executor_service",
}
FORBIDDEN_CALLS = {
    "execute",
    "launch",
    "run",
    "popen",
    "system",
    "AuthorizationGrantV1",
}


def valid_signals():
    return {
        "authority_readiness_status": "READY_FOR_REVIEW",
        "safety_healthy": True,
        "recovery_status": "RECOVERY_OK",
        "state_corrupted": False,
        "evidence_available": True,
        "evidence_integrity_valid": True,
        "critical_data_loss": 0,
        "runtime_equivalence_rate": 1,
        "critical_divergences": 0,
        "operational_health": "HEALTHY",
        "trust_confidence": "HIGH_CONFIDENCE",
        "trust_score": 80,
        "trust_recommendation": "EXTEND_CANARY",
        "controlled_activation_enabled": False,
        "v2_canary_enabled": False,
    }


def test_signals_reject_sensitive_fields() -> None:
    for field in (
        "prompt",
        "command",
        "path",
        "arguments",
        "user",
        "payload",
    ):
        with pytest.raises(ValidationError):
            ConsolidatedSignalsV1(
                **valid_signals(),
                **{field: "sensitive"},
            )


def test_decision_is_non_authoritative_and_non_executing() -> None:
    fields = set(FinalReadinessDecision.model_fields)
    assert FinalReadinessDecision.model_fields["authority"].default is False
    assert FinalReadinessDecision.model_fields["execution_requested"].default is False
    assert fields.isdisjoint({"tool", "grant", "command", "arguments", "payload", "runtime"})


def test_no_forbidden_imports_or_calls() -> None:
    violations = []
    for path in MODULE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            if any(name.startswith(forbidden) for name in names for forbidden in FORBIDDEN_IMPORTS):
                violations.append(f"{path.name}:{node.lineno}:import")
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []


def test_existing_runtime_does_not_import_final_readiness() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.final_control_plane_readiness" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
