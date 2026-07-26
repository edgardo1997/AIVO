import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.runtime_equivalence_validation import (
    RuntimeEquivalenceResultV1,
    RuntimeEquivalenceSnapshotV1,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "runtime_equivalence_validation"
FORBIDDEN_IMPORTS = {
    "subprocess",
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sentinel.core.planner",
    "sentinel.core.policy_engine",
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


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in MODULE.glob("*.py")]


def safe_values():
    return {
        "runtime_type": "LEGACY",
        "intent_hash": "a" * 64,
        "execution_plan_hash": "b" * 64,
        "discovery_hash": "c" * 64,
        "policy_hash": "d" * 64,
        "authorization_hash": "e" * 64,
        "runtime_status": "COMPLETED",
        "execution_result": "SUCCESS",
        "tool_selection_hash": "f" * 64,
        "event_sequence": ("INTENT", "RESULT"),
        "execution_timing_ms": 10,
        "return_code": "OK",
    }


def test_snapshots_reject_sensitive_or_executable_payloads() -> None:
    for field in ("prompt", "user", "command", "arguments", "path", "payload"):
        with pytest.raises(ValidationError):
            RuntimeEquivalenceSnapshotV1(
                **safe_values(),
                **{field: "sensitive"},
            )


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


def test_result_has_no_authority_or_executable_fields() -> None:
    fields = set(RuntimeEquivalenceResultV1.model_fields)
    assert RuntimeEquivalenceResultV1.model_fields["authority"].default is False
    assert fields.isdisjoint({"tool", "grant", "command", "arguments", "payload", "executable"})


def test_existing_runtime_does_not_import_equivalence_layer() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.runtime_equivalence_validation" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
