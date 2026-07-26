import ast
from pathlib import Path
from typing import get_args

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationScopeV1,
    AuthorizationStatusV1,
)

ROOT = Path(__file__).parents[2] / "sentinel" / "authorization_manager"


def test_authorization_package_has_no_productive_imports_or_calls():
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


def test_grant_contract_is_always_non_authoritative():
    assert get_args(AuthorizationGrantV1.model_fields["authority"].annotation) == (False,)
    assert get_args(AuthorizationGrantV1.model_fields["execution_requested"].annotation) == (False,)


def test_scope_and_status_vocabularies_are_strictly_limited():
    forbidden = {
        "FULL_ACCESS",
        "ADMIN",
        "ROOT",
        "AUTO_EXECUTE",
        "UNLIMITED",
        "SYSTEM_CONTROL",
        "FILE_DELETE",
        "PROCESS_KILL",
        "INSTALL",
    }
    assert {item.value for item in AuthorizationScopeV1}.isdisjoint(forbidden)
    assert {item.value for item in AuthorizationStatusV1}.isdisjoint(forbidden)
