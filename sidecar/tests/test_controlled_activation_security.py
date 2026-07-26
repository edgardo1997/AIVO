import ast
from pathlib import Path

from sentinel.controlled_runtime_activation import RuntimeRouteDecisionV1


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "controlled_runtime_activation"
FORBIDDEN_IMPORTS = {
    "subprocess",
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sentinel.core.planner",
    "sentinel.core.policy_engine",
    "sentinel.core.decision_engine",
    "sidecar.services.executor_service",
}
FORBIDDEN_CALLS = {
    "execute",
    "launch",
    "run",
    "popen",
    "system",
    "AuthorizationGrantV1",
}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in MODULE.glob("*.py")]


def test_no_forbidden_imports_or_calls() -> None:
    violations = []
    for path, tree in trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            if any(name.startswith(forbidden) for name in names for forbidden in FORBIDDEN_IMPORTS):
                violations.append(f"{path.name}:{node.lineno}:import")
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name in FORBIDDEN_CALLS:
                    if (
                        path.name == "canary_execution.py"
                        and name == "execute"
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Attribute)
                        and node.func.value.attr == "v2_executor"
                    ):
                        continue
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []


def test_decision_has_no_execution_capability() -> None:
    fields = set(RuntimeRouteDecisionV1.model_fields)
    assert RuntimeRouteDecisionV1.model_fields["authority"].default is False
    assert RuntimeRouteDecisionV1.model_fields["execution_requested"].default is False
    assert fields.isdisjoint({"runtime", "tool", "grant", "command", "arguments", "payload"})


def test_existing_runtime_does_not_import_activation() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.controlled_runtime_activation" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
