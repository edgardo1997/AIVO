import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.core.tool import Tool, ToolSpec, ToolResult, ToolStatus
from sentinel.core.tool_gateway import ToolGateway
from sentinel.security.tool_guard import ToolExecutionGuard


class DummyTool(Tool):
    def spec(self):
        return ToolSpec(
            id="dummy.echo",
            name="Dummy Echo",
            description="Echo for tests",
            version="1.0.0",
            parameters={},
            required_permissions=["dummy:use"],
            status=ToolStatus.ACTIVE,
        )

    async def execute(self, params, context):
        return ToolResult.ok(data=params.get("value"), tool_id="dummy.echo")


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_direct_tool_gateway_without_guard_is_denied():
    gateway = ToolGateway()
    gateway.register(DummyTool())
    # simulate a fake execution context with a forged guard reference
    fake_guard = object()
    gateway._execution_guard = fake_guard
    result = await gateway.execute(
        "dummy.echo",
        {"value": "forged"},
        context={
            "identity": {"is_authenticated": True, "user_id": "test_user", "session_id": "test_session"},
            "issuing_guard": object(),  # not the registered guard
        },
    )
    assert result.success is False
    assert "GOVERNANCE_CONTRACT_VIOLATION" in result.error


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_valid_guard_issuing_guard_allows_execution():
    gateway = ToolGateway()
    gateway._policy_engine = object()  # satisfy the runtime guard; policy already in context
    gateway._audit_service = MagicMock()
    gateway.register(DummyTool())
    guard = ToolExecutionGuard(tool_gateway=gateway)
    # guard should be registered as the issuing authority
    assert gateway._execution_guard is guard

    result = await gateway.execute(
        "dummy.echo",
        {"value": "ok"},
        context={
            "identity": {"is_authenticated": True, "user_id": "test_user", "session_id": "test_session"},
            "issuing_guard": guard,
            "_guard_policy_result": PolicyResult(
                effect=PolicyEffect.ALLOW,
                policy_id="test",
                reason="test",
            ),
        },
    )
    assert result.success is True
    assert result.data == "ok"


@pytest.mark.alpha_constitutional_gate
@pytest.mark.asyncio
async def test_missing_identity_is_denied():
    gateway = ToolGateway()
    gateway.register(DummyTool())
    result = await gateway.execute("dummy.echo", {"value": "x"}, context={})
    assert result.success is False
    assert "AUTHENTICATION_REQUIRED" in result.error
