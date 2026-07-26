import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.limited_execution_v2 import LimitedExecutionRequestV1

MODULE = Path("sentinel/limited_execution_v2")


def test_request_contract_rejects_dangerous_operations_and_payloads():
    base = {
        "request_id": "execute:safe",
        "correlation_id": "correlation:safe",
        "evidence_hash": "a" * 64,
        "authorization_id": "authorization:safe",
        "plan_id": "plan:safe",
        "step_id": "step:safe",
        "tool_id": "sentinel.system.information",
        "params_hash": "b" * 64,
        "operation": "SYSTEM_INFORMATION",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    for operation in (
        "DELETE_FILE",
        "INSTALL_APPLICATION",
        "STOP_PROCESS",
        "EXECUTE_COMMAND",
    ):
        with pytest.raises(ValidationError):
            LimitedExecutionRequestV1.model_validate({**base, "operation": operation})
    for field in ("command", "arguments", "path", "script", "payload"):
        with pytest.raises(ValidationError):
            LimitedExecutionRequestV1.model_validate({**base, field: "forbidden"})


def test_backend_has_no_shell_or_free_command_execution():
    backend = (MODULE / "backend.py").read_text(encoding="utf-8")
    tree = ast.parse(backend)
    assert "shell=True" not in backend.replace(" ", "")
    assert "os.system" not in backend
    assert "PowerShell" not in backend
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "Popen":
                assert node.args
                assert isinstance(node.args[0], ast.List)
                assert len(node.args[0].elts) == 1


def test_no_legacy_runtime_or_gateway_imports():
    forbidden = {
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
    }
    for source in MODULE.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert imports.isdisjoint(forbidden)
