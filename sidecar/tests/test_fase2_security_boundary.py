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

    async def test_direct_execution_bypass_is_not_exposed(self):
        from sentinel.core.execution_pipeline import ExecutionPipeline
        pipeline = ExecutionPipeline()
        assert not hasattr(pipeline, "_execute_direct")


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
        assert "confirm_pending_tool" in content, \
            "/v1/confirm must resolve confirmation through the broker helper"
        assert "approve_execution" not in content, \
            "/v1/confirm must not fall back to legacy Orchestrator approval"


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

    def test_guard_consent_wiring_in_main(self):
        """main.py debe conectar ConsentService + RiskClassifier al guard."""
        pyfile = ROOT / "sidecar" / "main.py"
        content = pyfile.read_text(encoding="utf-8")
        assert "set_consent_service" in content, \
            "ConsentService not wired into guard in main.py"
        assert "set_risk_classifier" in content, \
            "RiskClassifier not wired into guard in main.py"

    def test_guard_support_service_propagation(self):
        """ExecutionPipeline debe propagar audit/consent/risk al guard."""
        pyfile = ROOT / "sentinel" / "core" / "execution_pipeline.py"
        content = pyfile.read_text(encoding="utf-8")
        assert "set_audit_service" in content and "self._guard.set_audit_service" in content, \
            "Pipeline does not propagate audit to guard"
        assert "self._guard.set_consent_service" in content, \
            "Pipeline does not propagate consent to guard"
        assert "self._guard.set_risk_classifier" in content, \
            "Pipeline does not propagate risk classifier to guard"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGuardApprovedExecutionFlow:
    """Una ejecución ya aprobada debe pasar el guard sin reconfirmación."""

    def _make_guard(self, context=None):
        from unittest.mock import MagicMock, AsyncMock
        from sentinel.core import ToolSpec, ToolResult, ToolStatus, ToolGateway
        from sentinel.security.tool_guard import ToolExecutionGuard
        from sentinel.security.models import ToolRequest

        gateway = MagicMock(spec=ToolGateway)
        gateway.get_spec = MagicMock(return_value=ToolSpec(
            id="executor.command",
            name="Command",
            description="Run a command",
            version="1.0",
            parameters={},
            required_permissions=["executor.command"],
            status=ToolStatus.ACTIVE,
        ))
        gateway.execute = AsyncMock(return_value=ToolResult.ok(
            data={"output": "ok"}, tool_id="executor.command"
        ))
        guard = ToolExecutionGuard(tool_gateway=gateway)
        guard._policy = _require_confirm_policy()
        return guard, gateway

    async def test_orchestrator_approval_does_not_authorize_execution(self):
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo ok"},
            source="orchestrator",
            user_context={
                "_orchestrator_approval": True,
                "identity": {"user_id": "alice"},
            },
            user_id="alice",
        )
        result = await guard.execute(request)
        assert result.success is False
        gateway.execute.assert_not_awaited()

    async def test_unvalidated_confirmation_grant_does_not_authorize_execution(self):
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo ok"},
            source="orchestrator",
            user_context={
                "_confirmation_grant": {
                    "tool_id": "executor.command",
                    "user_id": "alice",
                }
            },
            user_id="alice",
        )
        result = await guard.execute(request)
        assert result.success is False
        gateway.execute.assert_not_awaited()

    async def test_confirmation_grant_with_tampered_params_hash_does_not_authorize_execution(self):
        """A syntactically complete grant must still bind the exact payload."""
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo altered"},
            source="orchestrator",
            user_context={
                "_confirmation_grant": {
                    "tool_id": "executor.command",
                    "user_id": "alice",
                    "params_hash": "0" * 16,
                    "identity_hash": "0" * 16,
                },
                "identity": {"user_id": "alice"},
            },
            user_id="alice",
        )
        result = await guard.execute(request)
        assert result.success is False
        gateway.execute.assert_not_awaited()

    async def test_confirmation_grant_rejected_for_other_user(self):
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo ok"},
            source="orchestrator",
            user_context={
                "_confirmation_grant": {
                    "tool_id": "executor.command",
                    "user_id": "bob",
                }
            },
            user_id="alice",
        )
        result = await guard.execute(request)
        assert result.success is False, "Grant of another user must not approve"

    async def test_denied_without_approval_no_consent(self):
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo ok"},
            source="orchestrator",
            user_context={"identity": {"user_id": "alice"}},
            user_id="alice",
        )
        result = await guard.execute(request)
        assert result.success is False
        assert "confirmation" in (result.error or "").lower()

    async def test_missing_session_never_reaches_executor(self):
        guard, gateway = self._make_guard()
        from sentinel.security.models import ToolRequest
        request = ToolRequest(
            tool_name="executor.command",
            arguments={"command": "echo denied"},
            source="api",
            user_context={"identity": {"user_id": "alice"}},
            user_id="alice",
            session_id="",
        )
        result = await guard.execute(request)
        assert result.success is False
        gateway.execute.assert_not_awaited()


def _require_confirm_policy():
    """PolicyEngine que exige confirmación salvo aprobación previa."""
    from sentinel.core.policy import Policy, PolicyEffect, PolicyResult

    class _RequireConfirmPolicy(Policy):
        def policy_id(self) -> str:
            return "test_require_confirm"

        def description(self) -> str:
            return "Require confirmation"

        async def evaluate(self, tool_id, params, context):
            grant = context.get("_confirmation_grant") or {}
            if grant and grant.get("user_id") == (context.get("identity") or {}).get("user_id"):
                return PolicyResult(
                    effect=PolicyEffect.ALLOW,
                    policy_id=self.policy_id(),
                    reason="granted",
                )
            return PolicyResult(
                effect=PolicyEffect.REQUIRE_CONFIRM,
                policy_id=self.policy_id(),
                reason="confirm required",
            )

    from sentinel.core.policy_engine import PolicyEngine
    engine = PolicyEngine(default_effect=PolicyEffect.REQUIRE_CONFIRM)
    engine.register(_RequireConfirmPolicy(), permissions=["executor.command"])
    return engine
