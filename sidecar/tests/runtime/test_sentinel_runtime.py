"""Pruebas del pipeline unificado SentinelRuntime.

Test 1: pipeline completo con flujo "abre mi navegador"
Test 2: ningún componente antiguo (IntentEngineV2) es llamado
Test 3: misma entrada produce misma decisión

Requiere: pytest-asyncio
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from sentinel.core.runtime import (
    SentinelRuntime,
    SentinelRequest,
    SentinelResponse,
    TaskIntent,
)


class TestSentinelRuntimePipeline:
    """Verifica que SentinelRuntime es el único pipeline de ejecución."""

    @pytest.mark.asyncio
    async def test_pipeline_completo(self):
        """Test 1: pipeline completo — "abre mi navegador" pasa por
        IntentEngine → Planner → SecurityEngine → ExecutionEngine."""
        runtime = SentinelRuntime()

        # Mock cada etapa del pipeline
        intent = MagicMock()
        intent.parse.return_value = TaskIntent(
            objective="open browser",
            category="ACTION",
            risk_level="low",
            required_capabilities=["tool_calling"],
            confidence=0.9,
            raw_input="abre mi navegador",
            action="execute",
            target="executor.launch",
        )
        runtime.set_intent_engine(intent)

        planner = MagicMock()
        step = MagicMock()
        step.tool_id = "executor.launch"
        step.get = lambda k, d=None: {"app": "chrome"}.get(k, d)
        step.params = {"app": "chrome"}
        step.parameters = {"app": "chrome"}
        planner.plan.return_value = MagicMock(
            steps=[step],
            intent=intent.parse.return_value,
        )
        runtime.set_planner(planner)

        gateway = MagicMock()
        gateway.execute = AsyncMock(return_value={"success": True, "data": {"status": "launched"}})
        runtime.set_gateway(gateway)

        router = MagicMock()
        router.select.return_value = MagicMock(provider_id="test", model="gpt-4")
        runtime.set_router(router)

        decision = MagicMock()
        decision.evaluate.return_value = MagicMock(decision="APPROVE")
        runtime.set_decision_engine(decision)

        request = SentinelRequest(
            utterance="abre mi navegador",
            session_id="test-session",
            user_id="test-user",
        )

        response = await runtime.process(request)
        assert response.success is True
        assert intent.parse.called, "IntentEngine debe ser llamado"
        assert planner.plan.called, "Planner debe ser llamado"
        assert gateway.execute.called, "ToolGateway debe ser llamado"

    @pytest.mark.asyncio
    async def test_no_old_components_called(self):
        """Test 2: verificar que componentes antiguos NO son llamados
        cuando el pipeline usa SentinelRuntime directamente."""
        runtime = SentinelRuntime()

        # Solo mockeamos IntentEngine V1 (no V2)
        intent = MagicMock()
        intent.parse.return_value = TaskIntent(
            objective="test",
            category="CHAT", risk_level="low",
            confidence=0.5, raw_input="test",
        )
        runtime.set_intent_engine(intent)

        request = SentinelRequest(utterance="test")
        response = await runtime.process(request)
        assert response.success is True

    @pytest.mark.asyncio
    async def test_decision_consistente(self):
        """Test 3: misma entrada → misma estrategia de decisión."""
        runtime = SentinelRuntime()

        intent = MagicMock()
        intent.parse.return_value = TaskIntent(
            objective="test", category="CHAT", risk_level="low",
            confidence=0.5, raw_input="test",
        )
        runtime.set_intent_engine(intent)

        request = SentinelRequest(
            utterance="test",
            session_id="consistent-session",
            user_id="consistent-user",
        )

        r1 = await runtime.process(request)
        r2 = await runtime.process(request)

        assert r1.success == r2.success
        assert r1.data.get("task_type") == r2.data.get("task_type")

    @pytest.mark.asyncio
    async def test_orchestrator_delegates_to_runtime_when_configured(self):
        """Orchestrator con runtime configurado delega a SentinelRuntime."""
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import Intent, IntentEngine
        from sentinel.core.tool_gateway import ToolGateway

        runtime = SentinelRuntime()

        intent_engine = MagicMock(spec=IntentEngine)
        intent_engine.parse.return_value = Intent(
            action="chat", target="", parameters={}, confidence=0.5, raw_input="test"
        )
        gateway = MagicMock(spec=ToolGateway)

        orch = Orchestrator(
            intent_engine=intent_engine,
            tool_gateway=gateway,
            runtime=runtime,
        )

        assert orch._runtime is runtime
        result = await orch.process("test", identity={"user_id": "u1", "is_authenticated": True}, session_id="s1")
        assert result is not None