"""Sentinel Runtime — Único pipeline de razonamiento, planificación y ejecución.

Arquitectura objetivo:
  User Request
       ↓
  SentinelRuntime.process()
       ├── IntentEngine        (analyze → IntentResult / TaskIntent)
       ├── ContextEngine       (collect → SystemContext)
       ├── Planner             (plan → Plan)
       ├── IntelligenceEngine  (recommend → IntelligenceRecommendation)
       ├── SecurityEngine      (Policy + Risk + Consent + Decision)
       ├── ExecutionEngine     (ToolGateway — único gate)
       ├── MemoryEngine        (store + retrieve)
       └── LearningEngine      (metrics + feedback)

Reglas:
  1. Ningún componente ejecuta herramientas directamente.
     Toda ejecución pasa por ToolGateway → PolicyEngine → Tool.
  2. Un solo dueño del flujo: SentinelRuntime.
  3. Los módulos inteligentes (IntelligenceEngine) son consultados,
     no toman decisiones autónomas.
  4. NO existe lógica específica de herramientas aquí.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class TaskIntent:
    """Modelo unificado de intención de tarea.

    Reemplaza IntentCategory + TaskType como representación única
    de lo que el usuario quiere, qué capacidades necesita y qué
    riesgo conlleva.
    """
    objective: str
    category: str
    risk_level: str = "low"
    required_capabilities: List[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_input: str = ""
    action: str = ""
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SentinelRequest:
    utterance: str
    session_id: str = ""
    user_id: str = ""
    conversation_id: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    timeout: Optional[float] = None


@dataclass
class SentinelResponse:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_id: str = ""
    duration_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_id": self.execution_id,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
        }


class SentinelRuntime:
    """Punto único de entrada para toda operación en Sentinel.

    Pipeline completo (en orden):
      1. RateLimit      → RateLimiter
      2. Context        → ContextEngine
      3. Intent         → IntentEngine
      4. Intelligence   → IntelligenceEngine (recommend)
      5. Plan           → Planner
      6. Security       → PolicyEngine + RiskClassifier + ConsentService
      7. Decision       → DecisionEngine
      8. Model Select   → ModelRouter
      9. Execution      → ToolGateway (único gate)
      10. Memory        → MemoryBackend
      11. Learning      → PerformanceIntelligence + FeedbackEngine
      12. Audit         → AuditService
      13. Response
    """

    def __init__(
        self,
        intent_engine: Any = None,
        policy_engine: Any = None,
        planner: Any = None,
        tool_gateway: Any = None,
        model_router: Any = None,
        audit_service: Any = None,
        consent_service: Any = None,
        # Intelligence Layer
        intelligence_engine: Any = None,
        performance_intelligence: Any = None,
        feedback_engine: Any = None,
        model_ranking: Any = None,
        time_predictor: Any = None,
        # Legacy compatibility (Orchestrator dependencies)
        context_engine: Any = None,
        memory: Any = None,
        risk_classifier: Any = None,
        simulation_engine: Any = None,
        decision_engine: Any = None,
        rate_limiter: Any = None,
        event_bus: Any = None,
        # Capability Engine
        capability_engine: Any = None,
        # Observability
        observability_engine: Any = None,
    ):
        self._intent = intent_engine
        self._policy = policy_engine
        self._planner = planner
        self._gateway = tool_gateway
        self._router = model_router
        self._audit = audit_service
        self._consent = consent_service
        self._intel = intelligence_engine
        self._perf = performance_intelligence
        self._feedback = feedback_engine
        self._ranking = model_ranking
        self._predictor = time_predictor
        self._context = context_engine
        self._memory = memory
        self._risk = risk_classifier
        self._simulation = simulation_engine
        self._decision = decision_engine
        self._rate_limiter = rate_limiter
        self._event_bus = event_bus
        self._capability = capability_engine
        self._obs = observability_engine
        self._db: Any = None
        self._audit_log: List[Dict[str, Any]] = []

    # ── Setters (inyección post-construcción) ─────────────────

    def set_intent_engine(self, engine: Any) -> None:
        self._intent = engine

    def set_intelligence_engine(self, engine: Any) -> None:
        self._intel = engine

    def set_capability_engine(self, engine: Any) -> None:
        self._capability = engine

    def set_context_engine(self, engine: Any) -> None:
        self._context = engine

    def set_planner(self, planner: Any) -> None:
        self._planner = planner

    def set_memory(self, memory: Any) -> None:
        self._memory = memory

    def set_router(self, router: Any) -> None:
        self._router = router
        if self._ranking and hasattr(router, "set_model_ranking"):
            router.set_model_ranking(self._ranking)

    def set_gateway(self, gateway: Any) -> None:
        self._gateway = gateway

    def set_decision_engine(self, engine: Any) -> None:
        self._decision = engine

    def set_policy_engine(self, engine: Any) -> None:
        self._policy = engine

    def set_risk_classifier(self, classifier: Any) -> None:
        self._risk = classifier

    def set_consent_service(self, service: Any) -> None:
        self._consent = service

    def set_audit_service(self, service: Any) -> None:
        self._audit = service

    # ── Getters públicos ──────────────────────────────────────

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    @property
    def performance_intelligence(self) -> Any:
        return self._perf

    @property
    def feedback_engine(self) -> Any:
        return self._feedback

    @property
    def model_ranking(self) -> Any:
        return self._ranking

    @property
    def time_predictor(self) -> Any:
        return self._predictor

    @property
    def intelligence_engine(self) -> Any:
        return self._intel

    @property
    def observability(self) -> Any:
        return self._obs

    def set_observability(self, obs: Any) -> None:
        self._obs = obs

    def initialize_intelligence(self) -> None:
        """Activar suscripciones a eventos para inteligencia."""
        if self._perf is not None and self._event_bus is not None:
            try:
                self._perf.subscribe_to_events(self._event_bus)
            except Exception as e:
                logger.warning("PerformanceIntelligence event subscription failed: %s", e)
        if self._feedback is not None and self._event_bus is not None:
            try:
                self._feedback.subscribe_to_events(self._event_bus)
            except Exception as e:
                logger.warning("FeedbackEngine event subscription failed: %s", e)

    # ── Proceso principal ─────────────────────────────────────

    async def process(self, request: SentinelRequest) -> SentinelResponse:
        """Pipeline completo de una petición."""
        start = datetime.now(timezone.utc)
        execution_id = _generate_id()
        logger.info("Runtime process start: %s | %s", execution_id, request.utterance[:80])

        trace_span = None
        if self._obs:
            trace_span = self._obs.start_request_trace(request_id=execution_id, metadata={"utterance": request.utterance[:80], "user_id": request.user_id})
            self._obs.metrics.record_request(model_id="pending", success=True)

        try:
            result = await self._process_impl(request, execution_id)
            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result.duration_ms = duration
            if self._obs:
                self._obs.end_request_trace(trace_span, status="ok" if result.success else "error")
                self._obs.metrics.record_request(model_id=result.data.get("task_type", "unknown"), success=result.success, latency_ms=duration)
            self._audit_log.append({
                "action": "runtime.process",
                "execution_id": execution_id,
                "success": result.success,
                "duration_ms": duration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return result
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            if self._obs:
                self._obs.end_request_trace(trace_span, status="error")
                self._obs.metrics.record_request(model_id="unknown", success=False, latency_ms=duration)
            logger.exception("Runtime process error: %s | %s", execution_id, str(e))
            return SentinelResponse(
                success=False,
                error=str(e),
                execution_id=execution_id,
                duration_ms=duration,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    async def _process_impl(self, request: SentinelRequest, execution_id: str) -> SentinelResponse:
        context: Dict[str, Any] = dict(request.context)
        context["execution_id"] = execution_id
        context["session_id"] = request.session_id
        context["user_id"] = request.user_id

        if self._obs:
            from sentinel.observability.health.health_checker import ComponentHealth, HealthState
            self._obs.health.register("database", lambda: ComponentHealth(name="database", state=HealthState.HEALTHY if self._db else HealthState.DEGRADED, details={"connected": self._db is not None}))
            self._obs.health.register("memory", lambda: ComponentHealth(name="memory", state=HealthState.HEALTHY if self._memory else HealthState.DEGRADED, details={"available": self._memory is not None}))
            self._obs.health.register("model_router", lambda: ComponentHealth(name="model_router", state=HealthState.HEALTHY if self._router else HealthState.DEGRADED, details={"initialized": self._router is not None}))
            self._obs.health.register("tool_gateway", lambda: ComponentHealth(name="tool_gateway", state=HealthState.HEALTHY if self._gateway else HealthState.DEGRADED, details={"initialized": self._gateway is not None}))

        # ── 1. Rate limit ──
        if self._rate_limiter:
            try:
                dec = self._rate_limiter.check_hierarchy([
                    ("global", 1000),
                    (f"user:{request.user_id}", 100),
                ]) if hasattr(self._rate_limiter, "check_hierarchy") else None
                if dec and not dec.allowed:
                    return SentinelResponse(
                        success=False,
                        error=f"Rate limit exceeded. Retry after {dec.retry_after}s",
                        execution_id=execution_id,
                    )
            except Exception as e:
                logger.warning("Rate limit check failed: %s", e)

        # ── 2. Context collection ──
        if self._context:
            try:
                sys_ctx = await self._context.collect()
                context["system"] = sys_ctx.to_dict() if hasattr(sys_ctx, "to_dict") else sys_ctx
                if hasattr(sys_ctx, "summary"):
                    context["system_summary"] = sys_ctx.summary()
            except Exception as e:
                logger.warning("Context collection failed: %s", e)

        # ── 3. Intent analysis ──
        intent_result = None
        task_type = "chat"
        if self._intent:
            try:
                intent_result = self._intent.parse(request.utterance, context)
                context["intent_result"] = intent_result
                task_type = self._resolve_task_type(intent_result)
                context["task_type"] = task_type
            except Exception as e:
                logger.warning("Intent analysis failed: %s", e)

        # ── 4. Intelligence recommendation ──
        recommendation = None
        if self._intel:
            try:
                caps = self._resolve_required_capabilities(task_type, intent_result)
                recommendation = self._intel.recommend(
                    task_type=task_type,
                    required_capabilities=caps,
                    context=context,
                )
                context["intelligence_recommendation"] = recommendation
            except Exception as e:
                logger.warning("Intelligence recommendation failed: %s", e)

        # ── 5. Planning ──
        plan = None
        if self._planner and intent_result:
            try:
                plan = self._planner.plan(intent_result, context)
                context["plan"] = plan
            except Exception as e:
                logger.warning("Planning failed: %s", e)

        # ── 6. Security: Risk + Policy + Decision ──
        decision = None
        risk = None
        sim = None
        if plan:
            if self._risk:
                try:
                    risk = self._risk.classify(intent_result, plan, context)
                    context["risk"] = risk
                except Exception as e:
                    logger.warning("Risk classification failed: %s", e)

            if self._simulation:
                try:
                    sim = await self._simulation.simulate(plan, context) if hasattr(self._simulation, "simulate") else None
                    context["simulation"] = sim
                except Exception as e:
                    logger.warning("Simulation failed: %s", e)

            if self._decision:
                try:
                    decision = await self._evaluate_decision(plan, context, sim, risk)
                    context["decision"] = decision
                except Exception as e:
                    logger.warning("Decision evaluation failed: %s", e)

        # ── 7. Consent (if required) ──
        consent_granted = True
        if decision and hasattr(decision, "decision"):
            decision_str = str(decision.decision.value if hasattr(decision.decision, "value") else decision.decision)
            if decision_str in ("REQUIRE_CONFIRM", "DENY", "reject", "require_confirm"):
                if decision_str in ("DENY", "reject"):
                    return SentinelResponse(
                        success=False,
                        error=getattr(decision, "reason", "Blocked by policy"),
                        data={"intent": str(intent_result), "plan": str(plan), "decision": str(decision)},
                        execution_id=execution_id,
                    )
                if self._consent:
                    try:
                        action_id = f"run_{execution_id}"
                        user_message = getattr(decision, "reason", "Requires confirmation")
                        consent_granted = await self._request_consent(request, action_id, user_message, risk)
                    except Exception as e:
                        logger.warning("Consent request failed: %s", e)
                        consent_granted = False
                else:
                    consent_granted = False
                if not consent_granted:
                    return SentinelResponse(
                        success=False,
                        error="User denied confirmation",
                        data={"intent": str(intent_result), "plan": str(plan), "decision": str(decision)},
                        execution_id=execution_id,
                    )

        # ── 8. Model selection (with IntelligenceEngine support) ──
        model_selection = None
        if self._router:
            try:
                if recommendation and recommendation.model_id:
                    context["intel_model_id"] = recommendation.model_id
                    context["intel_fallbacks"] = recommendation.fallback_models
                model_selection = self._router.select(task_type, context)
                context["model_selection"] = model_selection
                if self._obs and model_selection:
                    provider = model_selection.get("provider") if isinstance(model_selection, dict) else getattr(model_selection, "provider", "unknown")
                    self._obs.metrics.record_request(model_id=provider, success=True)
            except Exception as e:
                if self._obs:
                    self._obs.metrics.record_request(model_id="unknown", success=False)
                logger.warning("Model selection failed: %s", e)

        # ── 8b. Time prediction ──
        time_prediction = None
        if self._predictor and plan and hasattr(plan, "steps"):
            try:
                provider_id = getattr(model_selection, "provider_id", None) if model_selection else None
                time_prediction = self._predictor.predict(
                    task_type=str(task_type or ""),
                    model_id=str(provider_id) if provider_id else None,
                )
                context["time_prediction"] = time_prediction
            except Exception as e:
                logger.warning("Time prediction failed: %s", e)

        # ── 9. Execution via ToolGateway ──
        results = []
        if plan and hasattr(plan, "steps") and not request.dry_run:
            for step in plan.steps:
                tool_id = self._resolve_tool_id(step)
                if tool_id and self._gateway:
                    try:
                        step_result = await self._gateway.execute(
                            tool_id,
                            self._step_params(step),
                            {
                                "identity": request.user_id,
                                "execution_id": execution_id,
                                "session_id": request.session_id,
                                "source": "sentinel_runtime",
                            },
                        )
                        results.append({"tool_id": tool_id, "result": step_result, "success": True})
                    except Exception as e:
                        logger.error("Tool execution failed: %s | %s", tool_id, e)
                        results.append({"tool_id": tool_id, "error": str(e), "success": False})

                    # ── 10. Performance metrics ──
                    if self._perf:
                        try:
                            self._perf.record_metric(self._build_metric(tool_id, results[-1], request))
                        except Exception as e:
                            logger.warning("Metric recording failed: %s", e)

        # ── 11. Memory ──
        if self._memory:
            try:
                if request.session_id:
                    context["session_history"] = self._memory.get_session_history(
                        request.session_id, limit=5, user_id=request.user_id
                    )
            except Exception as e:
                logger.warning("Memory retrieval failed: %s", e)

        # ── 12. Audit ──
        if self._audit:
            try:
                overall_success = all(r.get("success", False) for r in results) if results else True
                self._audit.log_action(
                    "runtime.process",
                    {
                        "execution_id": execution_id,
                        "utterance": request.utterance[:200],
                        "task_type": task_type,
                        "intent": str(intent_result),
                        "plan": str(plan),
                        "decision": str(decision),
                        "model": str(model_selection),
                        "results_count": len(results),
                    },
                    "success" if overall_success else "failure",
                    request.user_id,
                )
            except Exception as e:
                logger.warning("Audit logging failed: %s", e)

        return SentinelResponse(
            success=True,
            data={
                "utterance": request.utterance,
                "task_type": task_type,
                "intent": str(intent_result),
                "plan": str(plan),
                "decision": str(decision),
                "risk": str(risk),
                "model": str(model_selection),
                "recommendation": str(recommendation),
                "results": results,
                "consent_granted": consent_granted,
                "time_prediction": time_prediction.to_dict() if hasattr(time_prediction, "to_dict") else str(time_prediction) if time_prediction else None,
            },
            execution_id=execution_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def _evaluate_decision(
        self, plan: Any, context: Dict[str, Any],
        simulation_result: Optional[Any] = None,
        risk_classification: Optional[Any] = None,
    ) -> Any:
        if self._decision is None:
            return None
        evaluate_async = getattr(self._decision, "evaluate_async", None)
        if callable(evaluate_async):
            try:
                candidate = evaluate_async(plan, context, simulation_result=simulation_result, risk_classification=risk_classification)
            except TypeError:
                candidate = evaluate_async(plan, context, simulation_result=simulation_result)
            if hasattr(candidate, "__await__"):
                return await candidate
        return self._decision.evaluate(plan, context, simulation_result=simulation_result, risk_classification=risk_classification)

    async def _request_consent(self, request: SentinelRequest, action_id: str, reason: str, risk: Any) -> bool:
        if self._consent is None:
            return False
        try:
            result = await self._consent.request_confirmation(
                action_id=action_id,
                description=reason,
                risk_level=getattr(risk, "level", "unknown"),
                user_id=request.user_id,
                session_id=request.session_id,
                context={"utterance": request.utterance},
            )
            return bool(result)
        except Exception as e:
            logger.warning("Consent request failed: %s", e)
            return False

    # ── Helpers ────────────────────────────────────────────────

    def _resolve_task_type(self, intent_result: Any) -> str:
        """Deriva el tipo de tarea desde el resultado del intent engine."""
        if intent_result is None:
            return "chat"
        if hasattr(intent_result, "category"):
            cat = str(intent_result.category)
            mapping = {
                "CHAT": "chat", "ACTION": "tool", "CODING": "code",
                "SEARCH": "search", "DOCUMENT": "analysis", "SYSTEM_OPERATION": "tool",
                "AUTOMATION": "code", "MEMORY": "chat", "REASONING": "reasoning",
                "UNKNOWN": "chat",
            }
            return mapping.get(cat, "chat")
        if hasattr(intent_result, "action"):
            action = intent_result.action
            mapping = {
                "query": "chat", "execute": "tool", "analyze": "analysis",
                "configure": "tool", "control": "chat", "code": "code",
            }
            return mapping.get(action, "chat")
        return "chat"

    def _resolve_required_capabilities(self, task_type: str, intent_result: Any) -> Optional[List[str]]:
        cap_map = {
            "tool": ["tool_calling"],
            "code": ["coding", "reasoning"],
            "analysis": ["reasoning", "analysis"],
            "search": ["internet", "grounding"],
            "reasoning": ["reasoning"],
        }
        return cap_map.get(task_type)

    def _resolve_tool_id(self, step: Any) -> Optional[str]:
        if isinstance(step, dict):
            return step.get("tool_id") or step.get("action")
        return getattr(step, "tool_id", None) or getattr(step, "action", None)

    def _step_params(self, step: Any) -> Dict[str, Any]:
        if isinstance(step, dict):
            return step.get("params", {}) or step.get("parameters", {})
        return getattr(step, "params", {}) or getattr(step, "parameters", {})

    def _build_metric(self, tool_id: str, result: Dict[str, Any], request: SentinelRequest) -> Any:
        from sentinel.core.performance_intelligence import ExecutionMetrics
        duration = 0.0
        success = True
        if isinstance(result, dict):
            r = result.get("result", {})
            if hasattr(r, "duration_ms"):
                duration = r.duration_ms / 1000.0
            elif isinstance(r, dict):
                duration = r.get("duration_ms", 0) / 1000.0
            success = result.get("success", True)
        return ExecutionMetrics(
            model_id=tool_id,
            task_type=self._resolve_task_type(None),
            intent=request.utterance[:100],
            latency=duration,
            tokens_used=0,
            cost=0.0,
            success=success,
        )

    async def close(self) -> None:
        """Libera recursos del runtime."""
        logger.info("Runtime shutdown")


class DeprecatedRuntimeAdapter:
    """Wrapper de compatibilidad — SentinelRuntime será eliminado en FASE 2.

    Reemplaza SentinelRuntime como puente entre la API y Orchestrator.
    """

    def __init__(self, orchestrator: Any):
        self._orchestrator = orchestrator
        logger.warning(
            "DeprecatedRuntimeAdapter: SentinelRuntime is deprecated. "
            "Use Orchestrator directly. This adapter will be removed in a future release."
        )

    async def process(self, request: SentinelRequest) -> SentinelResponse:
        """Delega a Orchestrator.process() y adapta la respuesta."""
        identity = request.context.get("identity") or {}
        if request.user_id:
            identity["user_id"] = request.user_id
        result = await self._orchestrator.process(
            request.utterance,
            identity=identity,
            session_id=request.session_id,
        )
        error = result.error
        if not error and result.tool_result and not result.tool_result.success:
            error = result.tool_result.error
        return SentinelResponse(
            success=error is None,
            data=result.tool_result.data if result.tool_result else None,
            error=error,
            session_id=request.session_id,
            context=request.context,
        )

    async def close(self) -> None:
        self._orchestrator.close()


def _generate_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]
