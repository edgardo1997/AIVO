import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sentinel" / "evidence_integrity"
FORBIDDEN_IMPORTS = {
    "executor",
    "tool_gateway",
    "orchestrator",
    "planner",
    "policy_engine",
    "decision_engine",
    "subprocess",
}
FORBIDDEN_CALLS = {"Popen", "system", "launch", "execute", "run"}


def test_integrity_layer_has_no_runtime_or_execution_capability():
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


def test_private_keys_are_not_contract_fields():
    source = (Path(__file__).parents[2] / "sentinel" / "contracts" / "evidence.py").read_text(encoding="utf-8")
    assert "private_key" not in source
    assert "prompt" not in source
    assert "command" not in source
