from unittest.mock import AsyncMock

import pytest

from sentinel.core.intent import Intent
from sentinel.core.orchestrator import Orchestrator, StepResult
from sentinel.core.planner import Plan, Planner, PlanStep
from sentinel.core.recovery import FallbackHandler, RecoveryPolicy, RetryHandler, RollbackManager
from sentinel.core.tool import ToolResult


def make_plan(steps):
    intent = Intent(action="execute", target="workflow", parameters={}, confidence=1.0, raw_input="workflow")
    return Plan(steps=steps, intent=intent, description="test workflow")


def test_dependency_graph_resolves_parallel_levels():
    plan = make_plan([
        PlanStep(id="a", tool_id="system.info"),
        PlanStep(id="b", tool_id="system.cpu"),
        PlanStep(id="c", tool_id="system.processes", depends_on=["a", "b"]),
    ])
    levels = Planner().resolve_dependencies(plan)
    assert [[step.id for step in level] for level in levels] == [["a", "b"], ["c"]]


@pytest.mark.parametrize("steps", [
    [PlanStep(id="a", tool_id="x", depends_on=["missing"])],
    [PlanStep(id="a", tool_id="x", depends_on=["b"]), PlanStep(id="b", tool_id="y", depends_on=["a"])],
    [PlanStep(id="same", tool_id="x"), PlanStep(id="same", tool_id="y")],
])
def test_invalid_dependency_graph_is_rejected(steps):
    assert Planner().resolve_dependencies(make_plan(steps)) == []


def test_parallel_failure_cannot_be_overwritten_by_later_success():
    failed = StepResult(step_id="a", tool_id="x", success=False, error="failed")
    succeeded = StepResult(step_id="b", tool_id="y", success=True, data={"ok": True})
    merged = Orchestrator._merge_tool_result(Orchestrator._merge_tool_result(None, failed), succeeded)
    assert merged.success is False
    assert merged.error == "failed"


@pytest.mark.asyncio
async def test_transient_step_records_retry_attempts():
    gateway = AsyncMock()
    gateway.execute.side_effect = [
        ToolResult.fail(error="service unavailable", tool_id="system.info"),
        ToolResult.ok(data={"ok": True}, tool_id="system.info"),
    ]
    orchestrator = object.__new__(Orchestrator)
    orchestrator._tool_gateway = gateway
    orchestrator._retry_handler = RetryHandler()
    orchestrator._fallback_handler = FallbackHandler()
    orchestrator._feedback = None
    orchestrator._cost_tracker = None
    orchestrator._perf_tracker = None
    step = PlanStep(id="read", tool_id="system.info", recovery_policy=RecoveryPolicy(max_retries=2, retry_delay_ms=0))
    intent = Intent(action="query", target="system.info", parameters={}, confidence=1.0, raw_input="status")

    result = await orchestrator._execute_single_step(step, intent, {})

    assert result.success is True
    assert result.attempts == 2
    assert result.recovery_strategy == "retry"


@pytest.mark.asyncio
async def test_rollback_runs_successful_steps_in_reverse_order():
    calls = []
    async def execute(tool_id, params):
        calls.append(tool_id)
        return ToolResult.ok(data={}, tool_id=tool_id)
    completed = [
        (PlanStep(id="one", tool_id="write.one", is_reversible=True, rollback_tool_id="undo.one"), ToolResult.ok(data={}, tool_id="write.one")),
        (PlanStep(id="two", tool_id="write.two", is_reversible=True, rollback_tool_id="undo.two"), ToolResult.ok(data={}, tool_id="write.two")),
    ]
    actions = await RollbackManager().rollback(completed, execute)
    assert calls == ["undo.two", "undo.one"]
    assert all(action.success for action in actions)
