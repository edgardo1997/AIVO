import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from modules.sentinel_bridge import get_orchestrator, reset_bridge
from conftest import TEST_IDENTITY

client = TestClient(app)


class TestSimulationBlocking:
    def setup_method(self):
        reset_bridge()

    def test_low_risk_not_blocked(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is False
        assert data["action_id"] is None

    def test_high_risk_command_is_blocked(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command rm -rf /"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is True, f"Expected blocked=True, got {data.get('blocked')}"
        assert data["action_id"] is not None, "Expected action_id for blocked execution"
        assert data["error"] is not None, "Expected error message explaining block"
        assert "autorización" in data["error"].lower()
        assert data["simulation_summary"] != ""

    def test_blocking_pending_action_stored(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command rm -rf /",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        assert result.action_id is not None
        memory = orch._memory
        pending = memory.get_pending_action(result.action_id)
        assert pending is not None
        assert pending.params.get("utterance") == "run command rm -rf /"
        memory.remove_pending_action(result.action_id)

    def test_legacy_approve_execution_cannot_execute(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command echo hello_approved",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        action_id = result.action_id

        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")
        approved = asyncio.run(orch.approve_execution(action_id, approved=True))
        perm_svc.set_level("confirm")

        # Legacy approval is deprecated and must never produce authority:
        # no execution result, no tool_result, and an unambiguous denial.
        assert approved.tool_result is None
        assert approved.error is not None
        assert "deprecated" in approved.error.lower() or "reconfirm" in approved.error.lower()

    def test_legacy_reject_execution_returns_denial(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(
            orch.process(
                "run command echo should_reject",
                identity=TEST_IDENTITY,
            )
        )
        assert result.blocked is True
        action_id = result.action_id

        rejected = asyncio.run(orch.approve_execution(action_id, approved=False))
        # The legacy adapter never executes: rejecting must not be claimed as an
        # approval result either; it fails closed with the deprecation denial.
        assert rejected.tool_result is None
        assert rejected.error is not None

    def test_legacy_approve_unknown_action_fails_closed(self):
        orch = get_orchestrator()
        import asyncio

        result = asyncio.run(orch.approve_execution("nonexistent_action", approved=True))
        # An action that cannot be resolved must never grant authority.
        assert result.tool_result is None
        assert result.error is not None
        assert getattr(result, "blocked", False) is False
        durables = getattr(getattr(orch, "_tool_gateway", None), "_confirmation_broker", None)
        if durables is not None:
            assert durables.consume("nonexistent_action", TEST_IDENTITY.get("user_id"), True) is None

    def test_blocked_via_api_endpoint(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command rm -rf /"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is True

    def test_approve_reject_via_api_endpoint(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo api_test"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        reject_resp = client.post("/api/sentinel/simulate/reject", json={"action_id": action_id})
        assert reject_resp.status_code == 200
        reject_data = reject_resp.json()
        assert reject_data["blocked"] is False
        assert reject_data["approved"] is False

    def test_approve_via_legacy_api_is_denied(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo api_approve"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        approve_resp = client.post(
            "/api/sentinel/simulate/approve",
            json={
                "action_id": action_id,
                "approved": True,
            },
        )
        assert approve_resp.status_code == 200
        approve_data = approve_resp.json()
        # The legacy approve endpoint routes to the deprecated adapter and must
        # deny execution: no tool_result success, explicit denial, no block claim.
        assert approve_data.get("tool_result") is None or approve_data.get("tool_result", {}).get("success") is not True
        if approve_data.get("error"):
            assert "deprecated" in approve_data["error"].lower() or "reconfirm" in approve_data["error"].lower()

    def test_durable_confirmation_executes_real_tool(self):
        """A valid durable approval (ConfirmationBroker -> gateway.confirm ->
        ExecutionPipeline -> ToolExecutionGuard -> executor) CAN continue."""
        import asyncio
        from unittest.mock import MagicMock

        from sentinel.core.confirmation import ConfirmationBroker
        from sentinel.core.execution_pipeline import ExecutionPipeline
        from sentinel.core.operational_memory import InMemoryBackend
        from sentinel.core.policy import PolicyEffect
        from sentinel.core.policy_engine import PolicyEngine
        from sentinel.core.tool import Tool, ToolResult, ToolSpec
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.policies.security_policies import (
            IdentityPermissionPolicy,
            PermissionLevelPolicy,
        )
        from sentinel.security.tool_guard import ToolExecutionGuard

        calls: list = []

        class _EscrowTool(Tool):
            def spec(self):
                return ToolSpec(
                    id="executor.command", name="Command", description="t", version="1",
                    parameters={}, required_permissions=["executor.command"],
                )

            async def execute(self, params, context):
                calls.append(params["command"])
                return ToolResult.ok({"executed": params["command"]}, "executor.command")

        memory = InMemoryBackend()
        engine = PolicyEngine(default_effect=PolicyEffect.DENY)
        engine.register(IdentityPermissionPolicy(), permissions=["executor.command"])
        engine.register(PermissionLevelPolicy(lambda: "confirm"), permissions=["executor.command"])
        gateway = ToolGateway(policy_engine=engine)
        audit = MagicMock()
        audit.log_gateway_authorization.return_value = None
        gateway.set_audit_service(audit)
        gateway.set_confirmation_broker(ConfirmationBroker(memory))
        guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=engine, audit_service=audit)
        pipeline = ExecutionPipeline(tool_gateway=gateway, tool_execution_guard=guard, audit_service=audit)
        pipeline.set_confirmation_broker(gateway._confirmation_broker)

        async def _confirmed(tool_id, params, context):
            return await pipeline.execute(tool_id, params, context, source="confirmation")

        gateway.set_confirmation_executor(_confirmed)
        gateway.register(_EscrowTool())
        identity = {
            "user_id": "test-user",
            "session_id": "test-session",
            "is_authenticated": True,
            "permissions": ["executor.command"],
        }

        pending = asyncio.run(gateway.execute(
            "executor.command", {"command": "echo durable_ok"}, {"identity": identity}
        ))
        assert pending.requires_confirmation is True
        assert calls == []
        action_id = pending.data["action_id"]

        approved = asyncio.run(gateway.confirm(action_id, True, identity))
        assert approved.success is True, approved.error
        assert calls == ["echo durable_ok"]

        replay = asyncio.run(gateway.confirm(action_id, True, identity))
        assert replay.success is False  # single-use
        assert len(calls) == 1

    def test_modify_and_approve_sends_modified_steps(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")

        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo test_modified"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]
        assert action_id is not None

        plan_data = data.get("plan", {})
        steps = plan_data.get("steps", [])
        assert len(steps) > 0

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
                "steps": steps,
            },
        )
        perm_svc.set_level("confirm")
        assert modify_resp.status_code == 200
        modify_data = modify_resp.json()
        assert modify_data["modified"] is True
        assert modify_data["approved"] is False
        assert modify_data["requires_reconfirmation"] is True
        assert modify_data["step_results"] is None
        # A modified plan never mints a fresh auto-approval from a legacy action:
        # it only demands durable reconfirmation.  Denial is explicit.
        if modify_data.get("action_id"):
            assert modify_data["action_id"] != action_id

    def test_modify_and_approve_no_steps_returns_error(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo no_steps"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
                "steps": [],
            },
        )
        modify_data = modify_resp.json() if modify_resp.status_code == 200 else modify_resp.json()
        assert modify_data.get("error") is not None or modify_data.get("detail") is not None

    def test_modify_and_approve_missing_action_id(self):
        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "steps": [{"tool_id": "system.info"}],
            },
        )
        assert modify_resp.status_code == 400

    def test_modify_and_approve_missing_steps(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo missing_steps"})
        assert resp.status_code == 200
        data = resp.json()
        action_id = data["action_id"]

        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": action_id,
            },
        )
        modify_data = modify_resp.json()
        assert modify_data.get("error") is not None
        assert "steps" in modify_data["error"].lower()

    def test_modify_and_approve_nonexistent_action(self):
        modify_resp = client.post(
            "/api/sentinel/simulate/modify-and-approve",
            json={
                "action_id": "nonexistent",
                "steps": [{"tool_id": "system.info"}],
            },
        )
        assert modify_resp.status_code == 200
        modify_data = modify_resp.json()
        assert modify_data["error"] is not None
        assert modify_data["approved"] is False

    def test_chat_pipeline_trace_includes_blocked(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/chat", json={"message": "delete everything"})
        perm_svc.set_level("confirm")
        assert resp.status_code == 200
        data = resp.json()
        pipeline = data.get("pipeline", {})
        assert "blocked" in pipeline
        assert "action_id" in pipeline
        assert "simulation_summary" in pipeline
