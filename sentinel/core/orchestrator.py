import asyncio
import inspect
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging
import uuid

from .intent import Intent, IntentEngine
from .model_router import ModelRouter, TaskType, RouterDecision
from .tool_gateway import ToolGateway
from .execution_pipeline import ExecutionPipeline
from .context import ContextEngine
from .tool import ToolResult
from .planner import Planner, Plan, PlanStep
from .decision_engine import Decision, DecisionEngine, DecisionResult
from .operational_memory import MemoryBackend, ExecutionRecord, PendingActionRecord
from .cost_tracker import CostTracker
from .intelligence_coordinator import IntelligenceCoordinator
from .plan_cache import PlanCache
from .recovery import RetryHandler, FallbackHandler, RollbackManager, RecoveryPolicy, RetryExhaustedError
from .rate_limiter import RateLimiter, RateLimitDecision, DEFAULT_LIMITS, load_rate_limit_config
from .multi_agent import MultiAgentOrchestrator
from .offline_queue import OfflineQueue, QueueItem
from .network_monitor import NetworkMonitor
from .alerting import AlertManager, AlertSeverity
from .events import SentinelEvent
from .event_bus import EventBus
from . import event_types
from sentinel.core.runtime import SentinelRuntime, SentinelRequest

logger = logging.getLogger(__name__)


