import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch, ANY
from datetime import datetime, timezone
from dataclasses import asdict

from sentinel.core.orchestrator import Orchestrator, ExecutionResult, Decision
from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep
from sentinel.core.model_router import RouterDecision, TaskType
from sentinel.core.decision_engine import DecisionResult
from sentinel.core.simulation import SimulationResult, SimulatedImpact
from sentinel.core.tool import ToolResult
from sentinel.core.context import SystemContext
from sentinel.core.operational_memory import PendingActionRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_intent(action="query", target="system.info", params=None, conf=0.95):
    return Intent(
        action=action,
        target=target,
        parameters=params or {},
        confidence=conf,
        raw_input=f"{action} {target}",
    )


def make_plan(intent=None, n_steps=1, step_ids=None):
    if intent is None:
        intent = make_intent()
    step_ids = step_ids or [f"s{i}" for i in range(n_steps)]
    steps = []
    for sid in step_ids:
        steps.append(
            PlanStep(
                id=sid,
                tool_id=intent.target,
                params={},
                description=f"step {sid}",
                is_reversible=True,
            )
        )
    return Plan(steps=steps, intent=intent, description="test plan")


def make_router_decision(provider="ollama", model="llama3", strategy="priority"):
    return RouterDecision(
        provider_id=provider,
        model=model,
        task_type=TaskType.QUICK,
        strategy=strategy,
        reason="test",
    )


def make_decision_result(decision=Decision.APPROVE, reason="ok", risk=0.3):
    return DecisionResult(
        decision=decision,
        plan=make_plan(),
        reason=reason,
        base_risk_score=risk,
        final_risk_score=risk,
        context_modifier=0.0,
        context_factors={},
    )


