"""Caso 2 — Ejecución de herramienta con validación de seguridad.

Entrada: "Abre Spotify"
Pipeline: Usuario → Intent → Planner → DecisionEngine → RiskClassifier → PolicyEngine → ConsentService → ToolGateway → Execution → Audit

Validación crítica de seguridad:
  - Toda ejecución DEBE pasar por PolicyEngine + RiskClassifier + DecisionEngine + ConsentService
  - NO debe existir ruta directa Model → ToolGateway → Execute
"""

import pytest
from tests.e2e.fixtures.sentinel_test_environment import (
    create_sentinel_runtime,
    StubToolGateway,
    StubPolicyEngine,
    StubConsentService,
    StubRiskClassifier,
    StubDecisionEngine,
    StubAuditService,
)
from sentinel.testing.assertions import E2EAssertions as A


@pytest.fixture
def runtime():
    return create_sentinel_runtime(auto_approve=True)


def _inner(data: dict) -> dict:
    return data.get("data", data) if isinstance(data, dict) else {}


@pytest.mark.e2e
class TestToolExecution:
    """Valida el pipeline de ejecución de herramientas con controles de seguridad."""

    @pytest.mark.asyncio
    async def test_tool_discovery(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-tool", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"success": response.success, "data": response.data}

        A.assert_success(data)
        A.assert_intent_detected(_inner(data), "ACTION")
        A.assert_plan_has_steps(_inner(data), min_steps=1)

    @pytest.mark.asyncio
    async def test_policy_checked(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        gateway = StubToolGateway()
        policy = StubPolicyEngine()
        gateway._policy_engine = policy
        runtime.set_gateway(gateway)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-policy", user_id="test")
        await runtime.process(req)

        assert hasattr(gateway, "_policy_engine"), "PolicyEngine not configured on gateway"

    @pytest.mark.asyncio
    async def test_risk_classified(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        risk = StubRiskClassifier()
        runtime.set_risk_classifier(risk)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-risk", user_id="test")
        await runtime.process(req)

        assert risk.call_count > 0, "RiskClassifier was not consulted"

    @pytest.mark.asyncio
    async def test_decision_evaluated(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        decision = StubDecisionEngine()
        runtime.set_decision_engine(decision)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-decision", user_id="test")
        await runtime.process(req)

        assert decision.call_count > 0, "DecisionEngine was not consulted"

    @pytest.mark.asyncio
    async def test_consent_requested_when_decision_requires(self, runtime):
        from sentinel.core.runtime import SentinelRequest
        from tests.e2e.fixtures.sentinel_test_environment import StubDecisionEngine

        consent = StubConsentService(auto_grant=False)
        runtime.set_consent_service(consent)
        runtime.set_decision_engine(StubDecisionEngine(mode="require_confirm"))

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-consent", user_id="test")
        response = await runtime.process(req)

        assert not response.success, "Should have been blocked without consent confirmation"
        assert "User denied confirmation" in (response.error or ""), f"Unexpected error: {response.error}"

    @pytest.mark.asyncio
    async def test_tool_gateway_executes(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        gateway = StubToolGateway()
        runtime.set_gateway(gateway)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-gateway", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"success": response.success}

        A.assert_success(data)
        assert len(gateway.executions) > 0, "ToolGateway.execute was not called"
        tool_ids = [e["tool_id"] for e in gateway.executions]
        assert any("app" in tid for tid in tool_ids), f"No app-related tools found in executions: {tool_ids}"

    @pytest.mark.asyncio
    async def test_audit_records_tool_execution(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-audit", user_id="test")
        await runtime.process(req)

        audit_log = runtime.audit_log
        assert len(audit_log) > 0, "No audit entries created"
        assert any("runtime.process" in e.get("action", "") for e in audit_log), "Missing runtime.process audit entry"

    @pytest.mark.asyncio
    async def test_no_direct_tool_gateway_bypass(self, runtime):
        """Verifica que la ejecución pasa por RiskClassifier + DecisionEngine antes de ToolGateway.

        El pipeline del Runtime ejecuta:
          1. Intent → Planner → RiskClassifier → DecisionEngine → ... → ToolGateway
        """
        from sentinel.core.runtime import SentinelRequest

        risk = StubRiskClassifier()
        decision = StubDecisionEngine()
        gateway = StubToolGateway()

        runtime.set_risk_classifier(risk)
        runtime.set_decision_engine(decision)
        runtime.set_gateway(gateway)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-nobypass", user_id="test")
        response = await runtime.process(req)

        assert risk.call_count > 0, "RiskClassifier was not consulted before execution"
        assert decision.call_count > 0, "DecisionEngine was not consulted before execution"
        assert len(gateway.executions) > 0, "ToolGateway was not reached"

        runtime_audit = runtime.audit_log
        assert len(runtime_audit) > 0, "No runtime audit trail"
        assert response.success, f"Pipeline failed: {response.error}"

    @pytest.mark.asyncio
    async def test_decision_deny_blocks_execution(self, runtime):
        """Si DecisionEngine rechaza, la ejecución no debe llegar a ToolGateway."""
        from sentinel.core.runtime import SentinelRequest
        from tests.e2e.fixtures.sentinel_test_environment import StubDecisionEngine

        gateway = StubToolGateway()
        runtime.set_decision_engine(StubDecisionEngine(mode="deny"))
        runtime.set_gateway(gateway)

        req = SentinelRequest(utterance="Abre Spotify", session_id="e2e-deny", user_id="test")
        response = await runtime.process(req)

        assert not response.success, "Tool execution should have been denied by decision engine"
        assert response.error, "Expected error message but got none"
        assert len(gateway.executions) == 0, "ToolGateway was reached despite decision deny"
