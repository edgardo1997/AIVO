"""Tests for the SimulationEngine."""

import pytest

from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.simulation import SimulationEngine


@pytest.fixture
def engine():
    return SimulationEngine()


@pytest.mark.asyncio
async def test_simulate_read_only(engine):
    plan = Plan(
        steps=[PlanStep(id="s1", tool_id="system.info", description="Get system info")],
        intent=Intent(action="query", target="system"),
    )
    result = await engine.simulate(plan, {})
    assert result.overall_risk == "low"
    assert result.requires_confirmation is False
    assert len(result.impacts) == 1
    assert result.impacts[0].impact_level == "none"


@pytest.mark.asyncio
async def test_simulate_file_write(engine):
    plan = Plan(
        steps=[
            PlanStep(
                id="s1",
                tool_id="filesystem.write",
                description="Write file",
                params={"path": "/tmp/test.txt", "content": "hello world"},
            ),
        ],
        intent=Intent(action="execute", target="filesystem"),
    )
    result = await engine.simulate(plan, {})
    assert result.overall_risk == "high"
    assert result.requires_confirmation is True
    assert "/tmp/test.txt" in result.impacts[0].files_affected


@pytest.mark.asyncio
async def test_simulate_destructive_command(engine):
    plan = Plan(
        steps=[
            PlanStep(id="s1", tool_id="executor.command", description="Run command", params={"command": "rm -rf /"}),
        ],
        intent=Intent(action="execute", target="executor"),
    )
    result = await engine.simulate(plan, {})
    assert result.overall_risk == "critical"
    assert result.requires_confirmation is True
    assert len(result.impacts[0].warnings) > 0


@pytest.mark.asyncio
async def test_simulate_irreversible(engine):
    plan = Plan(
        steps=[
            PlanStep(
                id="s1", tool_id="filesystem.delete", description="Delete file", params={"path": "/data/db.sqlite"}
            )
        ],
        intent=Intent(action="execute", target="filesystem"),
    )
    result = await engine.simulate(plan, {})
    assert result.overall_risk == "critical"
    assert result.requires_confirmation is True
    assert result.impacts[0].irreversible is False  # filesystem.delete now backs up to temp


@pytest.mark.asyncio
async def test_simulate_empty_plan(engine):
    plan = Plan(steps=[], intent=Intent(action="query", target="system"))
    result = await engine.simulate(plan, {})
    assert result.overall_risk == "low"
    assert result.requires_confirmation is False
    assert len(result.impacts) == 0


@pytest.mark.asyncio
async def test_simulate_high_cpu_context(engine):
    plan = Plan(
        steps=[PlanStep(id="s1", tool_id="executor.command", description="Heavy task", params={"command": "compile"})],
        intent=Intent(action="execute", target="executor"),
    )
    result = await engine.simulate(plan, {"system_summary": {"cpu_percent": 95}})
    assert any("CPU" in w for w in result.impacts[0].warnings)


@pytest.mark.asyncio
async def test_simulate_summary_format(engine):
    plan = Plan(
        steps=[PlanStep(id="s1", tool_id="system.info", description="Check health")],
        intent=Intent(action="query", target="system"),
    )
    result = await engine.simulate(plan, {})
    assert "Simulation:" in result.summary
    assert "low" in result.summary.lower()
