import asyncio
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging
import uuid

from .intent import Intent, IntentEngine
from .model_router import ModelRouter, TaskType, RouterDecision
from .tool_gateway import ToolGateway
from .context import ContextEngine
from .tool import ToolResult
from .planner import Planner, Plan, PlanStep
from .decision_engine import Decision, DecisionEngine, DecisionResult
from .operational_memory import MemoryBackend, ExecutionRecord, PendingActionRecord
from .model_feedback import ModelFeedbackStore
from .cost_tracker import CostTracker
from .performance_tracker import PerformanceTracker
from .plan_cache import PlanCache
from .recovery import RetryHandler, FallbackHandler, RollbackManager, RecoveryPolicy, RetryExhaustedError
from .rate_limiter import RateLimiter, RateLimitDecision, DEFAULT_LIMITS
from .multi_agent import MultiAgentOrchestrator
from .offline_queue import OfflineQueue, QueueItem
from .network_monitor import NetworkMonitor
from .alerting import AlertManager, AlertSeverity

logger = logging.getLogger(__name__)


INTENT_TO_TASK: Dict[str, TaskType] = {
    "query": TaskType.QUICK,
    "execute": TaskType.REASONING,
    "analyze": TaskType.ANALYSIS,
    "configure": TaskType.REASONING,
    "control": TaskType.QUICK,
}

TOOL_TO_TASK: Dict[str, TaskType] = {
    "system.cpu": TaskType.QUICK,
    "system.info": TaskType.QUICK,
    "system.processes": TaskType.QUICK,
    "system.network": TaskType.QUICK,
    "filesystem.search": TaskType.ANALYSIS,
    "filesystem.write": TaskType.CODE,
    "filesystem.delete": TaskType.QUICK,
    "executor.command": TaskType.REASONING,
    "executor.launch": TaskType.REASONING,
    "executor.kill": TaskType.QUICK,
}

INTENT_TO_TOOL: Dict[str, str] = {
    "system.cpu": "system.cpu",
    "system.memory": "system.info",
    "system.disk": "system.info",
    "system.processes": "system.processes",
    "system.network": "system.info",
    "system.info": "system.info",
    "system.health": "system.info",
    "system.uptime": "system.info",
    "models.list": "system.info",
    "settings.ai": "system.info",
    "executor.command": "executor.command",
    "executor.kill": "executor.kill",
}


@dataclass
class ExecutionPlan:
    intent: Intent
    plan: Plan
    tool_id: str
    tool_params: Dict[str, Any]
    task_type: TaskType
    router_decision: Optional[RouterDecision] = None


@dataclass
class StepResult:
    step_id: str
    tool_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    requires_confirmation: bool = False
    policy_result: Optional[Dict[str, Any]] = None
    quality_result: Optional[Dict[str, Any]] = None
    attempts: int = 0
    recovery_strategy: str = "none"
    executed_tool_id: Optional[str] = None
    status: str = "completed"


@dataclass
class ExecutionResult:
    plan: ExecutionPlan
    decision: Optional[DecisionResult] = None
    tool_result: Optional[ToolResult] = None
    error: Optional[str] = None
    step_results: List[StepResult] = field(default_factory=list)
    simulated: bool = False
    blocked: bool = False
    action_id: Optional[str] = None
    simulation_summary: str = ""
    rate_limited: bool = False
    retry_after: float = 0.0
    rollback_actions: List[Dict[str, Any]] = field(default_factory=list)
    advisory: Optional[Any] = None

    @property
    def approved(self) -> bool:
        return bool(self.tool_result and self.tool_result.success)