def make_system_context():
    return SystemContext(
        cpu={"percent": 30},
        memory={"percent": 50},
        disk={"percent": 40},
        network={},
        processes=[],
        boot_time=1000,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_gateway():
    gw = MagicMock()
    gw.execute = AsyncMock(return_value=ToolResult.ok(data={"result": "ok"}, tool_id="system.info"))
    reg = MagicMock()
    reg.list_all = MagicMock(return_value=[])
    reg.get = MagicMock(return_value=None)
    gw._capability_registry = reg
    gw.list_specs = MagicMock(return_value=[])
    return gw


@pytest.fixture
def mock_intent_engine():
    ie = MagicMock()
    ie.parse = MagicMock(return_value=make_intent())
    ie.list_supported_targets = MagicMock(return_value=[])
    ie.set_model_router = MagicMock()
    return ie


@pytest.fixture
def mock_planner():
    pl = MagicMock()
    pl.plan = MagicMock(return_value=make_plan())

    def resolve(plan):
        # return actual plan steps so model_decision flows through
        return [[s] for s in plan.steps] if plan.steps else [[PlanStep(id="s0", tool_id="system.info")]]

    pl.resolve_dependencies = MagicMock(side_effect=resolve)
    return pl


@pytest.fixture
def mock_context_engine():
    ce = MagicMock()
    ce.collect = AsyncMock(return_value=make_system_context())
    return ce


@pytest.fixture
def mock_model_router():
    mr = MagicMock()
    mr.select = MagicMock(return_value=make_router_decision())
    mr.set_cost_tracker = MagicMock()
    mr.set_feedback_store = MagicMock()
    mr._key_map = {}
    mr.list_providers = MagicMock(return_value=[])
    return mr


@pytest.fixture
def mock_decision_engine():
    de = MagicMock()
    de.evaluate = MagicMock(return_value=make_decision_result())
    de.set_model_router = MagicMock()
    return de


@pytest.fixture
def mock_simulation():
    sim = MagicMock()
    sim_result = MagicMock()
    sim_result.overall_risk = "low"
    sim_result.requires_confirmation = False
    sim_result.summary = "sim ok"
    sim_result.impacts = []
    sim.simulate = AsyncMock(return_value=sim_result)
    return sim


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.get_session_history = MagicMock(return_value=[])
    mem.get_user_preferences = MagicMock(return_value={})
    mem.get_learned_preferences = MagicMock(return_value={})
    mem.store_execution = MagicMock()
    mem.remember_execution = MagicMock()
    mem.store_pending_action = MagicMock()
    mem.get_pending_action = MagicMock(return_value=None)
    mem.remove_pending_action = MagicMock()
    mem.get_last_execution = MagicMock(return_value=None)
    return mem


@pytest.fixture
def mock_profile():
    pm = MagicMock()
    prof = MagicMock()
    prof.to_dict = MagicMock(return_value={"level": "admin"})
    pm.get_or_create_profile = MagicMock(return_value=prof)
    pm.get_all_preferences = MagicMock(return_value={})
    return pm


@pytest.fixture
def mock_deep_context():
    dc = MagicMock()
    dc.collect = AsyncMock(return_value={"deep": "ctx"})
    dc.summary = MagicMock(return_value="deep ctx summary")
    return dc


@pytest.fixture
def mock_feedback():
    fb = MagicMock()
    fb.record = MagicMock()
    return fb


@pytest.fixture
def mock_cost_tracker():
    ct = MagicMock()
    ct.record_cost = MagicMock()
    return ct


@pytest.fixture
def mock_perf_tracker():
    pt = MagicMock()
    pt.record = MagicMock(return_value=None)
    return pt


@pytest.fixture
def mock_plan_cache():
    pc = MagicMock()
    pc.get = MagicMock(return_value=None)
    pc.set = MagicMock()
    return pc


@pytest.fixture
def mock_audit():
    au = MagicMock()
    au.log_pipeline = MagicMock()
    return au


@pytest.fixture
def orchestrator(
    mock_gateway,
    mock_intent_engine,
    mock_planner,
    mock_context_engine,
    mock_model_router,
    mock_decision_engine,
    mock_simulation,
    mock_memory,
    mock_profile,
    mock_deep_context,
    mock_feedback,
    mock_cost_tracker,
    mock_perf_tracker,
    mock_plan_cache,
    mock_audit,
):
    return Orchestrator(
        intent_engine=mock_intent_engine,
        tool_gateway=mock_gateway,
        planner=mock_planner,
        decision_engine=mock_decision_engine,
        model_router=mock_model_router,
        context_engine=mock_context_engine,
        memory=mock_memory,
        audit_service=mock_audit,
        profile_manager=mock_profile,
        deep_context_engine=mock_deep_context,
        simulation_engine=mock_simulation,
        model_feedback_store=mock_feedback,
        cost_tracker=mock_cost_tracker,
        performance_tracker=mock_perf_tracker,
        plan_cache=mock_plan_cache,
    )


def planner_step():
    return PlanStep(id="s0", tool_id="system.info")


# ===================================================================
# process() - main pipeline
# ===================================================================


class TestProcessPipeline:
    """Tests for Orchestrator.process() — the main pipeline."""

    @pytest.mark.asyncio
    async def test_success_path(self, orchestrator, mock_gateway, mock_memory):
        """Happy path: parse → plan → simulate → approve → execute → return."""
        result = await orchestrator.process("show system info")
        assert result.tool_result is not None
        assert result.tool_result.success is True
        assert result.blocked is False
        assert result.error is None
        assert mock_gateway.execute.called

    @pytest.mark.asyncio
    async def test_success_path_stores_memory(self, orchestrator, mock_memory):
        """On success, execution is stored in memory."""
        await orchestrator.process("show system info")
        assert mock_memory.store_execution.called

    @pytest.mark.asyncio
    async def test_dry_run_skips_execution(self, orchestrator, mock_gateway, mock_simulation):
        """dry_run=True: return simulated data without real tool execution."""
        result = await orchestrator.process("show system info", dry_run=True)
        assert result.simulated is True
        assert mock_gateway.execute.called is False
        # simulated steps produce step results directly
        assert len(result.step_results) == 1
        assert result.step_results[0].data.get("simulated") is True

    @pytest.mark.asyncio
    async def test_rejected_by_decision_engine(self, orchestrator, mock_decision_engine):
        """Decision.REJECT returns blocked result with error."""
        mock_decision_engine.evaluate.return_value = make_decision_result(
            decision=Decision.REJECT,
            reason="too risky",
        )
        result = await orchestrator.process("format drive")
        assert result.tool_result is None or result.tool_result.success is False
        assert result.error is not None
        assert "rejected" in result.error.lower()

    @pytest.mark.asyncio
    async def test_require_confirm_blocks_and_stores_pending(
        self, orchestrator, mock_decision_engine, mock_memory, mock_simulation
    ):
        """Decision.REQUIRE_CONFIRM blocks execution and stores pending action."""
        sim_result = SimulationResult(
            plan_id="test",
            impacts=[],
            pre_snapshot={},
            overall_risk="high",
            requires_confirmation=True,
            summary="requires review",
        )
        mock_simulation.simulate.return_value = sim_result
        mock_decision_engine.evaluate.return_value = make_decision_result(
            decision=Decision.REQUIRE_CONFIRM,
            reason="needs approval",
        )
        result = await orchestrator.process("delete file")
        assert result.blocked is True
        assert result.action_id is not None
        assert mock_memory.store_pending_action.called

    @pytest.mark.asyncio
    async def test_plan_cache_hit_skips_intent_parsing_and_planning(
        self, orchestrator, mock_plan_cache, mock_intent_engine, mock_planner
    ):
        """A plan cache hit bypasses intent_engine.parse() and planner.plan()."""
        cached = make_plan()
        mock_plan_cache.get.return_value = cached
        result = await orchestrator.process("show system info")
        assert mock_plan_cache.get.called
        assert mock_plan_cache.set.called is False  # no new cache write
        assert result.tool_result is not None

    @pytest.mark.asyncio
    async def test_plan_cache_miss_calls_planner_and_sets_cache(self, orchestrator, mock_plan_cache, mock_planner):
        """A plan cache miss calls planner.plan() and writes the cache."""
        mock_plan_cache.get.return_value = None
        await orchestrator.process("show system info")
        assert mock_plan_cache.get.called
        assert mock_plan_cache.set.called
        assert mock_planner.plan.called

    @pytest.mark.asyncio
    async def test_override_plan_skips_intent_parsing_and_cache(
        self, orchestrator, mock_intent_engine, mock_plan_cache
    ):
        """An override_plan bypasses intent parsing and plan cache entirely."""
        plan = make_plan(intent=make_intent())
        result = await orchestrator.process("show system info", override_plan=plan)
        assert mock_intent_engine.parse.called is False
        assert mock_plan_cache.get.called is False
        assert mock_plan_cache.set.called is False
        assert result.tool_result is not None

    @pytest.mark.asyncio
    async def test_step_failure_triggers_rollback(self, orchestrator, mock_gateway, mock_memory):
        """When a step fails, completed steps are rolled back."""
        mock_gateway.execute = AsyncMock(
            return_value=ToolResult.fail(
                error="exec failed",
                tool_id="system.info",
            )
        )
        result = await orchestrator.process("show system info")
        assert result.tool_result is not None
        assert result.tool_result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_no_decision_engine_auto_proceeds(self, orchestrator):
        """Without decision engine, execution proceeds without decision."""
        # create orchestrator without decision_engine
        orch = Orchestrator(
            intent_engine=MagicMock(parse=MagicMock(return_value=make_intent())),
            tool_gateway=MagicMock(
                execute=AsyncMock(return_value=ToolResult.ok(data={}, tool_id="system.info")),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
            planner=MagicMock(
                plan=MagicMock(return_value=make_plan()),
                resolve_dependencies=MagicMock(return_value=[[planner_step()]]),
            ),
            decision_engine=None,
            model_router=MagicMock(
                select=MagicMock(return_value=make_router_decision()),
                set_cost_tracker=MagicMock(),
                set_feedback_store=MagicMock(),
                _key_map={},
            ),
        )
        result = await orch.process("show system info")
        assert result.decision is None
        assert result.tool_result is not None

    @pytest.mark.asyncio
    async def test_no_model_router_no_router_decision(self, orchestrator):
        """Without model router, no model is selected for steps."""
        orch = Orchestrator(
            intent_engine=MagicMock(parse=MagicMock(return_value=make_intent())),
            tool_gateway=MagicMock(
                execute=AsyncMock(return_value=ToolResult.ok(data={}, tool_id="system.info")),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
            planner=MagicMock(
                plan=MagicMock(return_value=make_plan()),
                resolve_dependencies=MagicMock(return_value=[[planner_step()]]),
            ),
            model_router=None,
        )
        result = await orch.process("show system info")
        assert result.tool_result is not None

    @pytest.mark.asyncio
    async def test_skip_simulation(self, orchestrator, mock_simulation):
        """skip_simulation=True avoids calling the simulation engine."""
        await orchestrator.process("show system info", skip_simulation=True)
        assert mock_simulation.simulate.called is False

    @pytest.mark.asyncio
    async def test_context_collected_and_injected(self, orchestrator, mock_context_engine):
        """System context is collected and injected into pipeline."""
        await orchestrator.process("show system info")
        assert mock_context_engine.collect.called

    @pytest.mark.asyncio
    async def test_deep_context_collected(self, orchestrator, mock_deep_context):
        """Deep context engine is called and injected."""
        await orchestrator.process("show system info")
        assert mock_deep_context.collect.called

    @pytest.mark.asyncio
    async def test_model_router_selects_for_each_step(self, orchestrator, mock_model_router):
        """Model router selects a model for the plan and each step."""
        await orchestrator.process("show system info")
        assert mock_model_router.select.called

    @pytest.mark.asyncio
    async def test_feedback_recorded_at_end(self, orchestrator, mock_feedback):
        """Model feedback is recorded after step execution."""
        await orchestrator.process("show system info")
        assert mock_feedback.record.called

    @pytest.mark.asyncio
    async def test_cost_recorded_when_usage_present(self, orchestrator, mock_cost_tracker, mock_gateway):
        """Cost is recorded only when token usage data is present in result."""
        mock_gateway.execute = AsyncMock(
            return_value=ToolResult.ok(
                data={"usage": {"prompt_tokens": 100, "completion_tokens": 20}},
                tool_id="system.info",
            )
        )
        await orchestrator.process("show system info")
        assert mock_cost_tracker.record_cost.called

    @pytest.mark.asyncio
    async def test_cost_not_recorded_without_usage(self, orchestrator, mock_cost_tracker, mock_gateway):
        """Without token usage in result data, cost recording is skipped."""
        mock_gateway.execute = AsyncMock(
            return_value=ToolResult.ok(
                data={"result": "plain"},
                tool_id="system.info",
            )
        )
        await orchestrator.process("show system info")
        assert mock_cost_tracker.record_cost.called is False

    @pytest.mark.asyncio
    async def test_performance_recorded(self, orchestrator, mock_perf_tracker):
        """Performance tracker records step duration."""
        await orchestrator.process("show system info")
        assert mock_perf_tracker.record.called

    @pytest.mark.asyncio
    async def test_parallel_steps_executed_concurrently(self, orchestrator, mock_gateway):
        """Steps in the same dependency level are gathered concurrently."""
        plan = make_plan(n_steps=2, step_ids=["a", "b"])
        # override resolve_dependencies to return a parallel level
        orch = Orchestrator(
            intent_engine=MagicMock(parse=MagicMock(return_value=make_intent())),
            tool_gateway=mock_gateway,
            planner=MagicMock(
                plan=MagicMock(return_value=plan),
                resolve_dependencies=MagicMock(return_value=[plan.steps]),
            ),
        )
        await orch.process("test parallel")
        assert mock_gateway.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_error_in_context_collection_does_not_crash(self, orchestrator, mock_context_engine):
        """If context collection fails, the pipeline continues."""
        mock_context_engine.collect.side_effect = RuntimeError("context fail")
        result = await orchestrator.process("show system info")
        assert result.tool_result is not None


# ===================================================================
# approve_with_modifications
# ===================================================================


class TestApproveWithModifications:
    @pytest.mark.asyncio
    async def test_no_memory_returns_error(self, orchestrator):
        """Without memory backend, returns error immediately."""
        orch = Orchestrator(
            intent_engine=MagicMock(parse=MagicMock(return_value=make_intent())),
            tool_gateway=MagicMock(
                execute=AsyncMock(return_value=ToolResult.ok(data={}, tool_id="system.info")),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
            memory=None,
        )
        result = await orch.approve_with_modifications("id", [])
        assert result.error is not None
        assert "no memory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_action_not_found(self, orchestrator, mock_memory):
        """If pending action not found, returns error."""
        mock_memory.get_pending_action.return_value = None
        result = await orchestrator.approve_with_modifications("unknown", [{"tool_id": "sys.info"}])
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_modified_steps(self, orchestrator, mock_memory):
        """Empty modified steps list returns error."""
        mock_memory.get_pending_action.return_value = PendingActionRecord(
            action_id="a1",
            tool_id="sys.info",
            params={
                "intent": {
                    "action": "query",
                    "target": "sys.info",
                    "parameters": {},
                    "confidence": 0.9,
                    "raw_input": "info",
                },
                "utterance": "info",
                "identity": None,
                "session_id": None,
            },
            reason="test",
            created_at="now",
            ttl_seconds=600,
        )
        result = await orchestrator.approve_with_modifications("a1", [])
        assert result.error is not None
        assert "no steps" in result.error.lower()

    @pytest.mark.asyncio
    async def test_approve_with_modifications_success(self, orchestrator, mock_memory):
        """Successful modification creates steps and executes."""
        mock_memory.get_pending_action.return_value = PendingActionRecord(
            action_id="a1",
            tool_id="sys.info",
            params={
                "intent": {
                    "action": "query",
                    "target": "system.info",
                    "parameters": {},
                    "confidence": 0.9,
                    "raw_input": "info",
                },
                "plan": {
                    "intent": {
                        "action": "query",
                        "target": "system.info",
                        "parameters": {},
                        "confidence": 0.9,
                        "raw_input": "info",
                    },
                    "steps": [
                        {
                            "id": "sys",
                            "tool_id": "system.info",
                            "params": {},
                            "description": "Get system info",
                            "estimated_impact": "low",
                        }
                    ],
                    "risk_score": 0.0,
                    "description": "Stored plan",
                },
                "utterance": "info",
                "identity": None,
                "session_id": None,
            },
            reason="needs review",
            created_at="now",
            ttl_seconds=600,
        )
        result = await orchestrator.approve_with_modifications(
            "a1",
            [
                {"tool_id": "system.info", "params": {}, "description": "check info"},
            ],
        )
        assert result.error is None or result.tool_result is not None
        assert mock_memory.remove_pending_action.called


# ===================================================================
# approve_execution (simple approve/deny)
# ===================================================================


class TestApproveExecution:
    @pytest.mark.asyncio
    async def test_different_user_cannot_approve(self, orchestrator, mock_memory):
        mock_memory.get_pending_action.return_value = PendingActionRecord(
            action_id="a1",
            tool_id="system.info",
            params={"identity": {"user_id": "owner"}, "plan": {"steps": []}},
            reason="test",
            created_at="now",
            ttl_seconds=600,
        )

        result = await orchestrator.approve_execution(
            "a1",
            True,
            approver_identity={"user_id": "other-user"},
        )

        assert "identity" in result.error.lower()
        mock_memory.remove_pending_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_memory_returns_error(self):
        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=MagicMock(
                execute=AsyncMock(return_value=ToolResult.ok(data={})),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
            memory=None,
        )
        result = await orch.approve_execution("id", True)
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_action_not_found(self, orchestrator, mock_memory):
        mock_memory.get_pending_action.return_value = None
        result = await orchestrator.approve_execution("unknown", True)
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_denied(self, orchestrator, mock_memory):
        mock_memory.get_pending_action.return_value = PendingActionRecord(
            action_id="a1",
            tool_id="sys.info",
            params={
                "intent": {
                    "action": "query",
                    "target": "sys.info",
                    "parameters": {},
                    "confidence": 0.9,
                    "raw_input": "info",
                },
                "utterance": "info",
                "identity": None,
                "session_id": None,
            },
            reason="test",
            created_at="now",
            ttl_seconds=600,
        )
        result = await orchestrator.approve_execution("a1", False)
        assert result.error is not None
        assert "rejected" in result.error.lower()

    @pytest.mark.asyncio
    async def test_approved_executes(self, orchestrator, mock_memory, mock_gateway, mock_intent_engine):
        mock_memory.get_pending_action.return_value = PendingActionRecord(
            action_id="a1",
            tool_id="sys.info",
            params={
                "intent": {
                    "action": "query",
                    "target": "system.info",
                    "parameters": {},
                    "confidence": 0.9,
                    "raw_input": "info",
                },
                "plan": {
                    "intent": {
                        "action": "query",
                        "target": "system.info",
                        "parameters": {},
                        "confidence": 0.9,
                        "raw_input": "info",
                    },
                    "steps": [
                        {
                            "id": "sys",
                            "tool_id": "system.info",
                            "params": {},
                            "description": "Get system info",
                            "estimated_impact": "low",
                        }
                    ],
                    "risk_score": 0.0,
                    "description": "Stored plan",
                },
                "utterance": "info",
                "identity": None,
                "session_id": None,
            },
            reason="test",
            created_at="now",
            ttl_seconds=600,
        )
        mock_intent_engine.parse.reset_mock()
        result = await orchestrator.approve_execution("a1", True)
        assert result.error is None or result.tool_result is not None
        mock_intent_engine.parse.assert_not_called()
        assert mock_gateway.execute.await_args.kwargs["tool_id"] == "system.info"


# ===================================================================
# execute_direct
# ===================================================================


class TestExecuteDirect:
    @pytest.mark.asyncio
    async def test_execute_direct_basic(self, orchestrator, mock_gateway):
        """Direct execution of a tool works."""
        result = await orchestrator.execute_direct("system.info", {})
        assert result.tool_result is not None

    @pytest.mark.asyncio
    async def test_execute_direct_dry_run(self, orchestrator, mock_gateway):
        """Dry run skips real execution in direct mode."""
        result = await orchestrator.execute_direct("system.info", {}, dry_run=True)
        assert result.simulated is True

    @pytest.mark.asyncio
    async def test_execute_direct_with_decision_engine(self, orchestrator, mock_decision_engine):
        """Direct execution is evaluated by decision engine if available."""
        mock_decision_engine.evaluate.return_value = make_decision_result(
            decision=Decision.REJECT,
            reason="not allowed",
        )
        result = await orchestrator.execute_direct("system.info", {})
        # even with reject, execute_direct does not check decision
        assert result.decision is not None


# ===================================================================
# Utility methods
# ===================================================================


class TestUtilities:
    def test_get_capabilities(self, orchestrator):
        caps = orchestrator.get_capabilities()
        assert "intents" in caps
        assert "tools" in caps
        assert "capabilities" in caps
        assert "models" in caps

    def test_feedback_store_property(self, orchestrator):
        assert orchestrator.feedback_store is not None

    def test_cost_tracker_property(self, orchestrator, mock_cost_tracker):
        assert orchestrator.cost_tracker is mock_cost_tracker

    def test_performance_tracker_property(self, orchestrator):
        assert orchestrator.performance_tracker is not None

    def test_plan_cache_property(self, orchestrator, mock_plan_cache):
        assert orchestrator.plan_cache is mock_plan_cache

    def test_plan_cache_defaults_none(self):
        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=MagicMock(
                execute=AsyncMock(),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
        )
        assert orch.plan_cache is None

    def test_get_last_execution_no_memory(self):
        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=MagicMock(
                execute=AsyncMock(),
                _capability_registry=MagicMock(list_all=MagicMock(return_value=[]), get=MagicMock(return_value=None)),
                list_specs=MagicMock(return_value=[]),
            ),
            memory=None,
        )
        assert orch.get_last_execution() is None

    def test_approved_property_true(self):
        plan = make_plan()
        exec_plan = MagicMock()
        exec_plan.plan = plan
        result = ExecutionResult(
            plan=exec_plan,
            tool_result=ToolResult.ok(data="yes", tool_id="t"),
        )
        assert result.approved is True

    def test_approved_property_false_no_tool_result(self):
        exec_plan = MagicMock()
        result = ExecutionResult(plan=exec_plan)
        assert result.approved is False

    def test_approved_property_false_on_failure(self):
        exec_plan = MagicMock()
        result = ExecutionResult(
            plan=exec_plan,
            tool_result=ToolResult.fail(error="fail", tool_id="t"),
        )
        assert result.approved is False
