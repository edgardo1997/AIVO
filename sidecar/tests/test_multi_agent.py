"""Tests for sentinel.core.multi_agent."""
import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock, patch
from sentinel.core.multi_agent import (
    MultiAgentOrchestrator, SubTask, SubTaskResult, DecompositionResult, MultiAgentResult,
)
from sentinel.core.agent import AgentSpec, AgentStatus, AgentRegistry


def make_agent(agent_id="agent-a", provider="ollama", model="llama3", capabilities=None):
    return AgentSpec(
        id=agent_id, name=agent_id, provider=provider, model=model,
        capabilities=capabilities or [],
        status=AgentStatus.ACTIVE,
    )


class TestIsComplex:
    def test_short_task_is_not_complex(self):
        ma = MultiAgentOrchestrator()
        assert not ma._is_complex("hello world")

    def test_long_task_is_complex(self):
        ma = MultiAgentOrchestrator()
        assert ma._is_complex(" ".join(["word"] * 15))

    def test_keyword_research_is_complex(self):
        ma = MultiAgentOrchestrator()
        assert ma._is_complex("research this topic thoroughly")

    def test_keyword_analyze_is_complex(self):
        ma = MultiAgentOrchestrator()
        assert ma._is_complex("analyze the results")

    def test_empty_is_not_complex(self):
        ma = MultiAgentOrchestrator()
        assert not ma._is_complex("")
        assert not ma._is_complex(None)


