import ast
from pathlib import Path

from sentinel.runtime_isolation import (
    RUNTIME_ISOLATION_V2_ENABLED,
    RuntimeIsolationControl,
)

ROOT = Path(__file__).parents[2]
MODULE = ROOT / "sentinel" / "runtime_isolation"


def test_flag_off_and_no_authority():
    assert RUNTIME_ISOLATION_V2_ENABLED is False
    control = RuntimeIsolationControl()
    assert control.enabled is False
    assert control.authority is False
    assert control.execution_requested is False


def test_no_os_productive_execution_or_filesystem_capabilities():
    forbidden_imports = {
        "subprocess",
        "multiprocessing",
        "socket",
        "pathlib",
        "os",
        "sentinel.core",
        "sentinel.modules",
        "sidecar",
    }
    forbidden_calls = {
        "execute",
        "exec",
        "launch",
        "run",
        "Popen",
        "system",
        "open",
        "write_text",
        "write_bytes",
    }
    for source_file in MODULE.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        assert not any(
            imported == item or imported.startswith(f"{item}.") for imported in imports for item in forbidden_imports
        ), source_file
        calls = {
            (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert calls.isdisjoint(forbidden_calls), source_file