class Orchestrator:
    def __init__(
        self,
        intent_engine: IntentEngine,
        tool_gateway: ToolGateway,
        planner: Optional[Planner] = None,
        decision_engine: Optional[DecisionEngine] = None,
        model_router: Optional[ModelRouter] = None,
        context_engine: Optional[ContextEngine] = None,
        memory: Optional[MemoryBackend] = None,
        audit_service: Optional[Any] = None,
        profile_manager: Optional[Any] = None,
        deep_context_engine: Optional[Any] = None,
        simulation_engine: Optional[Any] = None,
        model_feedback_store: Optional[ModelFeedbackStore] = None,
        cost_tracker: Optional[CostTracker] = None,
        performance_tracker: Optional[PerformanceTracker] = None,
        plan_cache: Optional[PlanCache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        multi_agent_orchestrator: Optional[MultiAgentOrchestrator] = None,
        offline_queue: Optional[OfflineQueue] = None,
        network_monitor: Optional[NetworkMonitor] = None,
        skill_engine: Optional[Any] = None,
        alert_manager: Optional[AlertManager] = None,
        knowledge_base: Optional[Any] = None,
        file_pipeline: Optional[Any] = None,
        web_browsing: Optional[Any] = None,
        hardening: Optional[Any] = None,
        advisory_service: Optional[Any] = None,
        process_timeout: Optional[float] = 60.0,
    ):
        self._process_timeout = process_timeout
        self._intent_engine = intent_engine
        self._tool_gateway = tool_gateway
        self._planner = planner or Planner()
        self._decision_engine = decision_engine
        self._model_router = model_router
        self._context_engine = context_engine
        self._memory = memory
        self._audit_service = audit_service
        self._profile_manager = profile_manager
        self._deep_context = deep_context_engine
        self._simulation = simulation_engine
        self._feedback = model_feedback_store or ModelFeedbackStore()
        self._cost_tracker = cost_tracker
        self._perf_tracker = performance_tracker or PerformanceTracker()
        self._plan_cache = plan_cache
        self._rate_limiter = rate_limiter
        self._multi_agent = multi_agent_orchestrator
        self._offline_queue = offline_queue
        self._network_monitor = network_monitor
        self._skill_engine = skill_engine
        self._knowledge_base = knowledge_base
        self._file_pipeline = file_pipeline
        self._web_browsing = web_browsing
        self._hardening = hardening
        self._advisory = advisory_service
        self._alert_manager = alert_manager or AlertManager()
        if self._cost_tracker:
            self._alert_manager.set_cost_tracker(self._cost_tracker)
        if self._perf_tracker:
            self._alert_manager.set_performance_tracker(self._perf_tracker)
        if self._offline_queue and self._network_monitor:
            self._network_monitor.on_transition(self._on_network_transition)
        if self._model_router and self._cost_tracker:
            self._model_router.set_cost_tracker(self._cost_tracker)
        if self._model_router:
            self._model_router.set_feedback_store(self._feedback)
        if model_router and model_router._key_map:
            self._intent_engine.set_model_router(model_router)
            if self._decision_engine:
                self._decision_engine.set_model_router(model_router)
        self._retry_handler = RetryHandler()
        self._fallback_handler = FallbackHandler()
        self._rollback_manager = RollbackManager()

    async def process(
        self, utterance: str, *, identity: Optional[dict] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
        skip_simulation: bool = False,
        override_plan: Optional[Plan] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        effective_timeout = timeout if timeout is not None else self._process_timeout
        if effective_timeout is not None and effective_timeout > 0:
            result = await asyncio.wait_for(
                self._process_impl(utterance, identity=identity, session_id=session_id,
                                   dry_run=dry_run, skip_simulation=skip_simulation,
                                   override_plan=override_plan),
                timeout=effective_timeout,
            )
        else:
            result = await self._process_impl(utterance, identity=identity, session_id=session_id,
                                              dry_run=dry_run, skip_simulation=skip_simulation,
                                              override_plan=override_plan)
        return self._attach_advisory(result)

    async def _process_impl(
        self, utterance: str, *, identity: Optional[dict] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
        skip_simulation: bool = False,
        override_plan: Optional[Plan] = None,
    ) -> ExecutionResult:
        execution_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        context: Dict[str, Any] = {"execution_id": execution_id, "session_id": session_id}
        if identity is not None:
            context["identity"] = identity

        if self._rate_limiter:
            try:
                global_limit = DEFAULT_LIMITS.get("global", 60)
                dec = self._rate_limiter.allow("global", limit=global_limit)
                if not dec.allowed:
                    logger.warning("Rate limit exceeded for global key (retry_after=%.0fs)", dec.retry_after)
                    return ExecutionResult(
                        plan=ExecutionPlan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                                           plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                                           tool_id="", tool_params={}, task_type=TaskType.QUICK),
                        error=f"Rate limit exceeded. Retry after {dec.retry_after}s",
                        rate_limited=True, retry_after=dec.retry_after,
                    )
                if session_id:
                    session_limit = DEFAULT_LIMITS.get("session", 20)
                    dec = self._rate_limiter.allow(f"session:{session_id}", limit=session_limit)
                    if not dec.allowed:
                        logger.warning("Rate limit exceeded for session %s", session_id)
                        return ExecutionResult(
                            plan=ExecutionPlan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                                               plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                                               tool_id="", tool_params={}, task_type=TaskType.QUICK),
                            error=f"Session rate limit exceeded. Retry after {dec.retry_after}s",
                            rate_limited=True, retry_after=dec.retry_after,
                        )
            except Exception as e:
                logger.warning("Rate limiter check failed: %s", e)

        if self._context_engine:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
                context["system_summary"] = sys_ctx.summary()
            except Exception as e:
                logger.warning("Context collection failed: %s", e)

        if session_id and self._memory:
            try:
                history = self._memory.get_session_history(session_id, limit=5)
                if history:
                    context["session_history"] = [
                        {
                            "utterance": h.utterance,
                            "intent": h.intent.get("action"),
                            "target": h.intent.get("target"),
                            "success": h.tool_result.get("success") if h.tool_result else None,
                            "error": h.error,
                        }
                        for h in history
                    ]
                    context["session_history_count"] = len(history)
                    logger.info("Injected %d past executions for session %s", len(history), session_id)
                prefs = self._memory.get_user_preferences(session_id)
                if prefs:
                    context["user_preferences"] = prefs
            except Exception as e:
                logger.warning("Session context retrieval failed: %s", e)

        if self._profile_manager and identity is not None:
            try:
                user_id = identity.get("user_id") if isinstance(identity, dict) else getattr(identity, "user_id", None)
                if user_id:
                    profile = self._profile_manager.get_or_create_profile(user_id)
                    context["user_profile"] = profile.to_dict()
                    user_prefs = self._profile_manager.get_all_preferences(user_id)
                    if user_prefs:
                        context["user_preferences_v2"] = user_prefs
            except Exception as e:
                logger.warning("Profile context injection failed: %s", e)

        if self._memory and identity is not None:
            try:
                user_id = identity.get("user_id") if isinstance(identity, dict) else getattr(identity, "user_id", None)
                if user_id:
                    learned = self._memory.get_learned_preferences(user_id)
                    if learned:
                        # Learned memory is advisory context only.  PolicyEngine and
                        # DecisionEngine remain the authorities for every action.
                        context["learned_preferences"] = {
                            key: {"value": pref.value, "source": pref.source, "confidence": pref.confidence}
                            for key, pref in learned.items()
                        }
            except Exception as e:
                logger.warning("Learned memory injection failed: %s", e)

        if self._deep_context:
            try:
                deep_ctx = await self._deep_context.collect()
                context["deep_context"] = deep_ctx
                context["deep_context_summary"] = self._deep_context.summary(deep_ctx)
                logger.info("Deep context injected: %s", deep_ctx.get("deep_context_summary", ""))
            except Exception as e:
                logger.warning("Deep context injection failed: %s", e)

        if override_plan:
            intent = override_plan.intent
            plan = override_plan
            logger.info("Using override plan with %d steps for %s", len(plan.steps), utterance)
        else:
            intent = self._intent_engine.parse(utterance, context)
            logger.info(
                "Parsed intent: %s -> %s/%s (conf=%.2f)",
                utterance, intent.action, intent.target, intent.confidence,
            )

            cached_plan = self._plan_cache.get(intent) if self._plan_cache else None
            if cached_plan:
                plan = cached_plan
                logger.info("Plan cache HIT for %s/%s", intent.action, intent.target)
            else:
                plan = self._planner.plan(intent, context)
                if self._plan_cache:
                    self._plan_cache.set(intent, plan)

        exec_plan = self._build_exec_plan(intent, plan, context)

        simulation_result = None
        if self._simulation and not dry_run and not skip_simulation:
            try:
                simulation_result = await self._simulation.simulate(plan, context)
                context["simulation"] = {
                    "overall_risk": simulation_result.overall_risk,
                    "requires_confirmation": simulation_result.requires_confirmation,
                    "summary": simulation_result.summary,
                    "impact_count": len(simulation_result.impacts),
                    "has_irreversible": any(i.irreversible for i in simulation_result.impacts),
                }
                logger.info(
                    "Simulation: risk=%s, confirm=%s, steps=%d",
                    simulation_result.overall_risk,
                    simulation_result.requires_confirmation,
                    len(simulation_result.impacts),
                )
            except Exception as e:
                logger.warning("Simulation failed: %s", e)

        decision: Optional[DecisionResult] = None
        if self._decision_engine:
            decision = self._decision_engine.evaluate(plan, context)
            context["decision"] = asdict(decision)

        if self._model_router:
            try:
                exec_plan.router_decision = self._model_router.select(exec_plan.task_type, context=context)
                for step in plan.steps:
                    step_task = TOOL_TO_TASK.get(step.tool_id, exec_plan.task_type)
                    step.model_decision = self._model_router.select(step_task, context=context)
            except RuntimeError as exc:
                logger.info("No model route available; local tool plan remains executable: %s", exc)

        if decision and decision.decision == Decision.REJECT:
            logger.warning("Execution REJECTED by decision engine: %s", decision.reason)
            result = ExecutionResult(
                plan=exec_plan, decision=decision, simulated=True,
                blocked=False, error=f"Execution rejected: {decision.reason}",
            )
            self._store_memory(execution_id, start, utterance, intent, plan, decision, context, result)
            return result

        if decision and decision.decision == Decision.REQUIRE_CONFIRM:
            action_id = f"sim_{uuid.uuid4().hex[:12]}"
            reason = decision.reason
            if simulation_result:
                reason = simulation_result.summary
            pending = PendingActionRecord(
                action_id=action_id,
                tool_id=exec_plan.tool_id,
                params={
                    "utterance": utterance,
                    "identity": identity,
                    "session_id": session_id,
                    "intent": asdict(intent),
                    "plan": self._plan_to_dict(plan),
                    "simulation": asdict(simulation_result) if simulation_result else None,
                    "context": context,
                },
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat(),
                ttl_seconds=600,
            )
            if self._memory:
                self._memory.store_pending_action(pending)
            sim_summary = simulation_result.summary if simulation_result else decision.reason
            logger.warning("Execution BLOCKED: %s (action_id=%s)", reason, action_id)
            result = ExecutionResult(
                plan=exec_plan, decision=decision, simulated=True,
                blocked=True, action_id=action_id,
                simulation_summary=sim_summary,
                error=f"Execution blocked: {reason}",
            )
            self._store_memory(execution_id, start, utterance, intent, plan, decision, context, result)
            return result

        step_results: List[StepResult] = []
        tool_result: Optional[ToolResult] = None
        executed: List[Tuple[PlanStep, StepResult]] = []
        rollback_actions: List[Dict[str, Any]] = []

        levels = self._planner.resolve_dependencies(plan)
        if plan.steps and not levels:
            tool_result = ToolResult.fail(error="Invalid plan dependency graph", tool_id="planner")
        for level in levels:
            if len(level) == 1:
                step = level[0]
                s_result = await self._execute_single_step(step, intent, context, dry_run=dry_run)
                step_results.append(s_result)
                tool_result = self._merge_tool_result(tool_result, s_result)
                executed.append((step, s_result))
                if not s_result.success and not dry_run:
                    rollback_actions.extend(asdict(action) for action in await self._rollback_completed(executed[:-1], context))
                    break
            else:
                tasks = [self._execute_single_step(s, intent, context, dry_run=dry_run) for s in level]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                all_ok = True
                for step, res in zip(level, results):
                    if isinstance(res, Exception):
                        step_results.append(StepResult(
                            step_id=step.id, tool_id=step.tool_id,
                            success=False, error=str(res),
                        ))
                        executed.append((step, step_results[-1]))
                        all_ok = False
                        if not tool_result:
                            tool_result = ToolResult(success=False, error=str(res), tool_id=step.tool_id)
                    else:
                        step_results.append(res)
                        tool_result = self._merge_tool_result(tool_result, res)
                        executed.append((step, res))
                        if not res.success:
                            all_ok = False
                if not all_ok and not dry_run:
                    completed = [(s, r) for s, r in executed if r.success]
                    rollback_actions.extend(asdict(action) for action in await self._rollback_completed(completed, context))
                    break

        executed_ids = {step_result.step_id for step_result in step_results}
        if not dry_run and any(not item.success for item in step_results):
            for step in plan.steps:
                if step.id not in executed_ids:
                    step_results.append(StepResult(step_id=step.id, tool_id=step.tool_id, success=False,
                                                   error="Skipped because a dependency failed", status="skipped"))

        if tool_result:
            tool_result.duration_ms = sum(s.duration_ms or 0 for s in step_results if s.duration_ms)

        result = ExecutionResult(
            plan=exec_plan, decision=decision,
            tool_result=tool_result,
            error=(tool_result.error if tool_result and not tool_result.success else None),
            step_results=step_results,
            simulated=dry_run,
            rollback_actions=rollback_actions,
        )
        if not dry_run:
            self._store_memory(execution_id, start, utterance, intent, plan, decision, context, result)
        return result

    async def execute_direct(
        self,
        tool_id: str,
        params: dict,
        *,
        identity: Optional[dict] = None,
        utterance: str = "",
        dry_run: bool = False,
    ) -> ExecutionResult:
        execution_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        context: dict = {"execution_id": execution_id}

        if identity:
            context["identity"] = identity

        if self._context_engine:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
                context["system_summary"] = sys_ctx.summary()
            except Exception as e:
                logger.warning("Context collection failed: %s", e)

        raw_input = utterance or f"execute {tool_id}"
        intent = Intent(
            action="execute", target=tool_id,
            parameters=params, confidence=1.0,
            raw_input=raw_input,
        )
        plan = self._planner.plan(intent, context)
        if not plan.steps or any(step.tool_id != tool_id for step in plan.steps):
            plan = Plan(
                intent=intent,
                steps=[PlanStep(
                    id=f"{tool_id}_0", tool_id=tool_id,
                    description=f"Execute {tool_id}",
                    params=dict(params), estimated_impact="critical",
                )],
                risk_score=1.0,
                description=f"Structured execution of unregistered capability {tool_id}",
            )
        else:
            for step in plan.steps:
                step.params.update(params)

        exec_plan = self._build_exec_plan(intent, plan, context)
        if self._model_router:
            try:
                exec_plan.router_decision = self._model_router.select(exec_plan.task_type, context=context)
                for step in plan.steps:
                    step_task = TOOL_TO_TASK.get(step.tool_id, exec_plan.task_type)
                    step.model_decision = self._model_router.select(step_task, context=context)
            except RuntimeError as exc:
                logger.info("No model route available; direct local tool remains executable: %s", exc)

        decision: Optional[DecisionResult] = None
        if self._decision_engine:
            decision = self._decision_engine.evaluate(plan, context)
            context["decision"] = asdict(decision)

        step_results: List[StepResult] = []
        tool_result: Optional[ToolResult] = None
        executed: List[Tuple[PlanStep, StepResult]] = []
        rollback_actions: List[Dict[str, Any]] = []

        levels = self._planner.resolve_dependencies(plan)
        if plan.steps and not levels:
            tool_result = ToolResult.fail(error="Invalid plan dependency graph", tool_id="planner")
        for level in levels:
            if len(level) == 1:
                step = level[0]
                s_result = await self._execute_single_step(step, intent, context, dry_run=dry_run)
                step_results.append(s_result)
                tool_result = self._merge_tool_result(tool_result, s_result)
                executed.append((step, s_result))
                if not s_result.success and not dry_run:
                    rollback_actions.extend(asdict(action) for action in await self._rollback_completed(executed[:-1], context))
                    break
            else:
                tasks = [self._execute_single_step(s, intent, context, dry_run=dry_run) for s in level]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                all_ok = True
                for step, res in zip(level, results):
                    if isinstance(res, Exception):
                        step_results.append(StepResult(
                            step_id=step.id, tool_id=step.tool_id,
                            success=False, error=str(res),
                        ))
                        executed.append((step, step_results[-1]))
                        all_ok = False
                    else:
                        step_results.append(res)
                        tool_result = self._merge_tool_result(tool_result, res)
                        executed.append((step, res))
                        if not res.success:
                            all_ok = False
                if not all_ok and not dry_run:
                    completed = [(s, r) for s, r in executed if r.success]
                    rollback_actions.extend(asdict(action) for action in await self._rollback_completed(completed, context))
                    break

        executed_ids = {step_result.step_id for step_result in step_results}
        if not dry_run and any(not item.success for item in step_results):
            for step in plan.steps:
                if step.id not in executed_ids:
                    step_results.append(StepResult(step_id=step.id, tool_id=step.tool_id, success=False,
                                                   error="Skipped because a dependency failed", status="skipped"))

        result = ExecutionResult(
            plan=exec_plan, decision=decision,
            tool_result=tool_result,
            error=(tool_result.error if tool_result and not tool_result.success else None),
            step_results=step_results,
            simulated=dry_run,
            rollback_actions=rollback_actions,
        )
        if not dry_run:
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
        return self._attach_advisory(result)

    def _attach_advisory(self, result: ExecutionResult) -> ExecutionResult:
        """Attach read-only advice. Advisory failure must never affect execution."""
        if self._advisory is None or result.advisory is not None:
            return result
        try:
            result.advisory = self._advisory.analyze(result)
        except Exception as exc:
            logger.warning("Advisory analysis failed; execution result is unchanged: %s", exc)
        return result

    def _store_memory(
        self,
        execution_id: str,
        start: datetime,
        utterance: str,
        intent: Intent,
        plan: Plan,
        decision: Optional[DecisionResult],
        context: Dict[str, Any],
        result: ExecutionResult,
    ) -> None:
        duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        session_id = context.get("session_id")
        system_summary = dict(context.get("system_summary", {}))
        if result.rollback_actions:
            system_summary["rollback_actions"] = result.rollback_actions
        if session_id is not None:
            system_summary["session_id"] = session_id
        identity = context.get("identity")
        user_id = identity.get("user_id") if isinstance(identity, dict) else getattr(identity, "user_id", None)
        if user_id:
            system_summary["user_id"] = user_id
        if self._memory:
            plan_dict = self._plan_to_dict(plan)
            decision_dict = None
            if decision:
                decision_dict = asdict(decision)
                if "plan" in decision_dict:
                    decision_dict["plan"] = self._plan_to_dict(decision.plan)
            record = ExecutionRecord(
                execution_id=execution_id,
                timestamp=start.isoformat().replace("+00:00", "Z"),
                utterance=utterance,
                intent=asdict(intent),
                plan=plan_dict,
                decision=decision_dict,
                context_summary=system_summary,
                step_results=[asdict(sr) for sr in result.step_results],
                tool_result=asdict(result.tool_result) if result.tool_result else None,
                error=result.error,
                duration_ms=duration_ms,
            )
            try:
                self._memory.store_execution(record)
                if user_id:
                    self._memory.remember_execution(user_id, record)
            except Exception as e:
                logger.warning("Failed to store execution record: %s", e)
        if self._audit_service:
            try:
                tool_id = (plan.steps[0].tool_id if plan.steps else "")
                identity_data = context.get("identity", {})
                intent_data = asdict(intent) if intent else None
                decision_data = asdict(decision) if decision else None
                policy_data = result.tool_result.policy_result if result.tool_result else None
                quality_data = result.tool_result.quality_result if result.tool_result else None
                effective_error = result.error
                if not effective_error and result.tool_result and not result.tool_result.success:
                    effective_error = result.tool_result.error
                exec_data = {
                    "duration_ms": duration_ms,
                    "success": result.tool_result.success if result.tool_result else None,
                    "error": result.tool_result.error if result.tool_result else None,
                }
                self._audit_service.log_pipeline(
                    execution_id=execution_id,
                    identity=identity_data,
                    intent=intent_data,
                    decision=decision_data,
                    policy=policy_data,
                    execution=exec_data,
                    quality=quality_data,
                    tool_id=tool_id,
                    error=effective_error,
                )
            except Exception as e:
                logger.warning("Failed to log pipeline audit: %s", e)

    def _build_exec_plan(
        self, intent: Intent, plan: Plan, context: Dict[str, Any]
    ) -> ExecutionPlan:
        tool_id = INTENT_TO_TOOL.get(intent.target, "system.info")
        task_type = INTENT_TO_TASK.get(intent.action, TaskType.QUICK)

        params: Dict[str, Any] = {}
        if intent.target == "system.processes":
            params["limit"] = intent.parameters.get("limit", 10)
        elif intent.target == "executor.command":
            params["command"] = intent.parameters.get("command", "")
        elif intent.target == "executor.kill":
            params["pid"] = intent.parameters.get("pid")

        return ExecutionPlan(
            intent=intent,
            plan=plan,
            tool_id=tool_id,
            tool_params=params,
            task_type=task_type,
        )

    async def _execute_single_step(
        self, step: PlanStep, intent: Intent, context: Dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        step_context = context
        if step.model_decision:
            step_context = dict(context)
            step_context["model_decision"] = step.model_decision.to_dict()

        if dry_run:
            return StepResult(
                step_id=step.id, tool_id=step.tool_id, success=True,
                data={"simulated": True, "tool_id": step.tool_id,
                      "params": dict(step.params),
                      "description": step.description,
                      "model_decision": step_context.get("model_decision")},
            )
        step_params = dict(step.params)
        if step.tool_id == "executor.command":
            step_params.setdefault("command", intent.parameters.get("command", ""))
        elif step.tool_id == "executor.kill":
            step_params.setdefault("pid", intent.parameters.get("pid"))
        elif step.tool_id == "executor.launch":
            step_params.setdefault("command", intent.parameters.get("command", ""))
        elif step.tool_id == "filesystem.search":
            step_params.setdefault("pattern", intent.parameters.get("pattern", ""))
            step_params.setdefault("path", intent.parameters.get("path", ""))

        attempted_tools: List[str] = []
        async def _do_execute(tool_id: Optional[str] = None):
            attempted_tools.append(tool_id or step.tool_id)
            return await self._tool_gateway.execute(
                tool_id=tool_id or step.tool_id,
                params=step_params,
                context=step_context,
            )

        policy = step.recovery_policy or RecoveryPolicy.default_for(step.tool_id)
        try:
            s_result = await self._retry_handler.execute(
                lambda: _do_execute(step.tool_id), policy, tool_id=step.tool_id,
            )
        except RetryExhaustedError as e:
            s_result = ToolResult.fail(error=str(e), tool_id=step.tool_id)

        if not s_result.success and policy.fallback_tool_ids:
            fallback_fns = []
            for fb_tid in policy.fallback_tool_ids:
                if fb_tid != step.tool_id:
                    fallback_fns.append(lambda tid=fb_tid: _do_execute(tid))
            if fallback_fns:
                s_result = await self._fallback_handler.execute(
                    s_result, fallback_fns, policy, tool_id=step.tool_id,
                )

        if step.model_decision and self._feedback:
            try:
                self._feedback.record(
                    provider_id=step.model_decision.provider_id,
                    model=step.model_decision.model,
                    task_type=step.model_decision.task_type,
                    success=s_result.success,
                    duration_ms=s_result.duration_ms or 0.0,
                    error=s_result.error,
                )
            except Exception as e:
                logger.warning("Failed to record model feedback: %s", e)

        if step.model_decision and self._cost_tracker:
            try:
                usage = None
                if isinstance(s_result.data, dict):
                    usage = s_result.data.get("usage")
                prompt_tokens = 0
                completion_tokens = 0
                estimated = True
                if usage and isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens", 0) or 0
                    completion_tokens = usage.get("completion_tokens", 0) or 0
                    estimated = False
                if prompt_tokens > 0 or completion_tokens > 0:
                    self._cost_tracker.record_cost(
                        provider_id=step.model_decision.provider_id,
                        model=step.model_decision.model,
                        task_type=step.model_decision.task_type,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        error=s_result.error,
                        estimated=estimated,
                    )
            except Exception as e:
                logger.warning("Failed to record cost: %s", e)

        if step.model_decision and self._perf_tracker:
            try:
                alert = self._perf_tracker.record(
                    provider_id=step.model_decision.provider_id,
                    model=step.model_decision.model,
                    task_type=step.model_decision.task_type,
                    tool_id=step.tool_id,
                    duration_ms=s_result.duration_ms or 0.0,
                    success=s_result.success,
                )
                if alert:
                    logger.warning(
                        "Performance regression: %s/%s %s (%.0fms vs baseline %.0fms, +%.0f%%)",
                        alert.provider_id, alert.model, alert.tool_id,
                        alert.current_avg, alert.baseline_avg, alert.deviation_pct,
                    )
            except Exception as e:
                logger.warning("Failed to record performance: %s", e)

        recovery_strategy = "fallback" if s_result.tool_id and s_result.tool_id != step.tool_id else (
            "retry" if len(attempted_tools) > 1 else "none"
        )
        return StepResult(
            step_id=step.id,
            tool_id=step.tool_id,
            success=s_result.success,
            data=s_result.data,
            error=s_result.error,
            duration_ms=s_result.duration_ms,
            requires_confirmation=s_result.requires_confirmation,
            policy_result=s_result.policy_result,
            quality_result=s_result.quality_result,
            attempts=len(attempted_tools),
            recovery_strategy=recovery_strategy,
            executed_tool_id=s_result.tool_id or step.tool_id,
        )

    @staticmethod
    def _merge_tool_result(
        current: Optional[ToolResult], step_result: StepResult,
    ) -> ToolResult:
        if current is None:
            return ToolResult(
                success=step_result.success, data=step_result.data,
                error=step_result.error, tool_id=step_result.tool_id,
                duration_ms=step_result.duration_ms,
                requires_confirmation=step_result.requires_confirmation,
                policy_result=step_result.policy_result,
                quality_result=step_result.quality_result,
            )
        if not current.success or not step_result.success:
            return ToolResult(
                success=False, error=current.error or step_result.error,
                tool_id=current.tool_id,
                duration_ms=(current.duration_ms or 0) + (step_result.duration_ms or 0),
                requires_confirmation=current.requires_confirmation or step_result.requires_confirmation,
                policy_result=step_result.policy_result or current.policy_result,
                quality_result=step_result.quality_result or current.quality_result,
            )
        return ToolResult(
            success=True, data=step_result.data or current.data,
            tool_id=current.tool_id,
            duration_ms=(current.duration_ms or 0) + (step_result.duration_ms or 0),
            requires_confirmation=step_result.requires_confirmation,
            policy_result=step_result.policy_result or current.policy_result,
            quality_result=step_result.quality_result or current.quality_result,
        )

    @staticmethod
    def _plan_to_dict(plan: Plan) -> Dict[str, Any]:
        d = asdict(plan)
        for s in d.get("steps", []):
            md = s.get("model_decision")
            if md:
                tt = md.get("task_type")
                if isinstance(tt, TaskType):
                    md["task_type"] = tt.value
                elif hasattr(tt, "value"):
                    md["task_type"] = tt.value
        return d

    @staticmethod
    def _plan_from_dict(data: Dict[str, Any]) -> Plan:
        """Rebuild the immutable execution shape shown during confirmation."""
        intent_data = data.get("intent", {})
        intent = Intent(
            action=intent_data.get("action", ""),
            target=intent_data.get("target", ""),
            parameters=dict(intent_data.get("parameters", {})),
            confidence=float(intent_data.get("confidence", 0.0)),
            raw_input=intent_data.get("raw_input", ""),
        )
        steps = [
            PlanStep(
                id=step.get("id", f"step_{index}"),
                tool_id=step.get("tool_id", ""),
                params=dict(step.get("params", {})),
                description=step.get("description", ""),
                is_reversible=bool(step.get("is_reversible", False)),
                rollback_tool_id=step.get("rollback_tool_id"),
                rollback_params=step.get("rollback_params"),
                estimated_impact=step.get("estimated_impact", "low"),
                estimated_duration_ms=step.get("estimated_duration_ms"),
                depends_on=list(step.get("depends_on", [])),
            )
            for index, step in enumerate(data.get("steps", []))
        ]
        return Plan(
            intent=intent,
            steps=steps,
            risk_score=float(data.get("risk_score", 0.0)),
            estimated_duration_ms=data.get("estimated_duration_ms"),
            description=data.get("description", ""),
        )

    async def _rollback_completed(
        self,
        completed: List[Tuple[PlanStep, StepResult]],
        context: Dict[str, Any],
    ) -> List[Any]:
        async def _exec(tool_id: str, params: Dict[str, Any]):
            return await self._tool_gateway.execute(tool_id, params, context)
        return await self._rollback_manager.rollback(completed, _exec)

    async def approve_with_modifications(
        self,
        action_id: str,
        modified_steps: List[Dict[str, Any]],
        approver_identity: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        if not self._memory:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="No memory backend available for approval",
            )
        record = self._memory.get_pending_action(action_id)
        if record is None:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error=f"Pending action '{action_id}' not found or expired",
            )
        stored_identity = record.params.get("identity") or {}
        if approver_identity and stored_identity.get("user_id") != approver_identity.get("user_id"):
            empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=empty_intent, plan=Plan(intent=empty_intent, steps=[]),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="Approval identity does not match the user who requested the action",
            )
        self._memory.remove_pending_action(action_id)

        if not modified_steps:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="Modified plan has no steps",
            )

        intent_dict = record.params.get("intent", {})
        intent = Intent(
            action=intent_dict.get("action", ""),
            target=intent_dict.get("target", ""),
            parameters=intent_dict.get("parameters", {}),
            confidence=intent_dict.get("confidence", 0.0),
            raw_input=intent_dict.get("raw_input", ""),
        )

        new_steps = []
        for i, s in enumerate(modified_steps):
            new_steps.append(PlanStep(
                id=f"step_{i}",
                tool_id=s.get("tool_id", ""),
                params=s.get("params", {}),
                description=s.get("description", ""),
                is_reversible=s.get("is_reversible", False),
                rollback_tool_id=s.get("rollback_tool_id"),
                rollback_params=s.get("rollback_params"),
                estimated_impact=s.get("estimated_impact", "low"),
                estimated_duration_ms=s.get("estimated_duration_ms"),
                depends_on=s.get("depends_on", []),
            ))

        plan = Plan(
            intent=intent,
            steps=new_steps,
            description=f"Modified plan for {intent.action}.{intent.target}",
        )

        utterance = record.params.get("utterance", "")
        identity = record.params.get("identity")
        session_id = record.params.get("session_id")

        return await self.process(
            utterance,
            identity=identity,
            session_id=session_id,
            skip_simulation=False,
            override_plan=plan,
        )

    async def approve_execution(
        self, action_id: str, approved: bool,
        approver_identity: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        if not self._memory:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="No memory backend available for approval",
            )
        record = self._memory.get_pending_action(action_id)
        if record is None:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error=f"Pending action '{action_id}' not found or expired",
            )
        stored_identity = record.params.get("identity") or {}
        if approver_identity and stored_identity.get("user_id") != approver_identity.get("user_id"):
            empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=empty_intent, plan=Plan(intent=empty_intent, steps=[]),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="Approval identity does not match the user who requested the action",
            )
        self._memory.remove_pending_action(action_id)
        if not approved:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                              steps=[], risk_score=0.0, description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error=f"Execution rejected by user: {record.reason}",
            )
        logger.info("Execution APPROVED: %s (action_id=%s)", record.reason, action_id)
        utterance = record.params.get("utterance", "")
        identity = record.params.get("identity")
        session_id = record.params.get("session_id")
        stored_plan = self._plan_from_dict(record.params.get("plan", {}))
        if not stored_plan.steps:
            return ExecutionResult(
                plan=self._build_exec_plan(stored_plan.intent, stored_plan, {}),
                error="Stored approval plan is empty or invalid",
            )
        return await self.process(
            utterance,
            identity=identity,
            session_id=session_id,
            skip_simulation=True,
            override_plan=stored_plan,
        )

    @property
    def capability_registry(self):
        return getattr(self._tool_gateway, '_capability_registry', None)

    def get_capabilities(self) -> Dict[str, Any]:
        registry = self.capability_registry
        capabilities_list = []
        if registry is not None:
            capabilities_list = [c.to_dict() for c in registry.list_all()]
        return {
            "intents": self._intent_engine.list_supported_targets(),
            "tools": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in self._tool_gateway.list_specs()
            ],
            "capabilities": capabilities_list,
            "capabilities_count": len(capabilities_list),
            "models": self._model_router.list_providers() if self._model_router else [],
        }

    @property
    def feedback_store(self) -> Any:
        return self._feedback

    @property
    def cost_tracker(self) -> Any:
        return self._cost_tracker

    @property
    def performance_tracker(self) -> Any:
        return self._perf_tracker

    @property
    def plan_cache(self) -> Any:
        return self._plan_cache

    def get_last_execution(self) -> Optional[ExecutionRecord]:
        if self._memory:
            return self._memory.get_last_execution()
        return None

    @property
    def multi_agent(self) -> Optional[Any]:
        return self._multi_agent

    async def process_multi_agent(
        self, utterance: str, *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionResult:
        execution_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        context: Dict[str, Any] = {"execution_id": execution_id, "session_id": session_id}
        if identity is not None:
            context["identity"] = identity

        if not self._multi_agent:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="Multi-agent orchestrator not configured",
            )

        if self._rate_limiter:
            try:
                dec = self._rate_limiter.allow("global", limit=DEFAULT_LIMITS.get("global", 60))
                if not dec.allowed:
                    return ExecutionResult(
                        plan=ExecutionPlan(
                            intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                            plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                            tool_id="", tool_params={}, task_type=TaskType.QUICK,
                        ),
                        error="Rate limit exceeded",
                        rate_limited=True, retry_after=dec.retry_after,
                    )
            except Exception:
                pass

        if self._context_engine:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
            except Exception:
                pass

        try:
            ma_result = await self._multi_agent.execute(utterance, context)
            output = ma_result.merged_output.get("output", "") if ma_result.merged_output else ""
            error = ma_result.error
            step_results = [
                StepResult(
                    step_id=r.sub_task_id, tool_id=r.agent_id or "multi_agent",
                    success=r.success, data=r.data,
                    error=r.error, duration_ms=r.duration_ms,
                )
                for r in ma_result.sub_task_results
            ]
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="delegate", target="multi_agent", parameters={}, confidence=1.0, raw_input=utterance),
                    plan=Plan(steps=[], intent=Intent(action="delegate", target="multi_agent", parameters={}, confidence=1.0, raw_input=utterance), description="Multi-agent execution"),
                    tool_id="multi_agent", tool_params={}, task_type=TaskType.REASONING,
                ),
                tool_result=ToolResult(
                    success=ma_result.success, data={"output": output},
                    error=error, tool_id="multi_agent",
                ),
                error=error,
                step_results=step_results,
            )
        except Exception as e:
            logger.exception("Multi-agent execution failed")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error=f"Multi-agent execution error: {e}",
            )

    @property
    def offline_queue(self) -> Optional[Any]:
        return self._offline_queue

    @property
    def network_monitor(self) -> Optional[Any]:
        return self._network_monitor

    def _on_network_transition(self, online: bool) -> None:
        if online and self._offline_queue:
            log.info("Network restored — processing offline queue")
            import asyncio
            asyncio.create_task(self._process_offline_queue())

    async def _process_offline_queue(self) -> Dict[str, Any]:
        if not self._offline_queue:
            return {"synced": 0, "failed": 0}
        stats = await self._offline_queue.process_queue(self._sync_offline_item)
        if stats["synced"] > 0:
            log.info("Offline queue: %s", stats)
        return stats

    def _sync_offline_item(self, item: QueueItem) -> bool:
        log.info("Syncing offline item %s (%s)", item.id, item.operation_type)
        return True

    async def process_offline(
        self, utterance: str, *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._offline_queue:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(steps=[], intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance), description=""),
                    tool_id="", tool_params={}, task_type=TaskType.QUICK,
                ),
                error="Offline queue not configured",
            )

        item = self._offline_queue.enqueue(
            "orchestrator.process",
            {"utterance": utterance, "session_id": session_id},
        )
        logger.info("Operation queued for offline processing: %s", item.id)
        return ExecutionResult(
            plan=ExecutionPlan(
                intent=Intent(action="queue", target="offline", parameters={}, confidence=1.0, raw_input=utterance),
                plan=Plan(steps=[], intent=Intent(action="queue", target="offline", parameters={}, confidence=1.0, raw_input=utterance), description="Queued for offline processing"),
                tool_id="offline", tool_params={}, task_type=TaskType.QUICK,
            ),
            tool_result=ToolResult(
                success=True, data={"queued": True, "item_id": item.id},
                tool_id="offline",
            ),
            action_id=item.id,
        )

    @property
    def skill_engine(self):
        return self._skill_engine

    async def process_skill(
        self,
        skill_id: str,
        params: Dict[str, Any],
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._skill_engine:
            return {"success": False, "error": "Skill engine not configured"}
        context: Dict[str, Any] = {"session_id": session_id}
        if identity is not None:
            context["identity"] = identity
        result = await self._skill_engine.execute(skill_id, params, context=context)
        return result.to_dict()

    @property
    def alert_manager(self) -> AlertManager:
        return self._alert_manager

    def check_alerts(self) -> Dict[str, Any]:
        count = self._alert_manager.check_all()
        return self._alert_manager.to_dict()
