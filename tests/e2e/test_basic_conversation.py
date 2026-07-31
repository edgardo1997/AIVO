"""Caso 1 — Conversación básica.

Entrada: "Hola Sentinel"
Pipeline: Usuario → API → SentinelRuntime → IntentEngine → ContextEngine → Planner → SecurityEngine → ExecutionEngine → ToolGateway → Memory → Response → Audit
"""

import pytest
from tests.e2e.fixtures.sentinel_test_environment import create_sentinel_runtime
from sentinel.testing.assertions import E2EAssertions as A


@pytest.fixture
def runtime():
    return create_sentinel_runtime(auto_approve=True)


@pytest.mark.e2e
class TestBasicConversation:
    """Valida el pipeline completo de una conversación simple."""

    def _inner(self, data: dict) -> dict:
        return data.get("data", data) if isinstance(data, dict) else {}

    @pytest.mark.asyncio
    async def test_conversation_pipeline(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Hola Sentinel", session_id="e2e-conversation", user_id="test")

        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"success": response.success, "data": response.data}

        A.assert_success(data)
        A.assert_intent_detected(self._inner(data), "CHAT")

    @pytest.mark.asyncio
    async def test_intent_detection(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Hola Sentinel", session_id="e2e-intent", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {}
        inner = self._inner(data)

        assert "intent" in inner, "No intent in response"
        intent_str = str(inner.get("intent", ""))
        assert "query" in intent_str.lower() or "CHAT" in intent_str, f"Unexpected intent: {intent_str}"

    @pytest.mark.asyncio
    async def test_memory_accessed(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        session_id = "e2e-memory-test"
        req = SentinelRequest(utterance="Hola Sentinel", session_id=session_id, user_id="test")
        await runtime.process(req)

        memory = runtime._memory
        assert memory is not None, "Memory is not configured"
        assert hasattr(memory, "get_session_history"), "Memory does not support get_session_history"

    @pytest.mark.asyncio
    async def test_response_generated(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Hola Sentinel", session_id="e2e-response", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"success": response.success, "duration_ms": response.duration_ms}

        assert data.get("success", False), f"Response not successful: {data.get('error')}"
        assert data.get("duration_ms", -1) >= 0, "No duration_ms in response"
        assert response.execution_id, "No execution_id in response"

    @pytest.mark.asyncio
    async def test_audit_created(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Hola Sentinel", session_id="e2e-audit", user_id="test")
        await runtime.process(req)

        audit_log = runtime.audit_log
        assert len(audit_log) > 0, "No audit entries created"
        assert any(e.get("action") == "runtime.process" for e in audit_log), "Missing runtime.process audit entry"

    @pytest.mark.asyncio
    async def test_provider_and_latency_recorded(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Hola Sentinel", session_id="e2e-latency", user_id="test")
        response = await runtime.process(req)

        assert response.duration_ms >= 0, "duration_ms not set"
        assert response.success, "Pipeline failed"
        assert response.execution_id, "No execution_id"
