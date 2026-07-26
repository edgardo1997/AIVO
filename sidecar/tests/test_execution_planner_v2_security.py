import ast
from pathlib import Path

from sentinel.execution_planner import (
    EXECUTION_PLANNER_V2_ENABLED,
    ExecutionPlannerControl,
)

ROOT = Path(__file__).parents[2]
MODULE = ROOT / "sentinel" / "execution_planner"


def test_feature_flag_off_and_no_authority():
    assert EXECUTION_PLANNER_V2_ENABLED is False
    control = ExecutionPlannerControl()
    assert control.enabled is False
    assert control.authority is False
    assert control.execution_requested is False


def test_no_productive_imports_or_execution_calls():
    forbidden_imports = {
        "subprocess",
        "multiprocessing",
        "socket",
        "pathlib",
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
