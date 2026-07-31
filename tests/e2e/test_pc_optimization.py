"""Caso 3 — Optimización Gaming.

Entrada: "Optimiza mi PC para gaming"
Pipeline: Intent → Hardware Analysis → Profile Selection → Optimization Plan → User Confirmation → Execution → Verification

NO debe ejecutar comandos aleatorios — debe crear un plan estructurado con reversión.
"""

import pytest
from tests.e2e.fixtures.sentinel_test_environment import (
    create_sentinel_runtime,
    StubContextEngine,
    StubToolGateway,
)
from sentinel.testing.assertions import E2EAssertions as A


@pytest.fixture
def runtime():
    return create_sentinel_runtime(auto_approve=True)


def _inner(data: dict) -> dict:
    return data.get("data", data) if isinstance(data, dict) else {}


@pytest.mark.e2e
class TestPcOptimization:
    @pytest.mark.asyncio
    async def test_intent_detected_as_system_optimization(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-intent", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        intent_str = str(_inner(data).get("intent", ""))
        assert "configure" in intent_str.lower() or "SYSTEM_OPERATION" in intent_str, f"Expected SYSTEM_OPERATION/configure intent: {intent_str}"

    @pytest.mark.asyncio
    async def test_hardware_analysis(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        ctx = StubContextEngine()
        runtime.set_context_engine(ctx)

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-hw", user_id="test")
        await runtime.process(req)

        assert ctx.call_count > 0, "ContextEngine was not called for hardware analysis"

    @pytest.mark.asyncio
    async def test_gaming_profile_activated(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-profile", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        assert "gaming" in plan_str.lower() or "high_performance" in plan_str.lower(), f"Gaming profile not found in plan: {plan_str[:200]}"
        A.assert_plan_has_steps(_inner(data), min_steps=1)

    @pytest.mark.asyncio
    async def test_snapshot_created_for_rollback(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-rollback", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        assert "snapshot" in plan_str.lower(), f"No snapshot step in plan: {plan_str[:200]}"

    @pytest.mark.asyncio
    async def test_no_random_commands(self, runtime):
        """El plan no debe contener ejecuciones de comandos aleatorios."""
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-safe", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        dangerous = ["delete", "format", "rm ", "shutdown", "reg delete", "taskkill /f"]
        for cmd in dangerous:
            assert cmd not in plan_str.lower(), f"Plan contiene comando peligroso: {cmd}"

    @pytest.mark.asyncio
    async def test_processes_and_services_optimized(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-procs", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        assert "process" in plan_str.lower() or "service" in plan_str.lower() or "optimize" in plan_str.lower(), f"Process/service optimization not in plan: {plan_str[:200]}"

    @pytest.mark.asyncio
    async def test_verification_step_exists(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Optimiza mi PC para gaming", session_id="e2e-optim-verify", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        assert "verify" in plan_str.lower() or "verification" in plan_str.lower(), f"No verification step in plan: {plan_str[:200]}"