class TestDefaultDecompose:
    def test_simple_task_passthrough(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("show cpu info")
        assert len(result.sub_tasks) == 1
        assert result.sub_tasks[0].id == "st_main"
        assert result.decomposition_method == "passthrough"

    def test_research_task(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("research and investigate the system performance")
        ids = [st.id for st in result.sub_tasks]
        assert "st_research" in ids

    def test_analyze_task(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("analyze the data from the experiment")
        ids = [st.id for st in result.sub_tasks]
        assert "st_analyze" in ids

    def test_design_task(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("design a solution for the architecture")
        ids = [st.id for st in result.sub_tasks]
        assert "st_design" in ids

    def test_complex_pipeline(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("research, analyze, and design a complete system")
        ids = [st.id for st in result.sub_tasks]
        assert "st_research" in ids
        assert "st_analyze" in ids
        assert "st_design" in ids

    def test_dependencies_set_correctly(self):
        ma = MultiAgentOrchestrator()
        result = ma._default_decompose("research and analyze the problem")
        st_map = {st.id: st for st in result.sub_tasks}
        if "st_analyze" in st_map and "st_research" in st_map:
            assert "st_research" in st_map["st_analyze"].dependencies


class TestAssignAgents:
    def test_no_registry_leaves_agent_none(self):
        ma = MultiAgentOrchestrator()
        st = SubTask(id="t1", description="test")
        result = ma.assign_agents([st])
        assert result[0].agent_id is None

    def test_with_registry_assigns_agent(self):
        registry = AgentRegistry()
        registry.register(make_agent("agent-1"))
        ma = MultiAgentOrchestrator(agent_registry=registry)
        st = SubTask(id="t1", description="do something")
        result = ma.assign_agents([st])
        assert result[0].agent_id == "agent-1"

    def test_preserves_existing_agent_id(self):
        registry = AgentRegistry()
        registry.register(make_agent("agent-1"))
        ma = MultiAgentOrchestrator(agent_registry=registry)
        st = SubTask(id="t1", description="test", agent_id="custom")
        result = ma.assign_agents([st])
        assert result[0].agent_id == "custom"

    def test_no_match_returns_none(self):
        registry = AgentRegistry()
        ma = MultiAgentOrchestrator(agent_registry=registry)
        st = SubTask(id="t1", description="test")
        result = ma.assign_agents([st])
        assert result[0].agent_id is None


class TestExecuteSingle:
    @pytest.mark.asyncio
    async def test_no_execute_fn_passthrough(self):
        ma = MultiAgentOrchestrator()
        st = SubTask(id="t1", description="test", agent_id="a1")
        result = await ma._run_sub_task(st, {})
        assert result.success
        assert "[passthrough]" in result.data["response"]

    @pytest.mark.asyncio
    async def test_execute_fn_success(self):
        def fake_execute(agent_id, task, ctx):
            return {"response": "done", "agent_id": agent_id}
        ma = MultiAgentOrchestrator(execute_agent_fn=fake_execute)
        st = SubTask(id="t1", description="test task", agent_id="a1")
        result = await ma._run_sub_task(st, {})
        assert result.success
        assert result.data["response"] == "done"

    @pytest.mark.asyncio
    async def test_execute_fn_error(self):
        def fake_execute(agent_id, task, ctx):
            return {"error": "something went wrong"}
        ma = MultiAgentOrchestrator(execute_agent_fn=fake_execute)
        st = SubTask(id="t1", description="test", agent_id="a1")
        result = await ma._run_sub_task(st, {})
        assert not result.success
        assert "something went wrong" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_fn_exception(self):
        def fake_execute(agent_id, task, ctx):
            raise RuntimeError("crash")
        ma = MultiAgentOrchestrator(execute_agent_fn=fake_execute)
        st = SubTask(id="t1", description="test", agent_id="a1")
        result = await ma._run_sub_task(st, {})
        assert not result.success
        assert "crash" in (result.error or "")


class TestExecuteMulti:
    @pytest.mark.asyncio
    async def test_simple_task_passthrough(self):
        ma = MultiAgentOrchestrator()
        result = await ma.execute("show disk usage")
        assert result.success
        assert len(result.sub_task_results) == 1
        assert result.sub_task_results[0].sub_task_id == "st_main"

    @pytest.mark.asyncio
    async def test_multi_sub_task_with_execution(self):
        def fake_execute(agent_id, task, ctx):
            return {"response": f"result from {agent_id}: {task[:20]}"}
        registry = AgentRegistry()
        registry.register(make_agent("agent-1"))
        registry.register(make_agent("agent-2"))
        ma = MultiAgentOrchestrator(
            agent_registry=registry,
            execute_agent_fn=fake_execute,
        )
        result = await ma.execute("research and analyze the current situation")
        assert len(result.sub_task_results) >= 2

    @pytest.mark.asyncio
    async def test_empty_decomposition_returns_error(self):
        def empty_decompose(task, ctx):
            return DecompositionResult(sub_tasks=[], decomposition_method="test")
        ma = MultiAgentOrchestrator(decompose_fn=empty_decompose)
        result = await ma.execute("anything")
        assert not result.success
        assert "no sub-tasks" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_circular_dependency_detected(self):
        ma = MultiAgentOrchestrator()
        # manually create circular dependency
        st1 = SubTask(id="a", description="task a", dependencies=["b"])
        st2 = SubTask(id="b", description="task b", dependencies=["a"])
        result = await ma._execute_multi([st1, st2], "test", {}, 0)
        assert not result.success
        assert "circular" in (result.error or "").lower()


class TestDefaultMerge:
    def test_merge_single_success(self):
        r = [SubTaskResult(sub_task_id="t1", success=True, data={"response": "hello"})]
        merged = MultiAgentOrchestrator._default_merge("test", r)
        assert merged["output"] == "hello"
        assert merged["success_count"] == 1

    def test_merge_multiple(self):
        r = [
            SubTaskResult(sub_task_id="t1", success=True, data={"response": "part1"}),
            SubTaskResult(sub_task_id="t2", success=True, data={"response": "part2"}),
        ]
        merged = MultiAgentOrchestrator._default_merge("test", r)
        assert "part1" in merged["output"]
        assert "part2" in merged["output"]

    def test_merge_with_errors(self):
        r = [
            SubTaskResult(sub_task_id="t1", success=True, data={"response": "ok"}),
            SubTaskResult(sub_task_id="t2", success=False, error="fail"),
        ]
        merged = MultiAgentOrchestrator._default_merge("test", r)
        assert "ok" in merged["output"]
        assert "fail" in merged["output"]
        assert merged["success_count"] == 1

    def test_merge_empty(self):
        merged = MultiAgentOrchestrator._default_merge("test", [])
        assert merged["output"] == ""


class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_process_multi_agent_no_orchestrator(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, multi_agent_orchestrator=None)
        result = await orch.process_multi_agent("test")
        assert not result.tool_result or not result.tool_result.success
        assert "not configured" in (result.error or "")

    @pytest.mark.asyncio
    async def test_process_multi_agent_with_orchestrator(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.multi_agent import MultiAgentOrchestrator
        from sentinel.core.agent import AgentRegistry, AgentSpec, AgentStatus

        def fake_execute(agent_id, task, ctx):
            return {"response": f"result from {agent_id}"}

        registry = AgentRegistry()
        registry.register(AgentSpec(id="test-agent", name="test", provider="ollama", model="llama3", status=AgentStatus.ACTIVE))
        ma = MultiAgentOrchestrator(agent_registry=registry, execute_agent_fn=fake_execute)
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, multi_agent_orchestrator=ma)
        result = await orch.process_multi_agent("show disk info")
        assert result.tool_result is not None
        assert result.tool_result.success

    @pytest.mark.asyncio
    async def test_process_multi_agent_property(self):
        from sentinel.core.orchestrator import Orchestrator
        from sentinel.core.intent import IntentEngine
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.multi_agent import MultiAgentOrchestrator
        gw = MagicMock(spec=ToolGateway)
        gw.execute = AsyncMock()
        ma = MultiAgentOrchestrator()
        orch = Orchestrator(intent_engine=IntentEngine(), tool_gateway=gw, multi_agent_orchestrator=ma)
        assert orch.multi_agent is ma
