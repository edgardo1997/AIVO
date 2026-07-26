import ast
from pathlib import Path

from sentinel.v2_authority_readiness import AuthorityReadinessResultV1


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "v2_authority_readiness"
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
    "popen",
    "system",
    "AuthorizationGrantV1",
}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in MODULE.glob("*.py")]


def test_no_forbidden_imports_or_execution_calls() -> None:
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
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []


def test_result_has_no_authority_or_migration_action() -> None:
    fields = set(AuthorityReadinessResultV1.model_fields)
    assert AuthorityReadinessResultV1.model_fields["authority"].default is False
    assert fields.isdisjoint({"grant", "tool", "action", "executable", "command", "arguments"})


def test_productive_runtime_does_not_import_readiness() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.v2_authority_readiness" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
