import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sentinel" / "operational_telemetry_hub"
FORBIDDEN_IMPORTS = {
    "executor",
    "tool_gateway",
    "orchestrator",
    "planner",
    "policy_engine",
    "decision_engine",
    "subprocess",
}
FORBIDDEN_CALLS = {"Popen", "system", "launch", "run"}


def test_hub_has_no_runtime_or_execution_dependencies():
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN_IMPORTS)
        assert calls.isdisjoint(FORBIDDEN_CALLS)
        source = path.read_text(encoding="utf-8")
        assert "authority=True" not in source
        assert "execution_requested=True" not in source


def test_sql_is_static_and_parameterized():
    source = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.glob("*.py"))
    assert 'f"SELECT' not in source
    assert 'f"INSERT' not in source
    assert 'f"UPDATE' not in source
    assert 'f"DELETE' not in source
    for sensitive in ("prompt", "command", "tool_arguments", "private_path"):
        assert sensitive not in source.lower()
