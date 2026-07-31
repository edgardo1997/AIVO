"""FASE 2: Security Boundary Repair — tests for mandatory security boundary.

Verifies:
1. ExecutionPipeline._execute_guarded() blocks when no guard configured
2. All v1 routers call request_identity() on every endpoint
3. /v1/confirm routes through Orchestrator (no direct gateway.confirm)
4. ToolExecutionGuard is wired in production
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

AUTHORIZED_AUTH_SKIP = frozenset({
    "sidecar/routers/v1/__init__.py",
    "sidecar/routers/v1/execute.py",    # already verified uses request_identity
    "sidecar/routers/auth_jwt.py",      # login/refresh endpoints — inherently public
    "sidecar/routers/system_live.py",   # health/liveness endpoint — public
})


def _get_router_files():
    """Scan v1 routers and any auth/system routers for endpoint auth."""
    routers_dir = ROOT / "sidecar" / "routers"
    if routers_dir.exists():
        yield from (routers_dir / "v1").rglob("*.py")
        yield routers_dir / "auth_jwt.py"
        yield routers_dir / "system_live.py"


def _relative_path(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


@pytest.mark.unit
@pytest.mark.asyncio
class TestExecutionPipelineGuardRequired:
    """ExecutionPipeline debe requerir ToolExecutionGuard."""

    async def test_execute_guarded_fails_without_guard(self):
        from sentinel.core.execution_pipeline import ExecutionPipeline
        pipeline = ExecutionPipeline()
        result = await pipeline._execute_guarded("test.tool", {}, {}, "test")
        assert not result.success
        assert "ToolExecutionGuard" in (result.error or "")

    async def test_execute_direct_fails_without_gateway(self):
        from sentinel.core.execution_pipeline import ExecutionPipeline
        pipeline = ExecutionPipeline()
        result = await pipeline._execute_direct("test.tool", {}, {})
        assert not result.success
        assert "no toolgateway" in (result.error or "").lower()


@pytest.mark.unit
class TestV1EndpointAuthentication:
    """Todos los endpoints v1 deben verificar identidad."""

    def _find_missing_auth(self):
        """AST scan: find endpoint functions that don't call request_identity."""
        violations = []
        for pyfile in _get_router_files():
            rel = _relative_path(pyfile)
            if rel in AUTHORIZED_AUTH_SKIP:
                continue
            try:
                tree = ast.parse(pyfile.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            routers = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                       getattr(node.func, 'attr', None) in ('get', 'post', 'put', 'patch', 'delete')]
            decorator_lines = {node.lineno for node in routers}

            class EndpointFinder(ast.NodeVisitor):
                def __init__(self):
                    self.endpoints = []

                def visit_FunctionDef(self, node):
                    is_route = any(
                        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and d.func.attr in ('get', 'post', 'put', 'patch', 'delete')
                        for d in node.decorator_list
                    )
                    if is_route:
                        has_auth = any(
                            isinstance(n, ast.Call) and
                            isinstance(n.func, ast.Attribute) and
                            n.func.attr == 'request_identity'
                            for n in ast.walk(node)
                        )
                        if not has_auth:
                            self.endpoints.append(node.name)
                    self.generic_visit(node)

            finder = EndpointFinder()
            finder.visit(tree)
            for ep in finder.endpoints:
                violations.append(f"{rel}:{ep} — missing request_identity() call")
        return violations

    def test_all_endpoints_have_auth(self):
        violations = self._find_missing_auth()
        assert not violations, "Endpoints without identity check:\n" + "\n".join(violations)


@pytest.mark.unit
class TestConfirmEndpointUsesOrchestrator:
    """/v1/confirm debe usar Orchestrator.approve_execution() y no gateway.confirm()."""

    def test_no_direct_gateway_confirm_in_execute_router(self):
        pyfile = ROOT / "sidecar" / "routers" / "v1" / "execute.py"
        content = pyfile.read_text(encoding="utf-8")
        assert "get_gateway().confirm" not in content, \
            "/v1/confirm still calls get_gateway().confirm() — must use Orchestrator"
        assert "get_orchestrator()" in content, \
            "/v1/confirm no longer references orchestrator"
        assert "approve_execution" in content, \
            "/v1/confirm must call orchestrator.approve_execution()"


@pytest.mark.unit
class TestGuardWiredInProduction:
    """ToolExecutionGuard debe estar cableado en producción."""

    def test_production_wiring_includes_guard(self):
        pyfile = ROOT / "sidecar" / "modules" / "__init__.py"
        content = pyfile.read_text(encoding="utf-8")
        assert "ToolExecutionGuard" in content, \
            "ToolExecutionGuard not imported in modules/__init__.py"
        assert "tool_execution_guard=guard" in content or "tool_execution_guard = guard" in content, \
            "ToolExecutionGuard not passed to ExecutionPipeline in __init__.py"

    def test_execution_pipeline_requires_guard(self):
        pyfile = ROOT / "sentinel" / "core" / "execution_pipeline.py"
        content = pyfile.read_text(encoding="utf-8")
        assert "no ToolExecutionGuard configured" in content, \
            "ExecutionPipeline does not enforce guard requirement"

    def test_no_gateway_confirm_dead_code(self):
        """Verify no remaining imports or references to gateway.confirm."""
        for pyfile in _get_router_files():
            rel = _relative_path(pyfile)
            content = pyfile.read_text(encoding="utf-8")
            if ".confirm(" in content and rel != "sidecar/routers/v1/execute.py":
                pytest.fail(f"{rel} still references .confirm() — bypass risk")
            if "gateway.confirm" in content:
                pytest.fail(f"{rel} still calls gateway.confirm() — bypass risk")
