"""Pruebas de la frontera de seguridad en ejecución de herramientas.

Verifica que:
  1. ModelRouter NO ejecuta herramientas sin ToolExecutionGuard
  2. ToolExecutionGuard rechaza argumentos inválidos
  3. ToolExecutionGateway bloquea herramientas críticas sin confirmación
  4. Herramientas legítimas pasan correctamente
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from sentinel.core import ToolSpec, ToolStatus, ToolResult, ToolGateway
from sentinel.security.models import ToolRequest, RiskLevel, SecurityDecision
from sentinel.security.tool_guard import ToolExecutionGuard
from sentinel.security.argument_validator import ArgumentValidator
from sentinel.security.tool_rate_limiter import ToolRateLimiter


class TestToolExecutionBoundary:
    """Verifica que el ToolExecutionGuard es el único punto de ejecución."""

    def test_guard_rejects_invalid_arguments(self):
        """Si los argumentos no pasan validación, se rechazan sin ejecutar."""
        guard = ToolExecutionGuard()
        request = ToolRequest(
            tool_name="filesystem.write",
            arguments={"path": "/etc/passwd"},
            source="test",
        )
        result = guard._validator.validate(
            request.tool_name, request.arguments
        )
        assert result.valid is False or result.risk_level >= RiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_guard_blocks_critical_tool_without_confirmation(self):
        """Herramienta crítica sin consent service es denegada."""
        guard = ToolExecutionGuard()
        request = ToolRequest(
            tool_name="filesystem.delete",
            arguments={"path": "/tmp/test.txt"},
            source="test",
            user_context={"intent": "delete temporary file"},
        )
        result = await guard.execute(request)
        assert result.decision == SecurityDecision.DENIED
        assert result.success is False

    @pytest.mark.asyncio
    async def test_guard_allows_low_risk_tool_without_policy(self):
        """Herramienta de bajo riesgo sin PolicyEngine pasa."""
        guard = ToolExecutionGuard()
        gateway = MagicMock(spec=ToolGateway)
        gateway.get_spec = MagicMock(return_value=ToolSpec(
            id="filesystem.read",
            name="Read File",
            description="Read a file",
            version="1.0",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            required_permissions=[],
            status=ToolStatus.ACTIVE,
        ))
        gateway.execute = AsyncMock(return_value=ToolResult.ok(
            data={"content": "safe content"}, tool_id="filesystem.read"
        ))
        guard.set_tool_gateway(gateway)

        request = ToolRequest(
            tool_name="filesystem.read",
            arguments={"path": "/home/user/doc.txt"},
            source="test",
        )
        result = await guard.execute(request)
        assert result.decision == SecurityDecision.APPROVED
        assert result.data["content"] == "safe content"

    @pytest.mark.asyncio
    async def test_guard_rate_limit_blocks_excessive_calls(self):
        """Rate limiter bloquea llamadas excesivas en ventana."""
        from sentinel.security.tool_rate_limiter import RateLimitConfig
        rate_limiter = ToolRateLimiter({
            "filesystem.read": RateLimitConfig(max_calls=1, window_seconds=60),
        })
        guard = ToolExecutionGuard(rate_limiter=rate_limiter)
        gateway = MagicMock(spec=ToolGateway)
        gateway.get_spec = MagicMock(return_value=ToolSpec(
            id="filesystem.read",
            name="Read File",
            description="Read a file",
            version="1.0",
            parameters={},
            required_permissions=[],
            status=ToolStatus.ACTIVE,
        ))
        gateway.execute = AsyncMock(return_value=ToolResult.ok(
            data={"content": "safe"}, tool_id="filesystem.read"
        ))
        guard.set_tool_gateway(gateway)

        request = ToolRequest(
            tool_name="filesystem.read",
            arguments={"path": "/tmp/test.txt"},
            source="test",
        )
        r1 = await guard.execute(request)
        assert r1.success is True

        r2 = await guard.execute(request)
        assert r2.success is False
        assert "rate limit" in (r2.error or "").lower()

    def test_no_execute_tool_call_in_model_router(self):
        """ModelRouter ya no tiene _execute_tool_call (solo _execute_tool_call_safe async)."""
        from sentinel.core.model_router import ModelRouter
        router = ModelRouter()
        assert not hasattr(router, "_execute_tool_call")
        assert hasattr(router, "_execute_tool_call_safe")

    @pytest.mark.asyncio
    async def test_guard_validates_path_traversal_attack(self):
        """Path traversal es detectado y bloqueado."""
        guard = ToolExecutionGuard()
        request = ToolRequest(
            tool_name="filesystem.read",
            arguments={"path": "../../../etc/passwd"},
            source="test",
        )
        result = await guard.execute(request)
        assert result.success is False or ".." in str(result.error or "")
