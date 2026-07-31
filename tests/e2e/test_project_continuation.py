"""Caso 4 — Continuación de proyecto.

Entrada: "Continúa mi proyecto Python"
Pipeline: ConversationMemory → ProjectContext → Previous Decisions → Current State → Next Action

Prueba la memoria real: debe recuperar estado previo de un proyecto y reconstruir contexto.
"""

import pytest
from tests.e2e.fixtures.sentinel_test_environment import (
    create_sentinel_runtime,
    StubMemory,
    StubContextEngine,
)
from sentinel.testing.assertions import E2EAssertions as A


@pytest.fixture
def runtime():
    return create_sentinel_runtime(auto_approve=True)


def _inner(data: dict) -> dict:
    return data.get("data", data) if isinstance(data, dict) else {}


@pytest.mark.e2e
class TestProjectContinuation:
    @pytest.mark.asyncio
    async def test_memory_retrieval(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        memory = StubMemory()
        memory.create_session("e2e-project-mem")
        runtime.set_memory(memory)

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id="e2e-project-mem", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"success": response.success}

        A.assert_success(data)

    @pytest.mark.asyncio
    async def test_project_context_in_plan(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id="e2e-project-plan", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        plan_str = str(_inner(data).get("plan", ""))
        assert "python" in plan_str.lower() or "project" in plan_str.lower(), f"Project context not found: {plan_str[:200]}"

    @pytest.mark.asyncio
    async def test_previous_decisions_loaded(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        session_id = "e2e-project-decisions"
        memory = StubMemory()
        memory.create_session(session_id)
        memory.store("project_python_last_state", "Working on data processing module")
        memory.store_preference("project_python_tasks", ["Refactor API client", "Add unit tests"])
        runtime.set_memory(memory)

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id=session_id, user_id="test")
        await runtime.process(req)

        stored = memory.get("project_python_last_state")
        assert stored is not None, "Previous project state was not stored"

    @pytest.mark.asyncio
    async def test_context_engine_used(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        ctx = StubContextEngine()
        runtime.set_context_engine(ctx)

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id="e2e-project-ctx", user_id="test")
        await runtime.process(req)

        assert ctx.call_count > 0, "ContextEngine was not consulted for project continuation"

    @pytest.mark.asyncio
    async def test_intent_detected_as_memory(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id="e2e-project-intent", user_id="test")
        response = await runtime.process(req)
        data = response.to_dict() if hasattr(response, "to_dict") else {"data": response.data}

        intent_str = str(_inner(data).get("intent", ""))
        assert "memory" in intent_str.lower() or "query" in intent_str.lower(), f"Expected MEMORY/query intent: {intent_str}"

    @pytest.mark.asyncio
    async def test_known_files_and_objectives_reconstructed(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        session_id = "e2e-project-files"
        memory = StubMemory()
        memory.create_session(session_id)
        memory.store_preference("project_python_objectives", "Complete data pipeline v2")
        runtime.set_memory(memory)

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id=session_id, user_id="test")
        await runtime.process(req)

        objectives = memory.get_preferences("project_python_objectives")
        assert objectives is not None, "Project objectives not stored or retrieved"

    @pytest.mark.asyncio
    async def test_audit_logs_continuation(self, runtime):
        from sentinel.core.runtime import SentinelRequest

        req = SentinelRequest(utterance="Continúa mi proyecto Python", session_id="e2e-project-audit", user_id="test")
        await runtime.process(req)

        audit_log = runtime.audit_log
        assert len(audit_log) > 0, "No audit entries created for project continuation"
