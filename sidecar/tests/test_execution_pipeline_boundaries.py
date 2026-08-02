"""Boundary test: verify no component bypasses ExecutionPipeline.

All tool execution must go through ExecutionPipeline.execute().
Direct calls to ToolGateway.execute(), get_gateway().execute(),
or get_execution_pipeline() without the pipeline are forbidden.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Modules that are AUTHORIZED to reference gateway.execute or ToolGateway.execute
AUTHORIZED_MODULES = frozenset({
    # ExecutionPipeline itself — this IS the pipeline
    "sentinel/core/execution_pipeline.py",
    # ToolExecutionGuard — wraps gateway inside the guard
    "sentinel/security/tool_guard.py",
})

# Files that may still reference get_gateway() for non-execute operations
# (get_spec, list_specs, etc.) — NOT for .execute()
AUTHORIZED_FOR_IMPORT = frozenset({
    "sidecar/modules/__init__.py",      # defines get_gateway and get_execution_pipeline
    "sidecar/modules/sentinel_bridge_helpers.py",  # helper def, not direct execute
})

# Files that have explicit fallback bypasses (with backward compat comment)
KNOWN_FALLBACKS = frozenset({})


def _get_py_files():
    """Find Python files in sentinel/core, sentinel/security, sidecar/modules, sidecar/routers."""
    dirs = [
        ROOT / "sentinel" / "core",
        ROOT / "sentinel" / "security",
        ROOT / "sidecar" / "modules",
        ROOT / "sidecar" / "routers",
    ]
    for d in dirs:
        if d.exists():
            yield from d.rglob("*.py")


def _relative_path(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def test_no_direct_gateway_execute_outside_authorized():
    """Ningún componente puede llamar .execute() directamente en el gateway.

    Solo ExecutionPipeline y ToolExecutionGuard están autorizados.
    """
    violations = []
    for pyfile in _get_py_files():
        rel = _relative_path(pyfile)
        # Skip authorized modules
        if any(rel.startswith(a) for a in AUTHORIZED_MODULES):
            continue
        if any(rel.startswith(a) for a in AUTHORIZED_FOR_IMPORT):
            continue
        if any(rel.startswith(a) for a in KNOWN_FALLBACKS):
            continue

        try:
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        except SyntaxError:
            violations.append(f"{rel}: Syntax error in file")
            continue

        class GatewayCallFinder(ast.NodeVisitor):
            def __init__(self):
                self.found = []

            def visit_Call(self, node):
                # Look for: something.execute(...)
                if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
                    # Check if the caller is a gateway-like object
                    if isinstance(node.func.value, ast.Name):
                        name = node.func.value.id
                        if name in ("gateway", "_gateway", "_tool_gateway", "get_gateway"):
                            self.found.append((node.lineno, name))
                    elif isinstance(node.func.value, ast.Attribute):
                        # Handle instance fields such as self._gateway.execute().
                        # The prior verifier only matched bare names, leaving this
                        # production-call form outside the structural guarantee.
                        name = node.func.value.attr
                        if name in ("gateway", "_gateway", "_tool_gateway"):
                            self.found.append((node.lineno, name))
                    elif isinstance(node.func.value, ast.Call):
                        # handle get_gateway().execute()
                        if isinstance(node.func.value.func, ast.Name):
                            name = node.func.value.func.id
                            if name == "get_gateway":
                                self.found.append((node.lineno, "get_gateway().execute()"))
                self.generic_visit(node)

        finder = GatewayCallFinder()
        finder.visit(tree)
        for lineno, name in finder.found:
            violations.append(f"{rel}:{lineno}: Direct call to {name} — must use ExecutionPipeline.execute()")

    assert not violations, "Bypass violations found:\n" + "\n".join(violations)
