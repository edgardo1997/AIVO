import ast
from pathlib import Path

from sentinel.shadow_runtime_real import PassiveShadowRuntimeObserver

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "shadow_runtime_real"


def _trees():
    return [ast.parse(path.read_text(encoding="utf-8")) for path in MODULE.glob("*.py")]


def test_real_shadow_has_no_productive_runtime_dependencies():
    banned = {
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
        "subprocess",
        "multiprocessing",
        "socket",
    }
    for tree in _trees():
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        assert not any(imported == name or imported.startswith(f"{name}.") for imported in imports for name in banned)


def test_real_shadow_has_no_execution_surface():
    banned_calls = {"execute", "launch", "run", "Popen", "system"}
    for tree in _trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in banned_calls
    assert PassiveShadowRuntimeObserver.authority is False
    assert PassiveShadowRuntimeObserver.execution_requested is False
    assert not hasattr(PassiveShadowRuntimeObserver, "execute")
    assert not hasattr(PassiveShadowRuntimeObserver, "launch")
