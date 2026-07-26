import ast
from pathlib import Path
from typing import get_args

from sentinel.contracts import (
    ToolGatewayDecisionResultV1,
    ToolGatewayDecisionValueV1,
)

ROOT = Path(__file__).parents[2] / "sentinel" / "tool_gateway"


def test_gateway_package_has_no_productive_imports_or_calls():
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
        "exec",
        "execute",
        "launch",
        "open",
        "run",
        "startfile",
        "system",
        "write_bytes",
        "write_text",
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


def test_gateway_decision_contract_is_always_non_authoritative():
    assert get_args(ToolGatewayDecisionResultV1.model_fields["authority"].annotation) == (False,)
    assert get_args(ToolGatewayDecisionResultV1.model_fields["execution_requested"].annotation) == (False,)


def test_gateway_vocabulary_has_no_execution_semantics():
    forbidden = {"EXECUTE", "AUTHORIZED", "ACTIVE", "APPROVED", "CUTOVER"}
    assert {item.value for item in ToolGatewayDecisionValueV1}.isdisjoint(forbidden)
