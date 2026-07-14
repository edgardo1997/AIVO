from unittest.mock import MagicMock

import pytest

from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.operational_memory import InMemoryBackend
from sentinel.core.policy import PolicyEffect
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.tool_gateway import ToolGateway
from sentinel.policies.security_policies import (
    GranularPermissionPolicy,
    IdentityPermissionPolicy,
    PermissionLevelPolicy,
)


IDENTITY = {"user_id": "alice", "is_authenticated": True, "permissions": ["*"]}


class DangerousTool(Tool):
    def __init__(self):
        self.calls = 0

    def spec(self):
        return ToolSpec(
            id="executor.command",
            name="Command",
            description="test",
            version="1",
            parameters={},
            required_permissions=["executor.command"],
        )

    async def execute(self, params, context):
        self.calls += 1
        return ToolResult.ok({"executed": params["command"]}, "executor.command")


def gateway_with_confirmation():
    memory = InMemoryBackend()
    engine = PolicyEngine(default_effect=PolicyEffect.DENY)
    engine.register(IdentityPermissionPolicy(), permissions=["executor.command"])
    engine.register(PermissionLevelPolicy(lambda: "confirm"), permissions=["executor.command"])
    gateway = ToolGateway(policy_engine=engine)
    gateway.set_confirmation_broker(ConfirmationBroker(memory))
    audit = MagicMock()
    audit.log_gateway_authorization.return_value = None
    gateway.set_audit_service(audit)
    tool = DangerousTool()
    gateway.register(tool)
    return gateway, tool


@pytest.mark.asyncio
async def test_confirmation_is_identity_bound_and_single_use():
    gateway, tool = gateway_with_confirmation()
    pending = await gateway.execute("executor.command", {"command": "safe-test"}, {"identity": IDENTITY})
    action_id = pending.data["action_id"]
    assert pending.requires_confirmation and tool.calls == 0

    wrong = await gateway.confirm(action_id, True, {**IDENTITY, "user_id": "bob"})
    assert wrong.success is False and "different user" in wrong.error
    approved = await gateway.confirm(action_id, True, IDENTITY)
    assert approved.success is True and tool.calls == 1
    replay = await gateway.confirm(action_id, True, IDENTITY)
    assert replay.success is False and tool.calls == 1


@pytest.mark.asyncio
async def test_rejection_consumes_confirmation_without_execution():
    gateway, tool = gateway_with_confirmation()
    pending = await gateway.execute("executor.command", {"command": "safe-test"}, {"identity": IDENTITY})
    rejected = await gateway.confirm(pending.data["action_id"], False, IDENTITY)
    assert rejected.success is False and tool.calls == 0


@pytest.mark.asyncio
async def test_granular_rule_matches_user_tool_permission_and_path_scope():
    rules = [
        {
            "id": "rule-1",
            "user_id": "alice",
            "tool": "filesystem.*",
            "permission": "filesystem.write",
            "path_prefix": "C:\\protected",
            "effect": "deny",
        }
    ]
    policy = GranularPermissionPolicy(lambda: rules)
    denied = await policy.evaluate(
        "filesystem.write",
        {"path": "C:\\protected\\file.txt"},
        {"identity": IDENTITY, "required_permissions": ["filesystem.write"]},
    )
    allowed = await policy.evaluate(
        "filesystem.write",
        {"path": "C:\\public\\file.txt"},
        {"identity": IDENTITY, "required_permissions": ["filesystem.write"]},
    )
    assert denied.effect == PolicyEffect.DENY
    assert allowed.effect == PolicyEffect.ALLOW
