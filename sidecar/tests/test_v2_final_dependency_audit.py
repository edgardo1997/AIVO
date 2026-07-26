import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sentinel"
PACKAGES = tuple(
    path
    for path in ROOT.iterdir()
    if path.is_dir() and path.name not in {"core", "tools", "policies", "modules", "__pycache__"}
)
FORBIDDEN = {
    "sentinel.core.tool_gateway",
    "sentinel.core.orchestrator",
    "sentinel.core.planner",
    "sidecar.services.executor_service",
    "subprocess",
}


def _import_modules(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_dependency_audit_records_all_planner_legacy_imports():
    findings = []
    for package in PACKAGES:
        for path in package.glob("*.py"):
            imports = _import_modules(ast.parse(path.read_text(encoding="utf-8")))
            for imported in imports.intersection({"sentinel.core.planner"}):
                findings.append((path.relative_to(ROOT).as_posix(), imported))
    assert sorted(findings) == [
        ("adapters/plan_adapter.py", "sentinel.core.planner"),
        ("shadow/observer.py", "sentinel.core.planner"),
        ("shadow/runtime_adapter.py", "sentinel.core.planner"),
    ]


def test_dependency_audit_records_subprocess_boundary_violation():
    findings = []
    for package in PACKAGES:
        for path in package.glob("*.py"):
            imports = _import_modules(ast.parse(path.read_text(encoding="utf-8")))
            if "subprocess" in imports:
                findings.append(path.relative_to(ROOT).as_posix())
    assert findings == [
        "limited_execution_v2/backend.py",
        "local_model/runtime.py",
    ]


def test_no_executor_gateway_or_orchestrator_dependency_exists():
    for package in PACKAGES:
        for path in package.glob("*.py"):
            imports = _import_modules(ast.parse(path.read_text(encoding="utf-8")))
            assert "sentinel.core.tool_gateway" not in imports
            assert "sentinel.core.orchestrator" not in imports
            assert "sidecar.services.executor_service" not in imports
