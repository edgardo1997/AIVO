import asyncio
import inspect
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
from .events import SentinelEvent
from .event_bus import EventBus
from . import event_types

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
    "app.discovery": "app.discovery",
    "executor.command": "executor.command",
    "executor.launch": "executor.launch",
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
    timestamp: str = ""


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
    presentation: Optional[Dict[str, Any]] = None
    grounding_results: List[Dict[str, Any]] = field(default_factory=list)
    grounding_satisfied: bool = True
    execution_id: Optional[str] = None

    @property
    def approved(self) -> bool:
        return bool(
            self.tool_result
            and self.tool_result.success
            and self.grounding_satisfied
            and not self.error
        )


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
        grounding_engine: Optional[Any] = None,
        environment_learning: Optional[Any] = None,
        presentation_layer: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        process_timeout: Optional[float] = 60.0,
    ):
        self._process_timeout = process_timeout
        self._intent_engine = intent_engine
        self._tool_gateway = tool_gateway
        self._planner = planner or Planner()
        self._event_bus = event_bus
        if event_bus:
            if self._intent_engine:
                self._intent_engine.set_event_bus(event_bus)
            if self._planner:
                self._planner.set_event_bus(event_bus)
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
        self._grounding = grounding_engine
        self._environment_learning = environment_learning
        self._presentation = presentation_layer
        if self._grounding:
            self._intent_engine.set_grounding_engine(self._grounding)
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
        self._pipeline_enforced = True
        self._retry_handler = RetryHandler()
        self._fallback_handler = FallbackHandler()
        self._rollback_manager = RollbackManager()

    async def _emit(self, event_type: str, *, component: str = "", session_id: str = "", request_id: str = "", status: str = "", tool: Optional[str] = None, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None, duration: Optional[float] = None) -> None:
        event_bus = getattr(self, "_event_bus", None)
        if event_bus is None:
            return
        event = SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "",
            request_id=request_id or "",
            component=component,
            status=status,
            tool=tool,
            message=message,
            details=details,
            duration=duration,
        )
        await self._event_bus.emit(event)

    def _enforce_pipeline(self, method_name: str = "process") -> None:
        if not self._pipeline_enforced:
            logger.warning("Pipeline enforcement disabled for %s", method_name)

    def close(self) -> None:
        """Release resources owned by this orchestrator instance."""
        for resource_name, resource in (
            ("network monitor", self._network_monitor),
            ("cost tracker", self._cost_tracker),
            ("memory backend", self._memory),
        ):
            close = getattr(resource, "close", None)
            if close is None:
                continue
            try:
                close()
            except Exception:
                logger.exception("Failed to close orchestrator %s", resource_name)

    async def process(
        self,
        utterance: str,
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
        skip_simulation: bool = False,
        override_plan: Optional[Plan] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        try:
            effective_timeout = timeout if timeout is not None else self._process_timeout
            if effective_timeout is not None and effective_timeout > 0:
                result = await asyncio.wait_for(
                    self._process_impl(
                        utterance,
                        identity=identity,
                        session_id=session_id,
                        dry_run=dry_run,
                        skip_simulation=skip_simulation,
                        override_plan=override_plan,
                    ),
                    timeout=effective_timeout,
                )
            else:
                result = await self._process_impl(
                    utterance,
                    identity=identity,
                    session_id=session_id,
                    dry_run=dry_run,
                    skip_simulation=skip_simulation,
                    override_plan=override_plan,
                )
            return self._attach_advisory(result)
        except Exception as exc:
            logger.exception("Pipeline failed: %s", exc)
            await self._emit(event_types.PIPELINE_FAILED, component="pipeline", session_id=session_id, request_id="", status="failed", message=str(exc))
            raise

    def classify_intent(self, utterance: str) -> Intent:
        """Run the side-effect-free preflight classifier used by conversation routing."""
        return self._intent_engine.parse(utterance)

    async def _evaluate_decision(
        self,
        plan: Plan,
        context: Dict[str, Any],
        simulation_result: Optional[Any] = None,
    ) -> DecisionResult:
        """Support the async engine while preserving legacy test/integration doubles."""
        evaluate_async = getattr(self._decision_engine, "evaluate_async", None)
        if callable(evaluate_async):
            candidate = evaluate_async(plan, context, simulation_result=simulation_result)
            if inspect.isawaitable(candidate):
                return await candidate
        return self._decision_engine.evaluate(plan, context, simulation_result=simulation_result)

    async def _process_impl(
        self,
        utterance: str,
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
        skip_simulation: bool = False,
        override_plan: Optional[Plan] = None,
    ) -> ExecutionResult:
        self._enforce_pipeline("_process_impl")
        execution_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        context: Dict[str, Any] = {"execution_id": execution_id, "session_id": session_id}
        if skip_simulation:
            # Private marker for the replay of a plan already approved through
            # Sentinel's signed pending-action flow.
            context["_orchestrator_approval"] = True
        if identity is not None:
            context["identity"] = identity

        if self._rate_limiter:
            try:
                global_limit = DEFAULT_LIMITS.get("global", 60)
                dec = self._rate_limiter.allow("global", limit=global_limit)
                if not dec.allowed:
                    logger.warning("Rate limit exceeded for global key (retry_after=%.0fs)", dec.retry_after)
                    return ExecutionResult(
                        plan=ExecutionPlan(
                            intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                            plan=Plan(
                                steps=[],
                                intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                                description="",
                            ),
                            tool_id="",
                            tool_params={},
                            task_type=TaskType.QUICK,
                        ),
                        error=f"Rate limit exceeded. Retry after {dec.retry_after}s",
                        rate_limited=True,
                        retry_after=dec.retry_after,
                    )
                if session_id:
                    session_limit = DEFAULT_LIMITS.get("session", 20)
                    dec = self._rate_limiter.allow(f"session:{session_id}", limit=session_limit)
                    if not dec.allowed:
                        logger.warning("Rate limit exceeded for session %s", session_id)
                        return ExecutionResult(
                            plan=ExecutionPlan(
                                intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                                plan=Plan(
                                    steps=[],
                                    intent=Intent(
                                        action="", target="", parameters={}, confidence=0.0, raw_input=utterance
                                    ),
                                    description="",
                                ),
                                tool_id="",
                                tool_params={},
                                task_type=TaskType.QUICK,
                            ),
                            error=f"Session rate limit exceeded. Retry after {dec.retry_after}s",
                            rate_limited=True,
                            retry_after=dec.retry_after,
                        )
            except Exception as e:
                logger.warning("Rate limiter check failed: %s", e)

        if self._context_engine:
            await self._emit(event_types.CONTEXT_LOADING, component="context_engine", session_id=session_id, request_id=execution_id)
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
                context["system_summary"] = sys_ctx.summary()
                await self._emit(event_types.CONTEXT_LOADED, component="context_engine", session_id=session_id, request_id=execution_id, status="completed")
            except Exception as e:
                logger.warning("Context collection failed: %s", e)
                await self._emit(event_types.CONTEXT_LOADED, component="context_engine", session_id=session_id, request_id=execution_id, status="failed")

        user_id = identity.get("user_id") if isinstance(identity, dict) else getattr(identity, "user_id", None)

        if session_id and self._memory:
            try:
                history = self._memory.get_session_history(session_id, limit=5, user_id=user_id)
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
                prefs = self._memory.get_user_preferences(session_id, user_id=user_id)
                if prefs:
                    context["user_preferences"] = prefs
            except Exception as e:
                logger.warning("Session context retrieval failed: %s", e)

        if self._profile_manager and identity is not None:
            try:
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
                if user_id:
                    learned = self._memory.get_learned_preferences(user_id, min_confidence=0.6)
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
            else:
                if self._environment_learning and user_id:
                    try:
                        self._environment_learning.observe(user_id, deep_ctx)
                        learned_environment = self._environment_learning.recent_context(user_id)
                        if learned_environment:
                            # Environmental changes feed into the objective risk
                            # assessor, which applies modifiers based on
                            # change_type (safe enum, not app names).
                            context["environment_changes"] = learned_environment
                    except Exception as e:
                        logger.warning("Environmental learning failed: %s", e)

        if override_plan:
            intent = override_plan.intent
            if self._grounding:
                intent = self._intent_engine.attach_grounding(intent)
            plan = override_plan
            logger.info("Using override plan with %d steps for %s", len(plan.steps), utterance)
        else:
            intent = self._intent_engine.parse(utterance, context)
            if self._grounding:
                intent = self._intent_engine.attach_grounding(intent)
            logger.info(
                "Parsed intent: %s -> %s/%s (conf=%.2f)",
                utterance,
                intent.action,
                intent.target,
                intent.confidence,
            )

            cached_plan = self._plan_cache.get(intent) if self._plan_cache else None
            if cached_plan:
                plan = cached_plan
                logger.info("Plan cache HIT for %s/%s", intent.action, intent.target)
            else:
                app_profiles = None
                deep_ctx = context.get("deep_context")
                if deep_ctx and isinstance(deep_ctx, dict):
                    app_profiles = deep_ctx.get("installed_apps")
                plan = self._planner.plan(intent, context, app_profiles=app_profiles)
                if self._plan_cache:
                    self._plan_cache.set(intent, plan)

        exec_plan = self._build_exec_plan(intent, plan, context)

        if self._model_router:
            try:
                exec_plan.router_decision = self._model_router.select(exec_plan.task_type, context=context)
                for step in plan.steps:
                    step_task = TOOL_TO_TASK.get(step.tool_id, exec_plan.task_type)
                    step.model_decision = self._model_router.select(step_task, context=context)
            except RuntimeError as exc:
                logger.info("No model route available; local tool plan remains executable: %s", exc)

        # Run shared pipeline from validation through execution
        result = await self._run_pipeline(
            execution_id=execution_id,
            start=start,
            raw_input=utterance,
            intent=intent,
            plan=plan,
            exec_plan=exec_plan,
            context=context,
            dry_run=dry_run,
            skip_simulation=skip_simulation,
        )
        result.execution_id = execution_id
        return result

    async def _run_pipeline(
        self,
        *,
        execution_id: str,
        start: datetime,
        raw_input: str,
        intent: Intent,
        plan: Plan,
        exec_plan: ExecutionPlan,
        context: Dict[str, Any],
        dry_run: bool,
        skip_simulation: bool = False,
    ) -> ExecutionResult:
        """Shared pipeline logic: validation -> simulation -> decision -> execution -> grounding -> memory -> advisory."""
        session_id = context.get("session_id")
        await self._emit(event_types.PIPELINE_STARTED, component="pipeline", session_id=session_id, request_id=execution_id)

        # Validation
        validation_error = self._validate_executable_plan(intent, plan)
        if not validation_error:
            validation_error = self._validate_grounding_plan(intent, plan)
        if validation_error:
            tool_result = ToolResult.fail(error=validation_error, tool_id=intent.target or "planner")
            result = ExecutionResult(plan=exec_plan, tool_result=tool_result, error=validation_error)
            self._store_memory(execution_id, start, raw_input, intent, plan, None, context, result)
            return self._attach_advisory(result)

        # Simulation
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

        # Decision
        decision: Optional[DecisionResult] = None
        if self._decision_engine:
            await self._emit(event_types.POLICY_VALIDATING, component="policy_engine", session_id=session_id, request_id=execution_id)
            decision = await self._evaluate_decision(plan, context, simulation_result=simulation_result)
            decision_value = decision.decision if isinstance(decision.decision, str) else getattr(decision.decision, "value", str(decision.decision))
            await self._emit(event_types.POLICY_VALIDATED, component="policy_engine", session_id=session_id, request_id=execution_id, status="completed", details={"decision": decision_value})
            safe_read_only_shortcut = self._decision_engine.should_skip_decision(intent) and not (
                simulation_result and simulation_result.requires_confirmation
            )
            if safe_read_only_shortcut and decision.decision == Decision.REQUIRE_CONFIRM:
                decision = DecisionResult(
                    decision=Decision.APPROVE,
                    plan=plan,
                    reason="Read-only query approved without interactive confirmation.",
                    context_factors=decision.context_factors,
                    base_risk_score=decision.base_risk_score,
                    context_modifier=decision.context_modifier,
                    final_risk_score=decision.final_risk_score,
                )
            context["decision"] = asdict(decision)

        # Model router (already done in caller, but ensure for both paths)
        if self._model_router:
            try:
                exec_plan.router_decision = self._model_router.select(exec_plan.task_type, context=context)
                for step in plan.steps:
                    step_task = TOOL_TO_TASK.get(step.tool_id, exec_plan.task_type)
                    step.model_decision = self._model_router.select(step_task, context=context)
            except RuntimeError as exc:
                logger.info("No model route available; local tool plan remains executable: %s", exc)

        # Reject
        if decision and decision.decision == Decision.REJECT:
            logger.warning("Execution REJECTED by decision engine: %s", decision.reason)
            result = ExecutionResult(
                plan=exec_plan,
                decision=decision,
                simulated=True,
                blocked=False,
                error=f"Execution rejected: {decision.reason}",
            )
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            return self._attach_advisory(result)

        # Require confirmation (no session means direct tool call — still enforces confirmation)
        if decision and decision.decision == Decision.REQUIRE_CONFIRM:
            action_id = f"sim_{uuid.uuid4().hex[:12]}"
            reason = decision.reason
            if simulation_result:
                reason = simulation_result.summary
            pending = PendingActionRecord(
                action_id=action_id,
                tool_id=exec_plan.tool_id,
                params={
                    "utterance": raw_input,
                    "identity": context.get("identity"),
                    "session_id": None,
                    "intent": self._intent_to_dict(intent),
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
                plan=exec_plan,
                decision=decision,
                simulated=True,
                blocked=True,
                action_id=action_id,
                simulation_summary=sim_summary,
                error=f"Execution blocked: {reason}",
            )
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            return self._attach_advisory(result)

        # Pre-execution grounding: run grounding tools first, reject if evidence missing
        grounding_step_ids = self._grounding_step_ids(intent)
        grounding_step_results: List[StepResult] = []
        grounding_tool_result: Optional[ToolResult] = None
        if grounding_step_ids and not dry_run:
            grounding_only = Plan(
                steps=[s for s in plan.steps if s.tool_id in grounding_step_ids],
                intent=intent,
                description="Grounding pre-check",
            )
            grounding_levels = self._planner.resolve_dependencies(grounding_only)
            for level in grounding_levels:
                tasks = [self._execute_single_step(s, intent, context, dry_run=dry_run) for s in level]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for step, res in zip(level, results):
                    if isinstance(res, Exception):
                        sr = StepResult(step_id=step.id, tool_id=step.tool_id, success=False, error=str(res))
                        grounding_step_results.append(sr)
                    else:
                        grounding_step_results.append(res)
                        grounding_tool_result = self._merge_tool_result(grounding_tool_result, res)
            grounding_ok = all(sr.success for sr in grounding_step_results)
            if grounding_ok:
                grounding_results, grounding_satisfied = self._verify_grounding_results(
                    intent, grounding_step_results, dry_run=dry_run
                )
                if not grounding_satisfied:
                    failed_reqs = [
                        r.category.value for r in getattr(intent, "grounding_requirements", [])
                        if r.required
                    ]
                    logger.warning("Pre-execution grounding FAILED for: %s", failed_reqs)
                    result = ExecutionResult(
                        plan=exec_plan,
                        decision=decision,
                        simulated=False,
                        blocked=False,
                        error=f"Required grounding failed: {failed_reqs}",
                        grounding_results=grounding_results,
                        grounding_satisfied=False,
                        step_results=grounding_step_results,
                        tool_result=grounding_tool_result,
                    )
                    self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
                    return self._attach_advisory(result)
                logger.info("Pre-execution grounding PASSED for intent %s/%s", intent.action, intent.target)
            else:
                failed = [
                    {"tool_id": sr.tool_id, "error": sr.error}
                    for sr in grounding_step_results if not sr.success
                ]
                logger.warning("Pre-execution grounding tool(s) FAILED: %s", failed)
                grounding_results, _ = self._verify_grounding_results(
                    intent, grounding_step_results, dry_run=dry_run
                )
                result = ExecutionResult(
                    plan=exec_plan,
                    decision=decision,
                    simulated=False,
                    blocked=False,
                    error=f"Grounding execution failed: {failed}",
                    grounding_results=grounding_results,
                    grounding_satisfied=False,
                    step_results=grounding_step_results,
                    tool_result=grounding_tool_result,
                )
                self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
                return self._attach_advisory(result)

        # Execution: run non-grounding plan steps (grounding already verified)
        await self._emit(event_types.EXECUTION_STARTED, component="execution", session_id=session_id, request_id=execution_id, details={"step_count": len(plan.steps)})
        grounding_executed_ids = {sr.step_id for sr in grounding_step_results}
        step_results: List[StepResult] = []
        step_results.extend(grounding_step_results)
        tool_result: Optional[ToolResult] = grounding_tool_result
        executed: List[Tuple[PlanStep, StepResult]] = []
        rollback_actions: List[Dict[str, Any]] = []

        grounding_pre_verified = bool(grounding_step_ids and not dry_run)
        levels = self._planner.resolve_dependencies(
            Plan(steps=plan.steps, intent=intent, description="Main execution")
        )
        if plan.steps and not levels and not step_results:
            tool_result = ToolResult.fail(error="Invalid plan dependency graph", tool_id="planner")
        for level in levels:
            pending = [s for s in level if s.id not in grounding_executed_ids]
            if not pending:
                continue
            if len(pending) == 1:
                step = pending[0]
                s_result = await self._execute_single_step(step, intent, context, dry_run=dry_run)
                step_results.append(s_result)
                tool_result = self._merge_tool_result(tool_result, s_result)
                executed.append((step, s_result))
                if not s_result.success and not dry_run:
                    rollback_actions.extend(
                        asdict(action) for action in await self._rollback_completed(executed[:-1], context)
                    )
                    break
            else:
                tasks = [self._execute_single_step(s, intent, context, dry_run=dry_run) for s in pending]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                all_ok = True
                for step, res in zip(pending, results):
                    if isinstance(res, Exception):
                        step_results.append(
                            StepResult(
                                step_id=step.id,
                                tool_id=step.tool_id,
                                success=False,
                                error=str(res),
                            )
                        )
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
                    rollback_actions.extend(
                        asdict(action) for action in await self._rollback_completed(completed, context)
                    )
                    break

        executed_ids = {step_result.step_id for step_result in step_results}
        if not dry_run and any(not item.success for item in step_results):
            for step in plan.steps:
                if step.id not in executed_ids:
                    step_results.append(
                        StepResult(
                            step_id=step.id,
                            tool_id=step.tool_id,
                            success=False,
                            error="Skipped because a dependency failed",
                            status="skipped",
                        )
                    )

        if tool_result:
            tool_result.duration_ms = sum(s.duration_ms or 0 for s in step_results if s.duration_ms)

        # Grounding verification (post-execution audit)
        grounding_results, grounding_satisfied = self._verify_grounding_results(
            intent, step_results, dry_run=dry_run
        )
        result = ExecutionResult(
            plan=exec_plan,
            decision=decision,
            tool_result=tool_result,
            error=(tool_result.error if tool_result and not tool_result.success else None),
            step_results=step_results,
            simulated=dry_run,
            rollback_actions=rollback_actions,
            grounding_results=grounding_results,
            grounding_satisfied=grounding_satisfied,
        )
        if not dry_run and not grounding_satisfied and not result.error and not grounding_pre_verified:
            result.error = "Required grounding evidence was not produced"
        if not dry_run:
            await self._emit(event_types.AUDIT_STARTED, component="audit", session_id=session_id, request_id=execution_id)
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            await self._emit(event_types.AUDIT_COMPLETED, component="audit", session_id=session_id, request_id=execution_id, status="completed")
        await self._emit(event_types.EXECUTION_COMPLETED, component="execution", session_id=session_id, request_id=execution_id, status="completed" if not result.error else "failed", duration=(datetime.now(timezone.utc) - start).total_seconds())
        await self._emit(event_types.PIPELINE_COMPLETED, component="pipeline", session_id=session_id, request_id=execution_id, status="completed" if not result.error else "failed")
        return self._attach_advisory(result)

    def _grounding_step_ids(self, intent: Intent) -> set:
        grounding_ids: set = set()
        for req in getattr(intent, "grounding_requirements", []):
            if req.tool_id:
                grounding_ids.add(req.tool_id)
        return grounding_ids

    def _tool_to_override_plan(self, tool_id: str, params: dict, utterance: str = "") -> Plan:
        raw_input = utterance or f"execute {tool_id}"
        intent = Intent(
            action="execute",
            target=tool_id,
            parameters=params,
            confidence=1.0,
            raw_input=raw_input,
        )
        step = PlanStep(
            id="direct",
            tool_id=tool_id,
            description=f"Execute {tool_id}",
            params=params,
            estimated_impact="low",
        )
        return Plan(
            steps=[step],
            intent=intent,
            description=f"Direct execution of {tool_id}",
        )

    async def execute_direct(
        self,
        tool_id: str,
        params: dict,
        *,
        identity: Optional[dict] = None,
        utterance: str = "",
        dry_run: bool = False,
        skip_simulation: bool = False,
    ) -> ExecutionResult:
        self._enforce_pipeline("execute_direct")
        raw_input = utterance or f"execute {tool_id}"
        override_plan = self._tool_to_override_plan(tool_id, params, utterance)
        return await self._process_impl(
            raw_input,
            identity=identity,
            session_id=None,
            dry_run=dry_run,
            skip_simulation=skip_simulation,
            override_plan=override_plan,
        )

    def _attach_advisory(self, result: ExecutionResult) -> ExecutionResult:
        """Attach read-only advice and presentation. Failures must never affect execution."""
        has_presentation = getattr(self, "_presentation", None) is not None
        if self._advisory is None and not has_presentation:
            return result
        if self._advisory is not None and result.advisory is None:
            try:
                result.advisory = self._advisory.analyze(result)
            except Exception as exc:
                logger.warning("Advisory analysis failed; execution result is unchanged: %s", exc)
        if has_presentation and result.presentation is None:
            try:
                from sentinel.presentation import PresentationMode
                mode = PresentationMode.USER
                result.presentation = self._presentation.present(result, mode)
            except Exception as exc:
                logger.warning("Presentation layer failed; execution result is unchanged: %s", exc)
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
                intent=self._intent_to_dict(intent),
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
                tool_id = plan.steps[0].tool_id if plan.steps else ""
                identity_data = context.get("identity", {})
                intent_data = self._intent_to_dict(intent) if intent else None
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

    def _build_exec_plan(self, intent: Intent, plan: Plan, context: Dict[str, Any]) -> ExecutionPlan:
        tool_id = INTENT_TO_TOOL.get(intent.target, "system.info")
        task_type = INTENT_TO_TASK.get(intent.action, TaskType.QUICK)

        params: Dict[str, Any] = {}
        if intent.target == "system.processes":
            params["limit"] = intent.parameters.get("limit", 10)
        elif intent.target == "app.discovery":
            params["action"] = intent.parameters.get("action", "list")
            params["limit"] = intent.parameters.get("limit", 30)
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
        self,
        step: PlanStep,
        intent: Intent,
        context: Dict[str, Any],
        dry_run: bool = False,
    ) -> StepResult:
        step_context = context
        if step.model_decision:
            step_context = dict(context)
            step_context["model_decision"] = step.model_decision.to_dict()

        if dry_run:
            return StepResult(
                step_id=step.id,
                tool_id=step.tool_id,
                success=True,
                data={
                    "simulated": True,
                    "tool_id": step.tool_id,
                    "params": dict(step.params),
                    "description": step.description,
                    "model_decision": step_context.get("model_decision"),
                },
            )
        step_params = dict(step.params)
        if step.tool_id == "executor.command":
            step_params.setdefault("command", intent.parameters.get("command", ""))
        elif step.tool_id == "executor.kill":
            step_params.setdefault("pid", intent.parameters.get("pid"))
        elif step.tool_id == "executor.launch":
            step_params.setdefault(
                "app_name",
                intent.parameters.get("app_name") or intent.parameters.get("command", ""),
            )
            step_params.setdefault("elevated", bool(intent.parameters.get("elevated", False)))
        elif step.tool_id == "filesystem.search":
            step_params.setdefault("pattern", intent.parameters.get("pattern", ""))
            step_params.setdefault("path", intent.parameters.get("path", ""))

        attempted_tools: List[str] = []

        async def _do_execute(tool_id: Optional[str] = None):
            tid = tool_id or step.tool_id
            attempted_tools.append(tid)
            session_id = context.get("session_id")
            execution_id = context.get("execution_id", "")
            await self._emit(event_types.TOOL_STARTED, component="tool_gateway", session_id=session_id, request_id=execution_id, tool=tid)
            result = await self._tool_gateway.execute(
                tool_id=tid,
                params=step_params,
                context=step_context,
            )
            await self._emit(event_types.TOOL_FINISHED, component="tool_gateway", session_id=session_id, request_id=execution_id, tool=tid, status="completed" if result.success else "failed", duration=result.duration_ms / 1000.0 if result.duration_ms else None)
            return result

        policy = step.recovery_policy or RecoveryPolicy.default_for(step.tool_id)
        try:
            s_result = await self._retry_handler.execute(
                lambda: _do_execute(step.tool_id),
                policy,
                tool_id=step.tool_id,
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
                    s_result,
                    fallback_fns,
                    policy,
                    tool_id=step.tool_id,
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
                        alert.provider_id,
                        alert.model,
                        alert.tool_id,
                        alert.current_avg,
                        alert.baseline_avg,
                        alert.deviation_pct,
                    )
            except Exception as e:
                logger.warning("Failed to record performance: %s", e)

        recovery_strategy = (
            "fallback"
            if s_result.tool_id and s_result.tool_id != step.tool_id
            else ("retry" if len(attempted_tools) > 1 else "none")
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
            timestamp=getattr(s_result, "timestamp", "") or datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _validate_grounding_plan(intent: Intent, plan: Plan) -> Optional[str]:
        planned_tools = {step.tool_id for step in plan.steps}
        for requirement in intent.grounding_requirements:
            if requirement.required and (
                not requirement.tool_id or requirement.tool_id not in planned_tools
            ):
                return (
                    "The plan cannot satisfy required grounding for "
                    f"{requirement.category.value}"
                )
        return None

    @staticmethod
    def _intent_to_dict(intent: Intent) -> Dict[str, Any]:
        data = asdict(intent)
        for requirement in data.get("grounding_requirements", []):
            category = requirement.get("category")
            if hasattr(category, "value"):
                requirement["category"] = category.value
        return data

    @staticmethod
    def _verify_grounding_results(
        intent: Intent,
        step_results: List[StepResult],
        *,
        dry_run: bool,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        evidence: List[Dict[str, Any]] = []
        satisfied = True
        for requirement in intent.grounding_requirements:
            matching = next(
                (
                    result
                    for result in step_results
                    if result.tool_id == requirement.tool_id
                    or result.executed_tool_id == requirement.tool_id
                ),
                None,
            )
            grounded = bool(matching and matching.success and not dry_run)
            if requirement.required and not grounded and not dry_run:
                satisfied = False
            evidence.append(
                {
                    "category": requirement.category.value,
                    "required": requirement.required,
                    "grounded": grounded,
                    "source": "simulation" if dry_run else ("tool" if grounded else "none"),
                    "tool_id": requirement.tool_id,
                    "timestamp": matching.timestamp if matching else "",
                    "freshness_seconds": requirement.freshness_seconds,
                    "reason": requirement.reason,
                    "error": None if grounded or dry_run else (
                        matching.error if matching else "Required tool result is missing"
                    ),
                }
            )
        return evidence, satisfied

    @staticmethod
    def _validate_executable_plan(intent: Intent, plan: Plan) -> Optional[str]:
        """Reject incomplete executable plans before simulation or confirmation."""
        if intent.confidence < 0.6:
            return None
        if not plan.steps:
            return "The planner produced no executable steps"
        required = {
            "executor.command": "command",
            "executor.launch": "app_name",
            "executor.kill": "pid",
        }.get(intent.target)
        if required and intent.parameters.get(required) is None:
            return f"{required} is required for {intent.target}"
        if any(not step.tool_id for step in plan.steps):
            return "The planner produced a step without a tool"
        return None

    @staticmethod
    def _merge_tool_result(
        current: Optional[ToolResult],
        step_result: StepResult,
    ) -> ToolResult:
        if current is None:
            return ToolResult(
                success=step_result.success,
                data=step_result.data,
                error=step_result.error,
                tool_id=step_result.tool_id,
                duration_ms=step_result.duration_ms,
                requires_confirmation=step_result.requires_confirmation,
                policy_result=step_result.policy_result,
                quality_result=step_result.quality_result,
            )
        if not current.success or not step_result.success:
            return ToolResult(
                success=False,
                error=current.error or step_result.error,
                tool_id=current.tool_id,
                duration_ms=(current.duration_ms or 0) + (step_result.duration_ms or 0),
                requires_confirmation=current.requires_confirmation or step_result.requires_confirmation,
                policy_result=step_result.policy_result or current.policy_result,
                quality_result=step_result.quality_result or current.quality_result,
            )
        return ToolResult(
            success=True,
            data=step_result.data or current.data,
            tool_id=current.tool_id,
            duration_ms=(current.duration_ms or 0) + (step_result.duration_ms or 0),
            requires_confirmation=step_result.requires_confirmation,
            policy_result=step_result.policy_result or current.policy_result,
            quality_result=step_result.quality_result or current.quality_result,
        )

    @staticmethod
    def _plan_to_dict(plan: Plan) -> Dict[str, Any]:
        d = asdict(plan)
        d["intent"] = Orchestrator._intent_to_dict(plan.intent)
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
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error="No memory backend available for approval",
            )
        record = self._memory.get_pending_action(action_id)
        if record is None:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error=f"Pending action '{action_id}' not found or expired",
            )
        stored_identity = record.params.get("identity") or {}
        if approver_identity and stored_identity.get("user_id") != approver_identity.get("user_id"):
            empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=empty_intent,
                    plan=Plan(intent=empty_intent, steps=[]),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error="Approval identity does not match the user who requested the action",
            )
        self._memory.remove_pending_action(action_id)

        if not modified_steps:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
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
            new_steps.append(
                PlanStep(
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
                )
            )

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
        self,
        action_id: str,
        approved: bool,
        approver_identity: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        if not self._memory:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error="No memory backend available for approval",
            )
        record = self._memory.get_pending_action(action_id)
        if record is None:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error=f"Pending action '{action_id}' not found or expired",
            )
        stored_identity = record.params.get("identity") or {}
        if approver_identity and stored_identity.get("user_id") != approver_identity.get("user_id"):
            empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=empty_intent,
                    plan=Plan(intent=empty_intent, steps=[]),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
                ),
                error="Approval identity does not match the user who requested the action",
            )
        self._memory.remove_pending_action(action_id)
        if not approved:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                    plan=Plan(
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=""),
                        steps=[],
                        risk_score=0.0,
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
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
        return getattr(self._tool_gateway, "_capability_registry", None)

    def get_capabilities(self) -> Dict[str, Any]:
        registry = self.capability_registry
        capabilities_list = []
        if registry is not None:
            capabilities_list = [c.to_dict() for c in registry.list_all()]
        return {
            "intents": self._intent_engine.list_supported_targets(),
            "tools": [
                {"id": s.id, "name": s.name, "description": s.description} for s in self._tool_gateway.list_specs()
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
        self,
        utterance: str,
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionResult:
        execution_id = uuid.uuid4().hex[:12]
        datetime.now(timezone.utc)
        context: Dict[str, Any] = {"execution_id": execution_id, "session_id": session_id}
        if identity is not None:
            context["identity"] = identity

        if not self._multi_agent:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(
                        steps=[],
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
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
                            plan=Plan(
                                steps=[],
                                intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                                description="",
                            ),
                            tool_id="",
                            tool_params={},
                            task_type=TaskType.QUICK,
                        ),
                        error="Rate limit exceeded",
                        rate_limited=True,
                        retry_after=dec.retry_after,
                    )
            except Exception as exc:
                logger.warning("Multi-agent rate-limit check failed: %s", exc)

        if self._context_engine:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
            except Exception as exc:
                logger.warning("Multi-agent context collection failed: %s", exc)

        try:
            ma_result = await self._multi_agent.execute(utterance, context)
            output = ma_result.merged_output.get("output", "") if ma_result.merged_output else ""
            error = ma_result.error
            step_results = [
                StepResult(
                    step_id=r.sub_task_id,
                    tool_id=r.agent_id or "multi_agent",
                    success=r.success,
                    data=r.data,
                    error=r.error,
                    duration_ms=r.duration_ms,
                )
                for r in ma_result.sub_task_results
            ]
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(
                        action="delegate", target="multi_agent", parameters={}, confidence=1.0, raw_input=utterance
                    ),
                    plan=Plan(
                        steps=[],
                        intent=Intent(
                            action="delegate", target="multi_agent", parameters={}, confidence=1.0, raw_input=utterance
                        ),
                        description="Multi-agent execution",
                    ),
                    tool_id="multi_agent",
                    tool_params={},
                    task_type=TaskType.REASONING,
                ),
                tool_result=ToolResult(
                    success=ma_result.success,
                    data={"output": output},
                    error=error,
                    tool_id="multi_agent",
                ),
                error=error,
                step_results=step_results,
            )
        except Exception as e:
            logger.exception("Multi-agent execution failed")
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(
                        steps=[],
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
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
            logger.info("Network restored — processing offline queue")
            import asyncio

            asyncio.create_task(self._process_offline_queue())

    async def _process_offline_queue(self) -> Dict[str, Any]:
        if not self._offline_queue:
            return {"synced": 0, "failed": 0}
        stats = await self._offline_queue.process_queue(self._sync_offline_item)
        if stats["synced"] > 0:
            logger.info("Offline queue: %s", stats)
        return stats

    def _sync_offline_item(self, item: QueueItem) -> bool:
        logger.info("Syncing offline item %s (%s)", item.id, item.operation_type)
        return True

    async def process_offline(
        self,
        utterance: str,
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._offline_queue:
            return ExecutionResult(
                plan=ExecutionPlan(
                    intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                    plan=Plan(
                        steps=[],
                        intent=Intent(action="", target="", parameters={}, confidence=0.0, raw_input=utterance),
                        description="",
                    ),
                    tool_id="",
                    tool_params={},
                    task_type=TaskType.QUICK,
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
                plan=Plan(
                    steps=[],
                    intent=Intent(action="queue", target="offline", parameters={}, confidence=1.0, raw_input=utterance),
                    description="Queued for offline processing",
                ),
                tool_id="offline",
                tool_params={},
                task_type=TaskType.QUICK,
            ),
            tool_result=ToolResult(
                success=True,
                data={"queued": True, "item_id": item.id},
                tool_id="offline",
            ),
            action_id=item.id,
        )

    @property
    def skill_engine(self):
        return self._skill_engine

    @property
    def alert_manager(self) -> AlertManager:
        return self._alert_manager

    def check_alerts(self) -> Dict[str, Any]:
        self._alert_manager.check_all()
        return self._alert_manager.to_dict()
