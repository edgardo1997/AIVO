"""AST boundaries preventing shadow observation from gaining authority."""

import ast
from pathlib import Path


SHADOW_DIR = Path("sentinel/shadow")
FORBIDDEN_IMPORTS = {
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sidecar.services.executor_service",
    "sidecar.modules.executor",
}


def _trees():
    for path in SHADOW_DIR.glob("*.py"):
        yield (
            path,
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            ),
        )


def test_shadow_does_not_import_execution_runtime():
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            names = ()
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module,)
            for name in names:
                if any(name == forbidden or name.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_IMPORTS):
                    violations.append((path.name, name))
    assert violations == []


def test_shadow_has_no_execute_or_launch_calls():
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"execute", "launch"}
            ):
                violations.append((path.name, node.lineno, node.func.attr))
    assert violations == []


def test_shadow_never_constructs_authorization_grants():
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if called == "AuthorizationGrantV1":
                    violations.append((path.name, node.lineno))
    assert violations == []


def test_shadow_does_not_mutate_plan_fields():
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in {"steps", "params", "parameters"}:
                    violations.append((path.name, node.lineno, target.attr))
    assert violations == []
