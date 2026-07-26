import ast
from pathlib import Path

from sentinel.execution_boundary import (
    EXECUTION_BOUNDARY_V2_ENABLED,
    ExecutionBoundaryControl,
)

ROOT = Path(__file__).parents[2]
MODULE = ROOT / "sentinel" / "execution_boundary"


def test_feature_flag_is_off_and_never_authoritative():
    assert EXECUTION_BOUNDARY_V2_ENABLED is False
    control = ExecutionBoundaryControl()
    assert control.enabled is False
    assert control.authority is False
    assert control.execution_requested is False


def test_no_productive_or_system_imports():
    forbidden = {
        "subprocess",
        "multiprocessing",
        "socket",
        "pathlib",
        "sentinel.core",
        "sentinel.modules",
        "sidecar",
    }
    for source_file in MODULE.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        assert not any(
            imported == item or imported.startswith(f"{item}.") for imported in imports for item in forbidden
        ), source_file


def test_no_execution_or_filesystem_capability():
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
        calls = {
            (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert calls.isdisjoint(forbidden_calls), source_file
