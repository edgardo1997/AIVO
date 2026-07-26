import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)

ROOT = Path(__file__).parents[2] / "sentinel" / "shadow_decision_orchestrator"


def test_shadow_package_has_no_productive_imports_or_execution_calls():
    forbidden_imports = {
        "multiprocessing",
        "socket",
        "subprocess",
        "threading",
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
    }
    forbidden_calls = {
        "Popen",
        "execute",
        "launch",
        "run",
        "startfile",
        "system",
    }
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        assert imports.isdisjoint(forbidden_imports), path.name
        assert calls.isdisjoint(forbidden_calls), path.name


def test_shadow_result_rejects_authority_and_execution():
    base = {
        "correlation_id": "decision:x",
        "evidence_hash": "a" * 64,
        "issuer_id": "issuer",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        ShadowDecisionResultV1.model_validate({**base, "authority": True})
    with pytest.raises(ValidationError):
        ShadowDecisionResultV1.model_validate({**base, "execution_requested": True})
