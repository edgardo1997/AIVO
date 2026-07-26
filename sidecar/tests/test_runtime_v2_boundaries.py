import ast
from datetime import datetime, timezone
from pathlib import Path

from sentinel.runtime_v2_controlled import RuntimeShadowResultV1


def test_runtime_v2_controlled_has_no_forbidden_imports_or_calls():
    forbidden_imports = {
        "sentinel.core.planner",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.tool_gateway",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
        "subprocess",
    }
    forbidden_calls = {
        "execute",
        "launch",
        "run",
        "popen",
        "system",
        "AuthorizationGrantV1",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if any(module == item or module.startswith(f"{item}.") for item in forbidden_imports):
                    violations.append((path.name, node.lineno, module))
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if called.casefold() in {item.casefold() for item in forbidden_calls}:
                    violations.append((path.name, node.lineno, called))
    assert violations == []


def test_all_runtime_shadow_results_have_no_authority():
    result = RuntimeShadowResultV1(
        schema_version="1.0",
        correlation_id="boundary-test",
        timestamp=datetime.now(timezone.utc),
        legacy_status="COMPLETED",
        shadow_status="OBSERVED",
        authority=False,
    )
    assert result.authority is False
    assert not hasattr(result, "plan")
    assert not hasattr(result, "grant")
    assert not hasattr(result, "tool")


def test_legacy_runtime_has_no_controlled_v2_import():
    paths = (
        ROOT / "sentinel/core/planner.py",
        ROOT / "sentinel/core/policy_engine.py",
        ROOT / "sentinel/core/decision_engine.py",
        ROOT / "sentinel/core/tool_gateway.py",
        ROOT / "sentinel/core/orchestrator.py",
        ROOT / "sidecar/services/executor_service.py",
    )
    assert all("sentinel.runtime_v2_controlled" not in path.read_text(encoding="utf-8") for path in paths)


def _trees():
    for path in (ROOT / "sentinel/runtime_v2_controlled").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


ROOT = Path(__file__).resolve().parents[2]
