"""Static guards against accidental pre-cutover runtime integration."""

import ast
from pathlib import Path

from sentinel.contracts import (
    ApplicationDescriptorV1,
    AuthorizationGrantV1,
)
from sentinel.shadow import ShadowMigrationObserver


ROOT = Path(__file__).resolve().parents[2]


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    return imported


def test_shadow_observer_does_not_import_orchestrator():
    imports = _imports(ROOT / "sentinel" / "shadow" / "observer.py")
    assert not any("orchestrator" in name for name in imports)


def test_contracts_do_not_import_runtime_components():
    banned = {
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
        "sidecar.modules.executor",
    }
    for path in (ROOT / "sentinel" / "contracts").glob("*.py"):
        for imported in _imports(path):
            assert not any(imported == name or imported.startswith(f"{name}.") for name in banned), (
                f"{path.name} imports runtime component {imported}"
            )


def test_adapters_do_not_import_or_execute_tools():
    banned = {"tool_gateway", "executor_service", "orchestrator"}
    for path in (ROOT / "sentinel" / "adapters").glob("*.py"):
        imports = _imports(path)
        assert not any(name in imported for name in banned for imported in imports)


def test_contracts_and_shadow_have_no_execution_authority():
    for value in (
        ApplicationDescriptorV1,
        AuthorizationGrantV1,
        ShadowMigrationObserver,
    ):
        assert not hasattr(value, "execute")
        assert not hasattr(value, "launch")
        assert not hasattr(value, "authorize")
