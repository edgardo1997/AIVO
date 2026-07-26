import ast
from pathlib import Path

from sentinel.runtime_trial import RuntimeTrialResult, RuntimeTrialV1


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "runtime_trial"
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


def test_no_forbidden_imports() -> None:
    violations = []
    for path, tree in trees():
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if any(name.startswith(value) for value in FORBIDDEN_IMPORTS):
                    violations.append(f"{path.name}:{node.lineno}:{name}")
    assert violations == []


def test_no_real_execution_calls_or_grants() -> None:
    violations = []
    for path, tree in trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
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


def test_trial_models_have_no_authority_or_executable_fields() -> None:
    for model in (RuntimeTrialV1, RuntimeTrialResult):
        fields = set(model.model_fields)
        assert model.model_fields["authority"].default is False
        assert fields.isdisjoint({"grant", "tool", "executable", "command", "arguments"})


def test_productive_runtime_does_not_import_trial() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.runtime_trial" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
