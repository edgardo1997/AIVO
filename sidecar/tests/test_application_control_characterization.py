"""Characterization tests for the current Application Control authorization flow.

These tests intentionally preserve current behavior, including contract
mismatches. They do not launch applications or invoke operating-system APIs.
"""

import inspect
from unittest.mock import AsyncMock, Mock

import pytest

from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.decision_engine import Decision, DecisionEngine, DecisionResult
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import InMemoryBackend
from sentinel.core.planner import Plan, Planner, PlanStep
from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import ToolResult, ToolSpec
from sentinel.core.tool_gateway import ToolGateway
from sentinel.core.orchestrator import Orchestrator
from sentinel.tools.app_discovery_tool import AppDiscoveryTool
from sidecar.services.executor_service import ExecutorService


def _launch_plan() -> Plan:
    intent = Intent(
        action="launch",
        target="executor.launch",
        parameters={"app_name": "Forza Horizon 6"},
        raw_input="Abrir Forza Horizon 6",
    )
    return Plan(
        steps=[
            PlanStep(
                id="launch",
                tool_id="executor.launch",
                params={"app_name": "Forza Horizon 6"},
                estimated_impact="medium",
            )
        ],
        intent=intent,
        risk_score=0.4,
    )


def _protected_tool() -> Mock:
    tool = Mock()
    tool.spec.return_value = ToolSpec(
        id="executor.launch",
        name="Launch Application",
        description="Characterization-only fake tool",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
        required_permissions=["executor.launch"],
    )
    tool.execute = AsyncMock(return_value=ToolResult.ok({"launched": False}))
    return tool


def _identity() -> dict:
    return {
        "identity": {
            "user_id": "characterization-user",
            "session_id": "characterization-session",
            "is_authenticated": True,
        }
    }


def test_decision_engine_returns_risk_recommendation_not_authorization_grant():
    result = DecisionEngine(get_permission_level=lambda: "confirm").evaluate(
        _launch_plan(),
        context={},
    )

    assert isinstance(result, DecisionResult)
    assert result.decision in {
        Decision.APPROVE,
        Decision.REJECT,
        Decision.REQUIRE_CONFIRM,
        Decision.MODIFY,
    }
    assert 0.0 <= result.base_risk_score <= 1.0
    assert 0.0 <= result.final_risk_score <= 1.0
    assert not hasattr(result, "authorization_grant")
    assert not hasattr(result, "authorization_id")


@pytest.mark.asyncio
async def test_policy_engine_is_evaluated_before_protected_tool_execution():
    events = []
    observed_context = {}

    async def evaluate_policy(tool_id, params, context):
        events.append("policy")
        observed_context.update(context)
        return PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="characterization.allow",
            reason="Characterize current allowed path",
        )

    async def execute_tool(params, context):
        events.append("execute")
        return ToolResult.ok({"launched": False})

    policy = Mock()
    policy.policy_id.return_value = "characterization.allow"
    policy.evaluate = AsyncMock(side_effect=evaluate_policy)
    engine = PolicyEngine()
    engine.register(policy, permissions=["executor.launch"])

    tool = _protected_tool()
    tool.execute = AsyncMock(side_effect=execute_tool)
    gateway = ToolGateway(policy_engine=engine)
    gateway.set_audit_service(Mock())
    gateway.register(tool)

    result = await gateway.execute(
        "executor.launch",
        {"app_name": "Forza Horizon 6"},
        _identity(),
    )

    assert result.success is True
    assert events == ["policy", "execute"]
    assert observed_context["required_permissions"] == ["executor.launch"]
    assert result.policy_result["effect"] == PolicyEffect.ALLOW.value


@pytest.mark.asyncio
async def test_gateway_denies_protected_tool_when_policy_authority_is_missing():
    tool = _protected_tool()
    gateway = ToolGateway()
    gateway.register(tool)

    result = await gateway.execute(
        "executor.launch",
        {"app_name": "Forza Horizon 6"},
        _identity(),
    )

    assert result.success is False
    assert result.policy_decision == "_missing_policy_engine"
    assert result.policy_result["effect"] == PolicyEffect.DENY.value
    tool.execute.assert_not_awaited()


def test_gateway_rejects_active_tool_without_declared_permissions():
    tool = _protected_tool()
    tool.spec.return_value.required_permissions = []

    with pytest.raises(ValueError, match="must declare at least one required permission"):
        ToolGateway().register(tool)


@pytest.mark.asyncio
async def test_confirmation_broker_persists_identity_bound_single_use_pending_action():
    memory = InMemoryBackend()
    broker = ConfirmationBroker(memory, ttl_seconds=600)
    try:
        action_id = broker.request(
            tool_id="executor.launch",
            params={"app_name": "Forza Horizon 6"},
            context=_identity(),
            reason="Policy requires confirmation",
            risk_level="medium",
            plan_id="plan-characterization",
        )
        record = memory.get_pending_action(action_id)

        assert record is not None
        assert record.params["kind"] == "tool_confirmation"
        assert record.params["tool_id"] == "executor.launch"
        assert record.params["params"] == {"app_name": "Forza Horizon 6"}
        assert record.risk_level == "medium"
        assert record.plan_id == "plan-characterization"
        assert record.params_hash
        assert record.identity_hash
        assert record.redacted is True

        grant = broker.consume(action_id, "characterization-user", approved=True)
        assert grant is not None
        assert grant.tool_id == "executor.launch"
        assert broker.consume(action_id, "characterization-user", approved=True) is None
    finally:
        memory.close()


def test_current_code_contains_two_distinct_pending_consent_routes():
    orchestrator_source = inspect.getsource(Orchestrator)
    gateway_source = inspect.getsource(ToolGateway.execute)

    assert "PendingActionRecord(" in orchestrator_source
    assert "self._memory.store_pending_action(pending)" in orchestrator_source
    assert "self._confirmation_broker.request(" in gateway_source
    assert 'ctx.get("_orchestrator_approval")' in gateway_source


def test_app_discovery_contract_requires_action_and_lookup_name():
    spec = AppDiscoveryTool().spec()

    assert spec.parameters["required"] == ["action"]
    assert "lookup" in spec.parameters["properties"]["action"]["enum"]
    assert "name" in spec.parameters["properties"]
    assert "app_name" not in spec.parameters["properties"]


def test_planner_currently_passes_app_name_not_lookup_name_to_discovery_step():
    intent = Intent(
        action="launch",
        target="executor.launch",
        parameters={"app_name": "Forza Horizon 6"},
        raw_input="Abrir Forza Horizon 6",
    )

    plan = Planner().plan(intent)
    discovery = next(step for step in plan.steps if step.tool_id == "app.discovery")

    assert discovery.params["app_name"] == "Forza Horizon 6"
    assert "action" not in discovery.params
    assert "name" not in discovery.params


@pytest.mark.asyncio
async def test_executor_launch_schema_and_handler_accept_unrestricted_text_without_launching():
    service = ExecutorService()
    spec = service.spec_launch()
    app_name_schema = spec.parameters["properties"]["app_name"]

    assert spec.parameters["required"] == ["app_name"]
    assert set(spec.parameters["properties"]) == {"app_name", "args"}
    assert app_name_schema["type"] == "string"
    assert "enum" not in app_name_schema
    assert "pattern" not in app_name_schema
    assert "elevated" not in spec.parameters["properties"]

    service.launch_app = Mock(return_value={"launched": False})
    arbitrary_text = "texto libre proporcionado por el usuario"
    result = await service.execute_launch({"app_name": arbitrary_text}, {})

    assert result.success is True
    service.launch_app.assert_called_once_with(arbitrary_text, "", elevated=False)
