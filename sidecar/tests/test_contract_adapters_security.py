import ast
from pathlib import Path

ADAPTERS_ROOT = Path(__file__).parents[2] / "sentinel" / "contract_adapters"
FORBIDDEN = {
    "executor",
    "tool_gateway",
    "orchestrator",
    "planner",
    "policy_engine",
    "decision_engine",
    "subprocess",
}
FORBIDDEN_CALLS = {"execute", "launch", "run", "Popen", "system"}


def test_contract_adapters_have_no_productive_dependencies_or_calls():
    for path in ADAPTERS_ROOT.glob("*.py"):
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
        assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN)
        assert calls.isdisjoint(FORBIDDEN_CALLS)


def test_adapters_do_not_import_existing_v2_modules():
    for path in ADAPTERS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "canary_environment" not in source
        assert "runtime_trial" not in source
        assert "controlled_runtime_activation" not in source