CONSERVATIVE_MODE = os.environ.get("SENTINEL_CONSERVATIVE_MODE", "0") == "1"
CONSERVATIVE_BLOCKED_TOOLS = frozenset(
    {
        "filesystem.write",
        "filesystem.delete",
        "executor.command",
        "executor.launch",
        "executor.kill",
        "executor.restart",
    }
)


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
    model_strategy: Optional[Dict[str, Any]] = None
    capability_recommendation: Optional[Dict[str, Any]] = None


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
        return bool(self.tool_result and self.tool_result.success and self.grounding_satisfied and not self.error)


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
        risk_classifier: Optional[Any] = None,
        consent_service: Optional[Any] = None,
        simulation_engine: Optional[Any] = None,
        model_feedback_store: Optional[Any] = None,
        cost_tracker: Optional[CostTracker] = None,
        performance_tracker: Optional[Any] = None,
        intelligence: Optional[Any] = None,
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
        execution_pipeline: Optional[ExecutionPipeline] = None,
        tool_execution_guard: Optional[Any] = None,
        hardening: Optional[Any] = None,
        advisory_service: Optional[Any] = None,
        grounding_engine: Optional[Any] = None,
        environment_learning: Optional[Any] = None,
        presentation_layer: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        event_store: Optional[Any] = None,
        process_timeout: Optional[float] = 60.0,
        rate_limit_config: Optional[Dict[str, int]] = None,
        runtime: Optional[SentinelRuntime] = None,
        observability_engine: Optional[Any] = None,
    ):
        self._process_timeout = process_timeout
        self._runtime = runtime
        self._intent_engine = intent_engine
        self._tool_gateway = tool_gateway
        self._planner = planner or Planner()
        self._event_bus = event_bus
        self._event_store = event_store
        if event_bus:
            if self._intent_engine:
                self._intent_engine.set_event_bus(event_bus)
            if self._planner:
                self._planner.set_event_bus(event_bus)
            if event_store is not None:

                async def _save_to_event_store(event):
                    try:
                        event_store.save(event)
                    except Exception:
                        logger.debug("Event store persistence failed", exc_info=True)

                event_bus.subscribe("*", _save_to_event_store)
        self._decision_engine = decision_engine
        self._model_router = model_router
        self._context_engine = context_engine
        self._memory = memory
        self._audit_service = audit_service
        self._profile_manager = profile_manager
        self._deep_context = deep_context_engine
        self._risk_classifier = risk_classifier
        self._consent_service = consent_service
        self._simulation = simulation_engine
        self._feedback = model_feedback_store
        self._cost_tracker = cost_tracker
        self._perf_tracker = performance_tracker
        self._intelligence = intelligence or IntelligenceCoordinator()
        self._plan_cache = plan_cache
        self._rate_limiter = rate_limiter
        self._rate_limit_config = rate_limit_config
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
        if execution_pipeline is None:
            execution_pipeline = ExecutionPipeline(
                tool_gateway=tool_gateway,
                audit_service=audit_service,
                tool_execution_guard=tool_execution_guard,
            )
        self._execution_pipeline = execution_pipeline
        self._tool_execution_guard = tool_execution_guard
        self._pipeline_enforced = True
        self._retry_handler = RetryHandler()
        self._fallback_handler = FallbackHandler()
        self._rollback_manager = RollbackManager()
        self._observability = observability_engine
        self._obs_persist_counter = 0
        if self._observability is not None:
            self._wire_observability()

    def _wire_observability(self) -> None:
        """Register Orchestrator-owned components in the ObservabilityEngine."""
        obs = self._observability
        try:
            register = getattr(obs, "register_component", None)
            if register is None:
                register = getattr(obs.health, "register", None)
            if register is None:
                return
            from sentinel.observability.health.health_checker import ComponentHealth, HealthState

            register(
                "orchestrator",
                lambda: ComponentHealth(
                    name="orchestrator",
                    state=HealthState.HEALTHY,
                    details={"pipeline_enforced": self._pipeline_enforced},
                ),
            )
            register(
                "execution_pipeline",
                lambda: ComponentHealth(
                    name="execution_pipeline",
                    state=HealthState.HEALTHY,
                    details={"enforced": self._pipeline_enforced},
                ),
            )
            register(
                "tool_gateway",
                lambda: ComponentHealth(
                    name="tool_gateway",
                    state=HealthState.HEALTHY,
                    details={"tools": len(getattr(self._tool_gateway, "_tools", {}) or {})},
                ),
            )
            register(
                "tool_execution_guard",
                lambda: ComponentHealth(
                    name="tool_execution_guard",
                    state=HealthState.HEALTHY if getattr(self, "_pipeline_enforced", True) else HealthState.DEGRADED,
                    details={"enforced": self._pipeline_enforced},
                ),
            )
        except Exception as e:
            logger.debug("Observability wiring failed: %s", e)

    async def _run_with_observability(
        self, coro, *, utterance: str, identity: Optional[dict], session_id: Optional[str], dry_run: bool
    ) -> Any:
        """Wrap the pipeline with a request trace + telemetry (fail-safe)."""
        obs = self._observability
        if obs is None:
            return await coro
        import time as _time

        start = _time.monotonic()
        span = None
        try:
            span = obs.start_request_trace(
                metadata={"utterance": utterance[:200], "session_id": session_id or "", "dry_run": dry_run}
            )
        except Exception:
            span = None
        try:
            result = await coro
            latency_ms = (_time.monotonic() - start) * 1000
            model_id = "unknown"
            try:
                if result.plan is not None and getattr(result.plan, "intent", None) is not None:
                    model_id = getattr(result.plan.intent, "action", "") or "unknown"
            except Exception:
                logger.debug("Failed to derive observability model id", exc_info=True)
            try:
                obs.record_request(model_id, True, latency_ms)
                obs.record_component_duration("orchestrator.process", latency_ms)
            except Exception:
                logger.warning("Failed to record successful orchestrator telemetry", exc_info=True)
            if span is not None:
                try:
                    obs.end_request_trace(span, status="ok")
                except Exception:
                    logger.warning("Failed to close successful orchestrator trace", exc_info=True)
            await self._maybe_persist_observability()
            return result
        except Exception:
            latency_ms = (_time.monotonic() - start) * 1000
            try:
                obs.record_request("unknown", False, latency_ms)
                obs.record_component_duration("orchestrator.process", latency_ms)
            except Exception:
                logger.warning("Failed to record failed orchestrator telemetry", exc_info=True)
            if span is not None:
                try:
                    obs.end_request_trace(span, status="error")
                except Exception:
                    logger.warning("Failed to close failed orchestrator trace", exc_info=True)
            raise

    async def _maybe_persist_observability(self) -> None:
        """Periodically flush engine telemetry into the official MetricRepository."""
        self._obs_persist_counter += 1
        if self._obs_persist_counter % 25 != 0:
            return
        if self._observability is None or self._intelligence is None:
            return
        persist = getattr(self._intelligence, "persist_observability_metrics", None)
        if persist is None:
            return
        try:
            await persist(self._observability)
        except Exception as e:
            logger.debug("Observability metrics persistence skipped: %s", e)

    async def _emit(
        self,
        event_type: str,
        *,
        component: str = "",
        session_id: str = "",
        request_id: str = "",
        status: str = "",
        tool: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        duration: Optional[float] = None,
    ) -> None:
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

    def set_rate_limit_config(self, config: Dict[str, int]) -> None:
        self._rate_limit_config = config

    def set_consent_service(self, service: Any) -> None:
        """Conectar ConsentService post-construcción (necesario por orden de inicialización en main.py)."""
        self._consent_service = service

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
        approved_plan_grant_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        if self._runtime is not None:
            return await self._runtime_process(utterance, identity=identity, session_id=session_id, dry_run=dry_run)
        try:
            effective_timeout = timeout if timeout is not None else self._process_timeout
            coro = self._process_impl(
                utterance,
                identity=identity,
                session_id=session_id,
                dry_run=dry_run,
                skip_simulation=skip_simulation,
                override_plan=override_plan,
                approved_plan_grant_id=approved_plan_grant_id,
            )
            coro = self._run_with_observability(
                coro,
                utterance=utterance,
                identity=identity,
                session_id=session_id,
                dry_run=dry_run,
            )
            if effective_timeout is not None and effective_timeout > 0:
                result = await asyncio.wait_for(coro, timeout=effective_timeout)
            else:
                result = await coro
            return self._attach_advisory(result)
        except Exception as exc:
            logger.exception("Pipeline failed: %s", exc)
            await self._emit(
                event_types.PIPELINE_FAILED,
                component="pipeline",
                session_id=session_id,
                request_id="",
                status="failed",
                message=str(exc),
            )
            raise

    async def _runtime_process(
        self,
        utterance: str,
        *,
        identity: Optional[dict] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """Bridge: Orchestrator.process() → SentinelRuntime.process() → ExecutionResult."""
        request = SentinelRequest(
            utterance=utterance,
            session_id=session_id or "",
            user_id=identity.get("user_id", "") if isinstance(identity, dict) else "",
            dry_run=dry_run,
            context={"identity": identity or {}},
        )
        response = await self._runtime.process(request)
        from .intent import Intent
        from .planner import Plan

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
            error=response.error,
        )

    def classify_intent(self, utterance: str) -> Intent:
        """Run the side-effect-free preflight classifier used by conversation routing."""
        return self._intent_engine.parse(utterance)

    async def _evaluate_decision(
        self,
        plan: Plan,
        context: Dict[str, Any],
        simulation_result: Optional[Any] = None,
        risk_classification: Optional[Any] = None,
    ) -> DecisionResult:
        """Support the async engine while preserving legacy test/integration doubles."""
        evaluate_async = getattr(self._decision_engine, "evaluate_async", None)
        if callable(evaluate_async):
            try:
                candidate = evaluate_async(
                    plan, context, simulation_result=simulation_result, risk_classification=risk_classification
                )
            except TypeError:
                candidate = evaluate_async(plan, context, simulation_result=simulation_result)
            if inspect.isawaitable(candidate):
                return await candidate
        try:
            return self._decision_engine.evaluate(
                plan, context, simulation_result=simulation_result, risk_classification=risk_classification
            )
        except TypeError:
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
        approved_plan_grant_id: Optional[str] = None,
    ) -> ExecutionResult:
        self._enforce_pipeline("_process_impl")
        execution_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        context: Dict[str, Any] = {"execution_id": execution_id, "session_id": session_id}
        if approved_plan_grant_id:
            context["approved_plan_grant_id"] = approved_plan_grant_id
        if skip_simulation:
            # Verificar ConsentManager antes de autorizar bypass
            if self._consent_service is not None and identity is not None:
                user_id = identity.get("user_id") if isinstance(identity, dict) else None
                if user_id and override_plan and override_plan.steps:
                    tool_id = override_plan.steps[0].tool_id
                    grant = self._consent_service.check_existing_consent(user_id, tool_id)
                    if grant is None:
                        logger.warning(
                            "No ConsentGrant found for %s/%s — fallback to pending action approval", user_id, tool_id
                        )
        if identity is not None:
            context["identity"] = identity

        if self._rate_limiter:
            try:
                rc = self._rate_limit_config or {}
                user_id = identity.get("user_id") if isinstance(identity, dict) else None
                user_tier = identity.get("tier", "free") if isinstance(identity, dict) else "free"
                tiers = []
                tier_global_key = f"tier:{user_tier}:global"
                global_limit = rc.get(tier_global_key) or rc.get("global", DEFAULT_LIMITS.get("global", 1000))
                tiers.append(("global", global_limit))
                if session_id:
                    tier_session_key = f"tier:{user_tier}:session"
                    session_limit = rc.get(tier_session_key) or rc.get("session", DEFAULT_LIMITS.get("session", 50))
                    tiers.append((f"session:{session_id}", session_limit))
                if user_id:
                    tier_user_key = f"tier:{user_tier}:user"
                    user_limit = rc.get(tier_user_key) or rc.get("user", DEFAULT_LIMITS.get("user", 100))
                    tiers.append((f"user:{user_id}", user_limit))
                dec = self._rate_limiter.check_hierarchy(tiers, tier_label=user_tier)
                if not dec.allowed:
                    denied_tier = tiers[-1][0] if tiers else "unknown"
                    for k, _ in reversed(tiers):
                        c = self._rate_limiter.check(k, limit=1)
                        if not c.allowed:
                            denied_tier = k
                            break
                    logger.warning(
                        "Rate limit exceeded for %s (retry_after=%.0fs, tier=%s)",
                        denied_tier,
                        dec.retry_after,
                        user_tier,
                    )
                    tier_base = denied_tier.split(":")[0] if ":" in denied_tier else denied_tier
                    tier_label = tier_base.capitalize()
                    if tier_base == "global":
                        err_msg = f"Rate limit exceeded. Retry after {dec.retry_after}s"
                    elif tier_base in ("user", "session"):
                        err_msg = f"{tier_label} rate limit exceeded. Retry after {dec.retry_after}s"
                    else:
                        err_msg = f"Rate limit exceeded. Retry after {dec.retry_after}s"
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
                        error=err_msg,
                        rate_limited=True,
                        retry_after=dec.retry_after,
                    )
            except Exception as e:
                logger.warning("Rate limiter check failed: %s", e)

        if (
            identity is None
            or not isinstance(identity, dict)
            or not identity.get("is_authenticated")
            or not identity.get("user_id")
        ):
            logger.warning("Missing authenticated identity in process() call — ToolGateway will enforce at execution")

        if self._context_engine:
            await self._emit(
                event_types.CONTEXT_LOADING, component="context_engine", session_id=session_id, request_id=execution_id
            )
            context_load_start = datetime.now(timezone.utc)
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                context["system"] = sys_ctx.to_dict()
                context["system_summary"] = sys_ctx.summary()
                context_load_end = datetime.now(timezone.utc)
                context_load_ms = (context_load_end - context_load_start).total_seconds() * 1000
                logger.info(f"[TIMING] Context Collection: {context_load_ms:.2f}ms")
                await self._emit(
                    event_types.CONTEXT_LOADED,
                    component="context_engine",
                    session_id=session_id,
                    request_id=execution_id,
                    status="completed",
                )
            except Exception as e:
                logger.warning("Context collection failed: %s", e)
                await self._emit(
                    event_types.CONTEXT_LOADED,
                    component="context_engine",
                    session_id=session_id,
                    request_id=execution_id,
                    status="failed",
                )

        user_id = (
            identity.get("user_id")
            if isinstance(identity, dict)
            else getattr(identity, "user_id", None)
            if identity is not None
            else None
        )

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
            memory_start = datetime.now(timezone.utc)
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
            memory_end = datetime.now(timezone.utc)
            memory_ms = (memory_end - memory_start).total_seconds() * 1000
            logger.info(f"[TIMING] Memory Retrieval: {memory_ms:.2f}ms")

        if self._deep_context:
            deep_context_start = datetime.now(timezone.utc)
            try:
                deep_ctx = await self._deep_context.collect()
                context["deep_context"] = deep_ctx
                context["deep_context_summary"] = self._deep_context.summary(deep_ctx)
                logger.info("Deep context injected: %s", deep_ctx.get("deep_context_summary", ""))
            except Exception as e:
                logger.warning("Deep context injection failed: %s", e)
            deep_context_end = datetime.now(timezone.utc)
            deep_context_ms = (deep_context_end - deep_context_start).total_seconds() * 1000
            logger.info(f"[TIMING] Deep Context Collection: {deep_context_ms:.2f}ms")
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
            intent_parse_start = datetime.now(timezone.utc)
            intent = self._intent_engine.parse(utterance, context)
            intent_parse_end = datetime.now(timezone.utc)
            intent_parse_ms = (intent_parse_end - intent_parse_start).total_seconds() * 1000
            logger.info(f"[TIMING] Intent Parsing: {intent_parse_ms:.2f}ms")
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
                planner_start = datetime.now(timezone.utc)
                app_profiles = None
                deep_ctx = context.get("deep_context")
                if deep_ctx and isinstance(deep_ctx, dict):
                    app_profiles = deep_ctx.get("installed_apps")
                plan = self._planner.plan(intent, context, app_profiles=app_profiles)
                planner_end = datetime.now(timezone.utc)
                planner_ms = (planner_end - planner_start).total_seconds() * 1000
                logger.info(f"[TIMING] Planner: {planner_ms:.2f}ms (steps={len(plan.steps)})")
                if self._plan_cache:
                    self._plan_cache.set(intent, plan)

        exec_plan = self._build_exec_plan(intent, plan, context)

        if self._intelligence is not None:
            try:
                strategy = self._intelligence.decide_strategy(utterance, intent, context)
                context["model_strategy"] = strategy
                exec_plan.model_strategy = strategy.to_dict()
                logger.info(
                    "Model strategy decided: %s (%s) for %s",
                    strategy.strategy.value,
                    strategy.complexity,
                    intent.target,
                )
            except Exception as exc:
                logger.debug("Model strategy decision skipped: %s", exc)
            try:
                recommendation = self._intelligence.recommend_model(intent.target or utterance, context)
                context["intelligence_recommendation"] = recommendation
                exec_plan.capability_recommendation = recommendation.to_dict()
            except Exception as exc:
                logger.debug("Capability recommendation skipped: %s", exc)

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

        # Execution history persistence (FASE 5.4)
        if self._intelligence is not None:
            try:
                selected_model = ""
                rec = getattr(exec_plan, "router_decision", None)
                if rec is not None:
                    selected_model = getattr(rec, "model", "") or getattr(rec, "model_id", "")
                if not selected_model and exec_plan.capability_recommendation:
                    selected_model = exec_plan.capability_recommendation.get("recommended_model", "")
                risk_level = ""
                if result.decision is not None:
                    risk_level = str(getattr(result.decision, "risk_level", "") or "")
                cost = 0.0
                if result.tool_result is not None:
                    cost = float(getattr(result.tool_result, "cost", 0.0) or 0.0)
                tools_used = [s.tool_id for s in plan.steps]
                await self._intelligence.record_execution(
                    execution_id=execution_id,
                    user_request=utterance,
                    intent=f"{intent.action}:{intent.target}",
                    task_type=exec_plan.task_type.value
                    if hasattr(exec_plan.task_type, "value")
                    else str(exec_plan.task_type),
                    selected_model=selected_model,
                    tools_used=tools_used,
                    duration=(datetime.now(timezone.utc) - start).total_seconds(),
                    success=result.error is None and not result.blocked,
                    failure_reason=result.error,
                    risk_level=risk_level,
                    cost=cost,
                    confidence_score=float(intent.confidence or 0.0),
                    error=result.error,
                )
            except Exception as exc:
                logger.debug("Execution history persistence skipped: %s", exc)

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
        await self._emit(
            event_types.PIPELINE_STARTED, component="pipeline", session_id=session_id, request_id=execution_id
        )

        # Validation (structural only — grounding moved after security pipeline)
        validation_error = self._validate_executable_plan(intent, plan)
        if validation_error:
            tool_result = ToolResult.fail(error=validation_error, tool_id=intent.target or "planner")
            result = ExecutionResult(plan=exec_plan, tool_result=tool_result, error=validation_error)
            self._store_memory(execution_id, start, raw_input, intent, plan, None, context, result)
            return self._attach_advisory(result)

        # Simulation
        simulation_result = None
        if self._simulation and not dry_run and not skip_simulation:
            simulation_start = datetime.now(timezone.utc)
            try:
                simulation_result = await self._simulation.simulate(plan, context)
                context["simulation"] = {
                    "overall_risk": simulation_result.overall_risk,
                    "requires_confirmation": simulation_result.requires_confirmation,
                    "summary": simulation_result.summary,
                    "impact_count": len(simulation_result.impacts),
                    "has_irreversible": any(i.irreversible for i in simulation_result.impacts),
                }
                simulation_end = datetime.now(timezone.utc)
                simulation_ms = (simulation_end - simulation_start).total_seconds() * 1000
                logger.info(
                    "Simulation: risk=%s, confirm=%s, steps=%d, took %.2fms",
                    simulation_result.overall_risk,
                    simulation_result.requires_confirmation,
                    len(simulation.impacts),
                    simulation_ms
                )
            except Exception as e:
                logger.warning("Simulation failed: %s", e)

        # Risk Classification (contextual, antes de la decisión)
        risk_classification = None
        if self._risk_classifier is not None:
            try:
                from .risk_classifier import RiskClassifier

                risk_classification = self._risk_classifier.classify(
                    intent, plan, context, simulation_result=simulation_result
                )
                logger.info(
                    "RiskClassifier: level=%s score=%.2f for %s/%s",
                    risk_classification.level.value if risk_classification else "?",
                    risk_classification.score if risk_classification else 0,
                    intent.action,
                    intent.target,
                )
            except Exception as e:
                logger.warning("RiskClassifier failed: %s", e)

        # Decision (RiskClassification es fuente primaria)
        decision: Optional[DecisionResult] = None
        if self._decision_engine:
            await self._emit(
                event_types.POLICY_VALIDATING, component="policy_engine", session_id=session_id, request_id=execution_id
            )
            decision_start = datetime.now(timezone.utc)
            decision = await self._evaluate_decision(
                plan, context, simulation_result=simulation_result, risk_classification=risk_classification
            )
            decision_end = datetime.now(timezone.utc)
            decision_ms = (decision_end - decision_start).total_seconds() * 1000
            logger.info(f"[TIMING] Policy/Decision Evaluation: {decision_ms:.2f}ms")
            decision_value = (
                decision.decision
                if isinstance(decision.decision, str)
                else getattr(decision.decision, "value", str(decision.decision))
            )
            await self._emit(
                event_types.POLICY_VALIDATED,
                component="policy_engine",
                session_id=session_id,
                request_id=execution_id,
                status="completed",
                details={"decision": decision_value},
            )
            safe_read_only_shortcut = self._decision_engine.should_skip_decision(intent) and not (
                simulation_result and simulation_result.requires_confirmation
            )
            if safe_read_only_shortcut and decision.decision == Decision.REQUIRE_CONFIRM:
                decision = DecisionResult(
                    decision=Decision.APPROVE,
                    plan=plan,
                    reason="Consulta de solo lectura aprobada sin confirmación interactiva.",
                    context_factors=decision.context_factors,
                    base_risk_score=decision.base_risk_score,
                    context_modifier=decision.context_modifier,
                    final_risk_score=decision.final_risk_score,
                )
            # A durable PlanApprovalGrant is the plan-level authority for a
            # resumed plan: it must not be re-blocked as a fresh cross-confirm.
            # Step-level bindings are still enforced per step by
            # ConfirmationBroker.issue_next_step_grant -> ToolExecutionGuard.
            # An explicit REJECT below remains a hard stop.
            if context.get("approved_plan_grant_id") and decision.decision == Decision.REQUIRE_CONFIRM:
                decision = DecisionResult(
                    decision=Decision.APPROVE,
                    plan=plan,
                    reason="Plan aprobado por consentimiento durable (grant aprobado).",
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
                error="No puedo ejecutar esta acción porque excede el nivel de riesgo permitido.",
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
                    # Only store essential context fields to avoid bloating memory
                    "context": {
                        "execution_id": context.get("execution_id"),
                        "session_id": context.get("session_id"),
                        "user_id": context.get("identity", {}).get("user_id") if isinstance(context.get("identity"), dict) else None,
                    },
                },
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat(),
                ttl_seconds=600,
            )
            if self._memory:
                self._memory.store_pending_action(pending)

            # Registrar solicitud de consentimiento (único punto de auditoría)
            if self._consent_service is not None:
                identity = context.get("identity")
                user_id = identity.get("user_id") if isinstance(identity, dict) else None
                if user_id:
                    self._consent_service.record_request(
                        user_id=user_id,
                        tool_id=exec_plan.tool_id,
                        action_id=action_id,
                        risk_level=str(risk_classification.level.value) if risk_classification else "unknown",
                    )

            sim_summary = simulation_result.summary if simulation_result else decision.reason
            logger.warning("Execution BLOCKED: %s (action_id=%s)", reason, action_id)
            user_message = "Necesito tu autorización para continuar con esta acción."
            if simulation_result:
                for imp in simulation_result.impacts:
                    if imp.tool_id == "executor.launch" and imp.processes_affected:
                        user_message = f"Necesito tu autorización para abrir {imp.processes_affected[0]}."
                        break
            result = ExecutionResult(
                plan=exec_plan,
                decision=decision,
                simulated=True,
                blocked=True,
                action_id=action_id,
                simulation_summary=sim_summary,
                error=user_message,
            )
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            return self._attach_advisory(result)

        # Grounding validation (after security pipeline — grounding can block but never replace security)
        grounding_validation_error = self._validate_grounding_plan(intent, plan)
        if grounding_validation_error:
            logger.warning("Grounding requirements cannot be satisfied: %s", grounding_validation_error)
            result = ExecutionResult(
                plan=exec_plan,
                decision=decision,
                simulated=False,
                blocked=False,
                error="No se pudo verificar la información necesaria antes de ejecutar.",
            )
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            return self._attach_advisory(result)

        # Pre-execution grounding: run grounding tools first, reject if evidence missing
        grounding_step_ids = self._grounding_step_ids(intent)
        grounding_step_results: List[StepResult] = []
        grounding_tool_result: Optional[ToolResult] = None
        if grounding_step_ids and not dry_run:
            grounding_start = datetime.now(timezone.utc)
            grounding_only = Plan(
                steps=[s for s in plan.steps if s.tool_id in grounding_step_ids],
                intent=intent,
                description="Grounding pre-check",
            )
            grounding_levels = self._planner.resolve_dependencies(grounding_only)
            grounding_exec_start = datetime.now(timezone.utc)
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
            grounding_exec_end = datetime.now(timezone.utc)
            grounding_exec_ms = (grounding_exec_end - grounding_exec_start).total_seconds() * 1000
            logger.info(f"[TIMING] Grounding Execution: {grounding_exec_ms:.2f}ms")
            grounding_ok = all(sr.success for sr in grounding_step_results)
            if grounding_ok:
                grounding_verify_start = datetime.now(timezone.utc)
                grounding_results, grounding_satisfied = self._verify_grounding_results(
                    intent, grounding_step_results, dry_run=dry_run
                )
                grounding_verify_end = datetime.now(timezone.utc)
                grounding_verify_ms = (grounding_verify_end - grounding_verify_start).total_seconds() * 1000
                logger.info(f"[TIMING] Grounding Verification: {grounding_verify_ms:.2f}ms")
                if not grounding_satisfied:
                    failed_reqs = [
                        r.category.value for r in getattr(intent, "grounding_requirements", []) if r.required
                    ]
                    logger.warning("Pre-execution grounding FAILED for: %s", failed_reqs)
                    result = ExecutionResult(
                        plan=exec_plan,
                        decision=decision,
                        simulated=False,
                        blocked=False,
                        error="No se pudo verificar la información necesaria antes de ejecutar.",
                        grounding_results=grounding_results,
                        grounding_satisfied=False,
                        step_results=grounding_step_results,
                        tool_result=grounding_tool_result,
                    )
                    self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
                    return self._attach_advisory(result)
                logger.info("Pre-execution grounding PASSED for intent %s/%s", intent.action, intent.target)
            else:
                failed = [{"tool_id": sr.tool_id, "error": sr.error} for sr in grounding_step_results if not sr.success]
                logger.warning("Pre-execution grounding tool(s) FAILED: %s", failed)
                grounding_results, _ = self._verify_grounding_results(intent, grounding_step_results, dry_run=dry_run)
                result = ExecutionResult(
                    plan=exec_plan,
                    decision=decision,
                    simulated=False,
                    blocked=False,
                    error="Error al ejecutar las verificaciones previas necesarias.",
                    grounding_results=grounding_results,
                    grounding_satisfied=False,
                    step_results=grounding_step_results,
                    tool_result=grounding_tool_result,
                )
                self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
                return self._attach_advisory(result)

        # Execution: run non-grounding plan steps (grounding already verified)
        await self._emit(
            event_types.EXECUTION_STARTED,
            component="execution",
            session_id=session_id,
            request_id=execution_id,
            details={"step_count": len(plan.steps)},
        )
        execution_start = datetime.now(timezone.utc)
        grounding_executed_ids = {sr.step_id for sr in grounding_step_results}
        step_results: List[StepResult] = []
        step_results.extend(grounding_step_results)
        tool_result: Optional[ToolResult] = grounding_tool_result
        executed: List[Tuple[PlanStep, StepResult]] = []
        rollback_actions: List[Dict[str, Any]] = []

        grounding_pre_verified = bool(grounding_step_ids and not dry_run)
        levels = self._planner.resolve_dependencies(Plan(steps=plan.steps, intent=intent, description="Main execution"))
        if context.get("approved_plan_grant_id"):
            context["approved_plan_step_indexes"] = {step.id: index for index, step in enumerate(plan.steps)}
            # Durable grants are a strict sequence: no two independently
            # authorized steps may race, even if the dependency graph permits it.
            levels = [[step] for step in plan.steps]
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

        execution_end = datetime.now(timezone.utc)
        execution_ms = (execution_end - execution_start).total_seconds() * 1000
        logger.info(f"[TIMING] Tool Execution: {execution_ms:.2f}ms (steps={len(step_results)})")

        # Grounding verification (post-execution audit)
        grounding_results, grounding_satisfied = self._verify_grounding_results(intent, step_results, dry_run=dry_run)
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
        if context.get("approved_plan_grant_id") and not result.error and all(item.success for item in step_results):
            broker = getattr(self._tool_gateway, "_confirmation_broker", None)
            identity = context.get("identity") or {}
            if broker and isinstance(identity, dict):
                identity_hash = broker._hash(
                    {"user_id": identity.get("user_id", ""), "session_id": identity.get("session_id", "")}
                )
                if not broker.complete_plan(
                    context["approved_plan_grant_id"],
                    user_id=identity.get("user_id", ""),
                    session_id=identity.get("session_id", ""),
                    identity_hash=identity_hash,
                ):
                    result.error = "durable plan completion failed"
        elif context.get("approved_plan_grant_id") and result.error:
            broker = getattr(self._tool_gateway, "_confirmation_broker", None)
            identity = context.get("identity") or {}
            if broker and isinstance(identity, dict):
                broker.fail_plan(
                    context["approved_plan_grant_id"],
                    user_id=identity.get("user_id", ""),
                    session_id=identity.get("session_id", ""),
                    identity_hash=broker._hash(
                        {
                            "user_id": identity.get("user_id", ""),
                            "session_id": identity.get("session_id", ""),
                        }
                    ),
                )
        if not dry_run and not grounding_satisfied and not result.error and not grounding_pre_verified:
            result.error = "No se pudo obtener la información necesaria para ejecutar la acción."
        if not dry_run:
            await self._emit(
                event_types.AUDIT_STARTED, component="audit", session_id=session_id, request_id=execution_id
            )
            audit_start = datetime.now(timezone.utc)
            self._store_memory(execution_id, start, raw_input, intent, plan, decision, context, result)
            audit_end = datetime.now(timezone.utc)
            audit_ms = (audit_end - audit_start).total_seconds() * 1000
            logger.info(f"[TIMING] Audit/Memory Storage: {audit_ms:.2f}ms")
            await self._emit(
                event_types.AUDIT_COMPLETED,
                component="audit",
                session_id=session_id,
                request_id=execution_id,
                status="completed",
            )
        await self._emit(
            event_types.EXECUTION_COMPLETED,
            component="execution",
            session_id=session_id,
            request_id=execution_id,
            status="completed" if not result.error else "failed",
            duration=(datetime.now(timezone.utc) - start).total_seconds(),
        )
        await self._emit(
            event_types.PIPELINE_COMPLETED,
            component="pipeline",
            session_id=session_id,
            request_id=execution_id,
            status="completed" if not result.error else "failed",
        )
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
        """Execute a tool directly through the full pipeline.

        Consolida en process() para garantizar identical validaciones
        (timeout, advisory, presentation) que la ruta principal.
        """
        self._enforce_pipeline("execute_direct")
        raw_input = utterance or f"execute {tool_id}"
        override_plan = self._tool_to_override_plan(tool_id, params, utterance)
        return await self.process(
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
        duration_ms = max(
            (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            0.001,
        )
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
                    "description": step.description,
                    "model_decision": step_context.get("model_decision"),
                },
            )
        if CONSERVATIVE_MODE and step.tool_id in CONSERVATIVE_BLOCKED_TOOLS:
            return StepResult(
                step_id=step.id,
                tool_id=step.tool_id,
                success=False,
                error="Esta acci\u00f3n est\u00e1 bloqueada por configuraci\u00f3n de seguridad.",
                data={"blocked_by": "conservative_mode", "tool_id": step.tool_id},
            )

        rate_limiter = getattr(self, "_rate_limiter", None)
        rate_limit_config = getattr(self, "_rate_limit_config", None)
        if rate_limiter and rate_limit_config:
            tool_cat = step.tool_id.split(".")[0] if "." in step.tool_id else step.tool_id
            tool_limit_key = f"tool:{tool_cat}"
            tool_limit = rate_limit_config.get(tool_limit_key)
            if tool_limit is not None:
                identity = step_context.get("identity") or {}
                user_tier = identity.get("tier", "free") if isinstance(identity, dict) else "free"
                dec = rate_limiter.allow(f"tool:{tool_cat}:{step.tool_id}", limit=tool_limit, tier=user_tier)
                if not dec.allowed:
                    logger.warning("Tool rate limit exceeded for %s (retry_after=%.0fs)", step.tool_id, dec.retry_after)
                    return StepResult(
                        step_id=step.id,
                        tool_id=step.tool_id,
                        success=False,
                        error=f"Rate limit exceeded for tool category '{tool_cat}'. Retry after {dec.retry_after}s",
                        data={"rate_limited": True, "retry_after": dec.retry_after, "tool_category": tool_cat},
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
            # `filesystem.search` is defined in terms of `query` and `root`.
            # Do not inject an empty legacy `path`: the central argument
            # validator correctly treats an explicit empty path as invalid.
            step_params.setdefault("query", intent.parameters.get("query", ""))
            step_params.setdefault("root", intent.parameters.get("root", "C:\\"))

        execution_grant = None
        plan_grant_id = step_context.get("approved_plan_grant_id")
        if plan_grant_id:
            broker = getattr(self._tool_gateway, "_confirmation_broker", None)
            identity = step_context.get("identity") or {}
            user_id = identity.get("user_id", "") if isinstance(identity, dict) else ""
            session_id = identity.get("session_id", "") if isinstance(identity, dict) else ""
            identity_hash = broker._hash({"user_id": user_id, "session_id": session_id}) if broker else ""
            plan = broker._grants.get_plan(plan_grant_id) if broker else None
            step_index = (step_context.get("approved_plan_step_indexes") or {}).get(step.id)
            if not plan or step_index is None:
                return StepResult(
                    step_id=step.id, tool_id=step.tool_id, success=False, error="durable plan grant context is invalid"
                )
            try:
                execution_grant = broker.issue_next_step_grant(
                    plan_grant_id=plan_grant_id,
                    user_id=user_id,
                    session_id=session_id,
                    identity_hash=identity_hash,
                    step_id=step.id,
                    step_index=step_index,
                    tool_id=step.tool_id,
                    params=step_params,
                    expires_at=plan["expires_at"],
                )
            except (PermissionError, ValueError) as exc:
                return StepResult(step_id=step.id, tool_id=step.tool_id, success=False, error=str(exc))

        attempted_tools: List[str] = []

        async def _do_execute(tool_id: Optional[str] = None):
            tid = tool_id or step.tool_id
            attempted_tools.append(tid)
            session_id = context.get("session_id")
            execution_id = context.get("execution_id", "")
            await self._emit(
                event_types.TOOL_STARTED,
                component="tool_gateway",
                session_id=session_id,
                request_id=execution_id,
                tool=tid,
            )
            execute_kwargs = {
                "tool_id": tid,
                "params": step_params,
                "context": step_context,
                "source": "approved_plan" if execution_grant is not None else "orchestrator",
            }
            # Keep non-approved-plan callers compatible with the established
            # pipeline contract.  Authority is still explicit: approved plans
            # always carry the typed context, never a null stand-in.
            if execution_grant is not None:
                execute_kwargs["execution_grant"] = execution_grant
            result = await self._execution_pipeline.execute(**execute_kwargs)
            await self._emit(
                event_types.TOOL_FINISHED,
                component="tool_gateway",
                session_id=session_id,
                request_id=execution_id,
                tool=tid,
                status="completed" if result.success else "failed",
                duration=result.duration_ms / 1000.0 if result.duration_ms else None,
            )
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

        if step.model_decision:
            if self._intelligence:
                try:
                    await self._intelligence.learn_from_model_result(
                        model_id=step.model_decision.model,
                        task_type=step.model_decision.task_type,
                        intent=step.model_decision.task_type,
                        latency_ms=s_result.duration_ms or 0.0,
                        tokens_used=0,
                        cost=0.0,
                        success=s_result.success,
                        error=s_result.error,
                    )
                except Exception as e:
                    logger.warning("Failed to record intelligence: %s", e)

            if self._cost_tracker:
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
            if requirement.required and (not requirement.tool_id or requirement.tool_id not in planned_tools):
                return f"The plan cannot satisfy required grounding for {requirement.category.value}"
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
        
        # Build lookup map for O(1) access instead of O(n) scanning per requirement
        results_by_tool = {}
        for result in step_results:
            results_by_tool[result.tool_id] = result
            if result.executed_tool_id:
                results_by_tool[result.executed_tool_id] = result
        
        for requirement in intent.grounding_requirements:
            matching = results_by_tool.get(requirement.tool_id)
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
                    "error": None
                    if grounded or dry_run
                    else (matching.error if matching else "Required tool result is missing"),
                }
            )
        return evidence, satisfied

    @staticmethod
    def _validate_executable_plan(intent: Intent, plan: Plan) -> Optional[str]:
        """Reject incomplete executable plans before simulation or confirmation."""
        if intent.confidence < 0.6:
            return None
        if not plan.steps:
            return "No se pudo generar un plan de acción ejecutable."
        required = {
            "executor.command": "command",
            "executor.launch": "app_name",
            "executor.kill": "pid",
        }.get(intent.target)
        if required and intent.parameters.get(required) is None:
            return f"{required} is required for {intent.target}"
        if any(not step.tool_id for step in plan.steps):
            return "El plan de acción contiene un paso sin herramienta asignada."
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
            return await self._execution_pipeline.execute(
                tool_id,
                params,
                context,
                source="rollback",
            )

        return await self._rollback_manager.rollback(completed, _exec)

    async def approve_with_modifications(
        self,
        action_id: str,
        modified_steps: List[Dict[str, Any]],
        approver_identity: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Deprecated compatibility adapter; pending records are diagnostic only.

        Modified plans must be submitted through the durable confirmation flow
        so their canonical hash and plan grant are established before execution.
        """
        return self._deprecated_approval_result(
            "approve_with_modifications is deprecated and cannot authorize execution; "
            "reconfirm the modified plan using a durable execution grant."
        )

    async def approve_execution(
        self,
        action_id: str,
        approved: bool,
        approver_identity: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Deprecated compatibility adapter; it never grants execution authority.

        Durable plan and step grants are the only admissible approval artefacts.
        Legacy pending actions remain diagnostic records and must be reconfirmed
        through the durable confirmation endpoint.
        """
        empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
        return ExecutionResult(
            plan=ExecutionPlan(
                intent=empty_intent,
                plan=Plan(intent=empty_intent, steps=[]),
                tool_id="",
                tool_params={},
                task_type=TaskType.QUICK,
            ),
            error="approve_execution is deprecated and cannot authorize execution; reconfirm using a durable execution grant.",
        )

    async def resume_approved_plan(self, plan_grant_id: str, identity: Dict[str, Any]) -> ExecutionResult:
        """Resume only the immutable plan bound to a durable approval grant."""
        broker = getattr(self._tool_gateway, "_confirmation_broker", None)
        user_id = identity.get("user_id", "") if isinstance(identity, dict) else ""
        session_id = identity.get("session_id", "") if isinstance(identity, dict) else ""
        identity_hash = broker._hash({"user_id": user_id, "session_id": session_id}) if broker else ""
        if broker is None:
            return self._deprecated_approval_result("durable confirmation broker is unavailable")
        try:
            resumed = broker.resume_approved_plan(
                plan_grant_id, user_id=user_id, session_id=session_id, identity_hash=identity_hash
            )
            plan = self._plan_from_dict(resumed["payload"])
            if not plan.steps:
                return self._deprecated_approval_result("approved plan is empty or invalid")
            return await self.process(
                "",
                identity=identity,
                session_id=session_id,
                override_plan=plan,
                approved_plan_grant_id=plan_grant_id,
            )
        except (PermissionError, ValueError) as exc:
            return self._deprecated_approval_result(str(exc))

    @staticmethod
    def _deprecated_approval_result(error: str) -> ExecutionResult:
        empty_intent = Intent(action="", target="", parameters={}, confidence=0.0, raw_input="")
        return ExecutionResult(
            plan=ExecutionPlan(
                intent=empty_intent,
                plan=Plan(intent=empty_intent, steps=[]),
                tool_id="",
                tool_params={},
                task_type=TaskType.QUICK,
            ),
            error=error,
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
    def intelligence(self) -> Any:
        return self._intelligence

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
                error="La ejecución multi-agente no está configurada.",
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

    async def _sync_offline_item(self, item: QueueItem) -> bool:
        """Re-execute a deferred operation once the network is restored.

        Previously a no-op stub that marked every item as synced without doing
        anything; now it replays the deferred operation through the same
        execution pipeline so offline work is actually completed.
        """
        op_type = item.operation_type
        payload = item.payload or {}
        try:
            if op_type == "orchestrator.process":
                utterance = payload.get("utterance", "")
                if not utterance:
                    logger.warning("Offline item %s has no utterance to replay", item.id)
                    return False
                identity = payload.get("identity")
                session_id = payload.get("session_id")
                result = await self.process(
                    utterance,
                    identity=identity,
                    session_id=session_id,
                    skip_simulation=False,
                )
                if result.error:
                    logger.warning("Offline replay of %s failed: %s", item.id, result.error)
                    return False
                logger.info("Offline item %s replayed successfully", item.id)
                return True
            logger.warning("Offline item %s has unsupported operation type %r", item.id, op_type)
            return False
        except Exception as exc:
            logger.warning("Offline replay of %s raised: %s", item.id, exc)
            return False

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
                error="La cola de ejecución offline no está configurada.",
            )

        item = self._offline_queue.enqueue(
            "orchestrator.process",
            {"utterance": utterance, "session_id": session_id, "identity": identity},
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
    def observability(self):
        """The production ObservabilityEngine wired into this orchestrator (may be None)."""
        return self._observability

    @property
    def alert_manager(self) -> AlertManager:
        return self._alert_manager

    def check_alerts(self) -> Dict[str, Any]:
        self._alert_manager.check_all()
        return self._alert_manager.to_dict()
