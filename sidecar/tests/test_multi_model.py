import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import ANY, MagicMock
import pytest

from sentinel.core.model_router import ModelRouter, TaskType, RouterDecision
from sentinel.core.planner import PlanStep, Planner
from sentinel.core.intent import Intent
from sentinel.core.orchestrator import Orchestrator, TOOL_TO_TASK
from sentinel.core.tool_gateway import ToolGateway


class TestRouterDecisionToDict:
    def test_to_dict_converts_task_type_enum(self):
        d = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="test",
        ).to_dict()
        assert d == {
            "provider_id": "ollama",
            "model": "llama3",
            "task_type": "quick",
            "strategy": "priority",
            "reason": "test",
        }

    def test_to_dict_json_serializable(self):
        import json
        d = RouterDecision(
            provider_id="openrouter", model="gpt-4o",
            task_type=TaskType.CODE, strategy="smart",
            reason="smart selected",
        ).to_dict()
        s = json.dumps(d)
        assert "gpt-4o" in s
        assert "code" in s


class TestToolToTaskMapping:
    def test_quick_tools(self):
        assert TOOL_TO_TASK["system.cpu"] == TaskType.QUICK
        assert TOOL_TO_TASK["system.info"] == TaskType.QUICK
        assert TOOL_TO_TASK["system.processes"] == TaskType.QUICK
        assert TOOL_TO_TASK["filesystem.delete"] == TaskType.QUICK

    def test_analysis_tools(self):
        assert TOOL_TO_TASK["filesystem.search"] == TaskType.ANALYSIS

    def test_code_tools(self):
        assert TOOL_TO_TASK["filesystem.write"] == TaskType.CODE

    def test_reasoning_tools(self):
        assert TOOL_TO_TASK["executor.command"] == TaskType.REASONING
        assert TOOL_TO_TASK["executor.launch"] == TaskType.REASONING


class TestPlanStepHasModelDecision:
    def test_default_is_none(self):
        step = PlanStep(id="s1", tool_id="system.cpu", description="cpu")
        assert step.model_decision is None

    def test_can_set_router_decision(self):
        decision = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="test",
        )
        step = PlanStep(id="s1", tool_id="system.cpu", description="cpu",
                        model_decision=decision)
        assert step.model_decision is decision
        assert step.model_decision.provider_id == "ollama"


class TestOrchestratorMultiModel:
    def test_per_step_model_decision_set_on_multi_step_plan(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test"}
        router.select.return_value = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="mock",
        )

        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="query", target="system.health",
            parameters={}, confidence=0.9, raw_input="check health",
        )

        import asyncio
        result = asyncio.run(orch.process("check health", skip_simulation=True))

        plan_steps = result.plan.plan.steps
        assert len(plan_steps) >= 2
        for step in plan_steps:
            assert step.model_decision is not None
            assert step.model_decision.provider_id == "ollama"

    def test_different_tools_get_different_model_decisions(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test", "openrouter": "sk-test"}
        router.select.side_effect = lambda tt, context=None: RouterDecision(
            provider_id="ollama" if tt == TaskType.QUICK else "openrouter",
            model="llama3" if tt == TaskType.QUICK else "gpt-4o",
            task_type=tt, strategy="priority",
            reason=f"mock for {tt.value}",
        )

        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="execute", target="executor.launch",
            parameters={"command": "notepad"}, confidence=0.9,
            raw_input="launch notepad",
        )

        import asyncio
        result = asyncio.run(orch.process("launch notepad", skip_simulation=True))

        plan_steps = result.plan.plan.steps
        assert len(plan_steps) >= 2
        assert plan_steps[0].tool_id == "system.processes"
        assert plan_steps[1].tool_id == "executor.launch"
        assert plan_steps[0].model_decision is not None
        assert plan_steps[1].model_decision is not None

        router.select.assert_any_call(TaskType.QUICK, context=ANY)
        router.select.assert_any_call(TaskType.REASONING, context=ANY)

    def test_step_context_includes_model_decision(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test"}
        router.select.return_value = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="mock",
        )

        executed_contexts = []
        gateway = ToolGateway()
        original_execute = gateway.execute

        async def tracking_execute(tool_id, params, context):
            executed_contexts.append(context.get("model_decision"))
            return await original_execute(tool_id, params, context)

        gateway.execute = tracking_execute

        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=gateway,
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="query", target="system.cpu",
            parameters={}, confidence=0.9, raw_input="cpu",
        )

        import asyncio
        asyncio.run(orch.process("cpu", skip_simulation=True))

        assert len(executed_contexts) >= 1
        md = executed_contexts[0]
        assert md is not None
        assert md["provider_id"] == "ollama"
        assert md["model"] == "llama3"
        assert md["task_type"] == "quick"

    def test_plan_to_dict_serializes_model_decision_safely(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test"}
        router.select.return_value = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="mock",
        )

        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="query", target="system.cpu",
            parameters={}, confidence=0.9, raw_input="cpu",
        )

        import asyncio
        import json
        result = asyncio.run(orch.process("cpu", skip_simulation=True))

        plan_dict = orch._plan_to_dict(result.plan.plan)
        step_md = plan_dict["steps"][0].get("model_decision")
        assert step_md is not None
        assert step_md["task_type"] == "quick"
        assert step_md["provider_id"] == "ollama"
        json.dumps(plan_dict)
