import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.decision_shadow_validation import (
    DecisionShadowResultV1,
    LegacyDecisionSnapshot,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "decision_shadow_validation"
FORBIDDEN_IMPORTS = {
    "subprocess",
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sidecar.services.executor_service",
}
FORBIDDEN_CALLS = {
    "execute",
    "launch",
    "popen",
    "system",
    "AuthorizationGrantV1",
}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in MODULE.glob("*.py")]


def test_snapshot_rejects_sensitive_fields_and_codes() -> None:
    values = {
        "decision_type": "CONTROL",
        "decision_status": "ALLOW",
        "engine_version": "1.0",
        "intent_hash": "a" * 64,
        "plan_hash": "b" * 64,
        "policy_hash": "c" * 64,
        "discovery_hash": "d" * 64,
        "authorization_hash": "e" * 64,
    }
    with pytest.raises(ValidationError):
        LegacyDecisionSnapshot(**values, prompt="Abrir aplicación")
    with pytest.raises(ValidationError):
        LegacyDecisionSnapshot(**values, codes=("C:\\private",))


def test_no_forbidden_imports_or_calls() -> None:
    violations = []
    for path, tree in trees():
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


def test_result_cannot_hold_authority_or_execution_fields() -> None:
    fields = set(DecisionShadowResultV1.model_fields)
    assert DecisionShadowResultV1.model_fields["authority"].default is False
    assert fields.isdisjoint({"grant", "tool", "action", "executable", "command", "arguments"})


def test_productive_runtime_does_not_import_validation() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.decision_shadow_validation" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
