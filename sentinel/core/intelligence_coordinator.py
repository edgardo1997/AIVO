"""IntelligenceCoordinator — única interfaz de inteligencia para Orchestrator.

Encapsula:
  - PerformanceIntelligence  (métricas de ejecución)
  - FeedbackEngine           (feedback de usuario)
  - ModelRanking             (scoring + ranking)
  - TimePredictor            (predicción de tiempo)
  - ModelDiscovery           (descubrimiento de modelos)
  - CostTracker              (estimación/registro de costos)

Flujo Orchestrator → Coordinator:
  1. analyze_request(intent, context) → IntelligenceDecision
  2. select_model(decision) → model_id
  3. predict_execution(model_id, task_type) → TimePrediction
  4. calculate_cost(model_id, tokens) → estimated_cost
  5. learn(result)                    → post-execution learning
  6. record_feedback(feedback)        → user feedback
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.core.cost_tracker import CostTracker
from sentinel.core.event_bus import EventBus
from sentinel.core.feedback_engine import (
    FeedbackEngine,
    FeedbackScore,
    FeedbackSummary,
    UserFeedback,
)
from sentinel.core.intelligence_orchestrator import (
    IntelligenceDecision,
    IntelligenceOrchestrator,
)
from sentinel.core.model_discovery import ModelDiscovery
from sentinel.core.model_ranking import ModelRanking, ModelScore
from sentinel.core.model_coordinator import (
    ModelCoordinator,
    ModelTask,
    MultiModelPlan,
    MultiModelResult,
    ModelTaskResult,
)
from sentinel.intelligence.model_capability import (
    CapabilityRecommendation,
    ModelCapabilityAnalyzer,
)
from sentinel.intelligence.model_strategy import (
    ModelStrategy,
    ModelStrategyEngine,
    StrategyType,
)
from sentinel.core.performance_intelligence import (
    ExecutionMetrics,
    ModelPerformanceSummary,
    PerformanceIntelligence,
)
from sentinel.core.time_predictor import TimePrediction, TimePredictor

logger = logging.getLogger(__name__)


class IntelligenceCoordinator:
    """Única interfaz de inteligencia para Orchestrator."""

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        cost_tracker: Optional[CostTracker] = None,
        model_registry: Any = None,
        capability_engine: Any = None,
        vault: Any = None,
        max_history: int = 10000,
    ):
        self._event_bus = event_bus

        # Nuevos componentes
        self._performance = PerformanceIntelligence(event_bus=event_bus, max_history=max_history)
        self._feedback = FeedbackEngine(event_bus=event_bus, max_history=max_history)
        self._ranking = ModelRanking(
            performance_intelligence=self._performance,
            feedback_engine=self._feedback,
            event_bus=event_bus,
        )
        if model_registry is not None:
            self._ranking.set_model_registry(model_registry)
        self._time_predictor = TimePredictor(performance_intelligence=self._performance)
        self._discovery = ModelDiscovery(vault=vault, model_registry=model_registry)
        self._cost_tracker = cost_tracker

        # Model orchestration (model selection)
        self._orchestrator = IntelligenceOrchestrator(
            model_registry=model_registry,
            capability_engine=capability_engine,
        )
        self._orchestrator.set_performance_intelligence(self._performance)
        self._orchestrator.set_model_ranking(self._ranking)
        self._orchestrator.set_time_predictor(self._time_predictor)

        # Capability Intelligence (FASE 4.3)
        self._capability_analyzer = ModelCapabilityAnalyzer(
            registry=model_registry,
            capability_engine=capability_engine,
            ranking=self._ranking,
        )

        # Multi-model coordination (FASE 4.5)
        self._model_coordinator = ModelCoordinator(model_registry=model_registry)
        self._model_router = None

        # Model Strategy Engine (FASE 4.6)
        self._strategy_engine = ModelStrategyEngine(
            registry=model_registry,
            capability_analyzer=self._capability_analyzer,
            coordinator=self,
            ranking=self._ranking,
        )

        # Repositorios (persistencia) — opcionales, se inyectan post-construcción
        self._metric_repo = None
        self._feedback_repo = None
        self._model_repo = None
        self._execution_repo = None
        self._performance_repo = None
        self._preference_repo = None
        self._restored_preferences: Dict[tuple, Any] = {}
        self._registry = model_registry

    # ── Injection de dependencias opcionales ─────────────────────

    def set_metric_repository(self, repo: Any) -> None:
        self._metric_repo = repo

    def set_feedback_repository(self, repo: Any) -> None:
        self._feedback_repo = repo

    def set_model_repository(self, repo: Any) -> None:
        self._model_repo = repo
        if self._discovery:
            self._discovery.set_model_repository(repo)

    def set_execution_repository(self, repo: Any) -> None:
        self._execution_repo = repo

    def set_model_performance_repository(self, repo: Any) -> None:
        self._performance_repo = repo

    def set_user_preference_repository(self, repo: Any) -> None:
        self._preference_repo = repo

    def set_model_registry(self, registry: Any) -> None:
        self._registry = registry
        self._orchestrator.set_model_registry(registry)
        if self._discovery:
            self._discovery.set_model_registry(registry)
        self._capability_analyzer.set_registry(registry)
        self._ranking.set_model_registry(registry)
        self._model_coordinator.set_model_registry(registry)
        self._strategy_engine.set_registry(registry)

    def set_capability_engine(self, engine: Any) -> None:
        self._orchestrator.set_capability_engine(engine)
        self._capability_analyzer.set_capability_engine(engine)

    def set_vault(self, vault: Any) -> None:
        if self._discovery:
            self._discovery.set_vault(vault)

    def set_resource_intelligence(self, ri: Any) -> None:
        self._orchestrator.set_resource_intelligence(ri)

    def set_cost_tracker(self, tracker: CostTracker) -> None:
        self._cost_tracker = tracker

    # ── 1. Analyze Request ──────────────────────────────────────

    async def analyze_request(
        self,
        classified_intent: Any,
        context: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[Any]] = None,
    ) -> IntelligenceDecision:
        """Analiza una petición y produce una decisión inteligente."""
        return self._orchestrator.orchestrate(
            classified_intent=classified_intent,
            context=context,
            available_tools=available_tools,
        )

    # ── 2. Select Model ─────────────────────────────────────────

    async def select_model(
        self, task_type: str, top_k: int = 3
    ) -> List[ModelScore]:
        """Retorna los mejores modelos rankeados para un tipo de tarea."""
        return self._ranking.get_top_k(k=top_k, task_type=task_type)

    # ── 3. Predict Execution ────────────────────────────────────

    async def predict_execution(
        self,
        model_id: str,
        task_type: str,
        complexity_hint: Optional[str] = None,
        estimated_tokens: Optional[int] = None,
    ) -> TimePrediction:
        """Estima el tiempo de ejecución y confianza."""
        return self._time_predictor.predict(
            model_id=model_id,
            task_type=task_type,
            complexity_hint=complexity_hint,
            estimated_tokens=estimated_tokens,
        )

    # ── 4. Calculate Cost ───────────────────────────────────────

    async def calculate_cost(
        self,
        provider_id: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> float:
        """Estima el costo de una ejecución."""
        if self._cost_tracker:
            return self._cost_tracker.estimate_cost(
                provider_id=provider_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        return 0.0

    async def record_cost(
        self,
        provider_id: str,
        model: str,
        task_type: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        session_id: Optional[str] = None,
        estimated: bool = True,
    ) -> Any:
        """Registra el costo de una ejecución."""
        if self._cost_tracker:
            return self._cost_tracker.record_cost(
                provider_id=provider_id,
                model=model,
                task_type=task_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                session_id=session_id,
                estimated=estimated,
            )
        return None

    # ── 5. Learn (post-execution) ───────────────────────────────

    async def learn(self, result: Any) -> None:
        """Post-execution learning: registra métricas y persiste."""
        if hasattr(result, "tool_result") and result.tool_result:
            tr = result.tool_result
            metric = ExecutionMetrics(
                model_id=getattr(tr, "model_id", "unknown"),
                task_type=getattr(result, "task_type", "unknown"),
                intent=getattr(result, "intent", "unknown"),
                latency=getattr(tr, "duration_ms", 0.0) / 1000.0,
                tokens_used=getattr(tr, "tokens_used", 0),
                cost=getattr(tr, "cost", 0.0),
                success=bool(getattr(tr, "success", False)),
                error=getattr(tr, "error", None),
            )
            self._performance.record_metric(metric)
            self._ranking.update_score(
                model_id=metric.model_id,
                latency=metric.latency,
                success=metric.success,
                task_type=metric.task_type,
            )
            await self._persist_metric(metric)

    async def learn_from_model_result(
        self,
        model_id: str,
        task_type: str,
        intent: str,
        latency_ms: float,
        tokens_used: int,
        cost: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Post-execution learning con parámetros explícitos."""
        metric = ExecutionMetrics(
            model_id=model_id,
            task_type=task_type,
            intent=intent,
            latency=latency_ms / 1000.0,
            tokens_used=tokens_used,
            cost=cost,
            success=success,
            error=error,
        )
        self._performance.record_metric(metric)
        self._ranking.update_score(
            model_id=model_id,
            latency=metric.latency,
            success=success,
            task_type=task_type,
        )
        await self._persist_metric(metric)
        await self._persist_performance_event(metric)

    # ── Execution History (FASE 5.4) ────────────────────────────

    async def record_execution(
        self,
        execution_id: str,
        user_request: str = "",
        intent: str = "",
        task_type: str = "",
        selected_model: str = "",
        tools_used: Optional[List[str]] = None,
        duration: float = 0.0,
        success: bool = True,
        failure_reason: Optional[str] = None,
        risk_level: str = "",
        cost: float = 0.0,
        confidence_score: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """Registra una ejecución en el historial persistente."""
        if self._execution_repo is None:
            return
        try:
            from sentinel.storage.models import StoredExecution

            await self._execution_repo.save(
                StoredExecution(
                    execution_id=execution_id,
                    user_request=user_request,
                    intent=intent,
                    task_type=task_type,
                    selected_model=selected_model,
                    tools_used=list(tools_used or []),
                    duration=duration,
                    success=success,
                    failure_reason=failure_reason,
                    risk_level=risk_level,
                    cost=cost,
                    confidence_score=confidence_score,
                    error=error,
                )
            )
        except Exception as e:
            logger.debug("Failed to persist execution: %s", e)

    # ── 6. Record Feedback ──────────────────────────────────────

    async def record_feedback(
        self,
        model_id: str,
        task_type: str,
        score: FeedbackScore,
        comment: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> None:
        """Registra feedback de usuario."""
        feedback = UserFeedback(
            model_id=model_id,
            task_type=task_type,
            score=score,
            comment=comment,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        self._feedback.record_feedback(feedback)
        await self._persist_feedback(feedback, execution_id=execution_id)

    # ── Consultas ───────────────────────────────────────────────

    def get_performance_summary(
        self, model_id: Optional[str] = None
    ) -> List[ModelPerformanceSummary]:
        return self._performance.get_summary(model_id=model_id)

    def get_model_summary(self, model_id: str) -> Optional[ModelPerformanceSummary]:
        return self._performance.get_model_summary(model_id)

    def get_feedback_summary(
        self, model_id: Optional[str] = None, task_type: Optional[str] = None
    ) -> List[FeedbackSummary]:
        return self._feedback.get_summary(model_id=model_id, task_type=task_type)

    def get_rankings(self, task_type: Optional[str] = None, top_k: int = 5) -> List[ModelScore]:
        return self._ranking.get_top_k(k=top_k, task_type=task_type)

    def get_model_score(self, model_id: str) -> Optional[ModelScore]:
        return self._ranking.get_model_score(model_id)

    def get_ranking(self) -> ModelRanking:
        return self._ranking

    # ── Capability Intelligence (FASE 4.3) ─────────────────────

    def recommend_model(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityRecommendation:
        """Recomienda el mejor modelo para una tarea según capacidades."""
        return self._capability_analyzer.analyze(task, context=context)

    async def recommend_model_async(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityRecommendation:
        return await self._capability_analyzer.analyze_async(task, context=context)

    def get_capability_analyzer(self) -> ModelCapabilityAnalyzer:
        return self._capability_analyzer

    # ── Multi-model coordination (FASE 4.5) ────────────────────

    def set_model_router(self, router: Any) -> None:
        self._model_router = router
        self._model_coordinator.set_model_router(router)

    def get_model_coordinator(self) -> ModelCoordinator:
        return self._model_coordinator

    def can_coordinate(self, classified_intent: Any) -> bool:
        return self._model_coordinator.can_coordinate(classified_intent)

    def decompose_task(
        self,
        user_message: str,
        classified_intent: Any = None,
        capabilities: Optional[List[str]] = None,
    ) -> MultiModelPlan:
        return self._model_coordinator.decompose(user_message, classified_intent, capabilities)

    async def execute_multi_model(
        self,
        user_message: str,
        classified_intent: Any = None,
        capabilities: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> MultiModelResult:
        """Divide y ejecuta una tarea compleja entre múltiples modelos."""
        plan = self._model_coordinator.decompose(user_message, classified_intent, capabilities)
        if not plan.tasks:
            return MultiModelResult(total_tasks=0, successful=0, failed=0)
        chat_fn = self._resolve_chat_fn()
        if chat_fn is None:
            logger.warning("No chat_fn available for multi-model execution")
            return MultiModelResult(total_tasks=len(plan.tasks), successful=0, failed=len(plan.tasks))
        return await self._model_coordinator.execute_plan(plan, user_message, chat_fn, context=context)

    def _resolve_chat_fn(self) -> Optional[Any]:
        if self._model_router is not None:
            return self._model_router.chat
        return None

    # ── Model Strategy (FASE 4.6) ──────────────────────────────

    def decide_strategy(
        self,
        task: str,
        intent: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelStrategy:
        """Decide la estrategia de modelos para una tarea."""
        return self._strategy_engine.decide(task, intent=intent, context=context)

    async def decide_strategy_async(
        self,
        task: str,
        intent: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelStrategy:
        return await self._strategy_engine.decide_async(task, intent=intent, context=context)

    def get_strategy_engine(self) -> ModelStrategyEngine:
        return self._strategy_engine

    # ── Failover / Reliability (FASE 4.7) ──────────────────────

    async def record_execution_result(
        self,
        provider_id: str,
        model_id: str,
        success: bool,
        latency_ms: float = 0.0,
        task_type: str = "chat",
        intent: str = "chat",
        tokens_used: int = 0,
        cost: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """Registra un resultado de ejecución: ranking + métricas del registro."""
        await self.learn_from_model_result(
            model_id=model_id,
            task_type=task_type,
            intent=intent,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            cost=cost,
            success=success,
            error=error,
        )
        self._update_registry_metrics(provider_id, model_id, success, latency_ms)

    async def apply_provider_failure(self, provider_id: str, model_id: Optional[str] = None) -> None:
        """Aplica penalización de fallo y degrada el estado del proveedor."""
        model_ids = self._registry_models_for_provider(provider_id) if model_id is None else [model_id]
        self._ranking.apply_provider_failure(provider_id, model_ids)
        for mid in model_ids:
            self._registry_degrade_model(mid)
        if self._registry is not None and model_id is None:
            for m in self._registry.find_by_provider(provider_id):
                self._registry_degrade_model(m.id)

    async def apply_provider_success(self, provider_id: str, model_id: Optional[str] = None) -> None:
        """Recupera el estado de un proveedor tras un éxito."""
        model_ids = self._registry_models_for_provider(provider_id) if model_id is None else [model_id]
        self._ranking.apply_provider_success(provider_id, model_ids)
        if self._registry is not None:
            for m in self._registry.find_by_provider(provider_id):
                try:
                    from sentinel.models import ModelStatus
                    self._registry.set_status(m.id, ModelStatus.AVAILABLE)
                except Exception:
                    pass

    def sync_circuit_breaker(self, cb: Any) -> None:
        """Sincroniza el CircuitBreaker con el ranking (failover real)."""
        self._ranking.apply_circuit_breaker(cb)

    def _update_registry_metrics(self, provider_id: str, model_id: str, success: bool, latency_ms: float) -> None:
        if self._registry is None:
            return
        try:
            model = self._registry.get(model_id)
            if model is None:
                return
            cfg = model.config
            usage = int(cfg.get("usage_count", 0)) + 1
            success_rate = float(cfg.get("success_rate", 1.0))
            success_rate = (success_rate * (usage - 1) + (1.0 if success else 0.0)) / usage
            self._registry.update_metrics(
                model_id=model_id,
                latency_avg=latency_ms / 1000.0,
                success_rate=round(success_rate, 3),
                usage_count=usage,
            )
        except Exception:
            pass

    def _registry_models_for_provider(self, provider_id: str) -> List[str]:
        if self._registry is None:
            return [provider_id]
        try:
            return [m.id for m in self._registry.find_by_provider(provider_id)]
        except Exception:
            return [provider_id]

    def _registry_degrade_model(self, model_id: str) -> None:
        if self._registry is None:
            return
        try:
            from sentinel.models import ModelStatus
            self._registry.update_metrics(model_id=model_id, success_rate=0.0)
        except Exception:
            pass

    # ── Discovery ───────────────────────────────────────────────

    async def discover_models(self) -> Dict[str, Any]:
        """Descubre modelos de todos los proveedores configurados."""
        self._discovery.add_default_discoverers()
        if self._model_repo is not None:
            try:
                await self._registry.load_from_repository(self._model_repo)
            except Exception:
                pass
        return await self._discovery.run_full_discovery_async()

    async def health_check_models(self) -> Dict[str, bool]:
        """Health check de todos los proveedores de descubrimiento."""
        return await self._discovery.health_check_all()

    def get_model_capabilities(self, model_id: str) -> Dict[str, Any]:
        """Capacidades declaradas de un modelo."""
        return self._discovery.get_capabilities(model_id)

    async def load_registry_from_repository(self) -> int:
        if self._registry is not None and self._model_repo is not None:
            return await self._registry.load_from_repository(self._model_repo)
        return 0

    async def persist_registry_to_repository(self) -> int:
        if self._registry is not None and self._model_repo is not None:
            return await self._registry.persist_to_repository(self._model_repo)
        return 0

    # ── Lifecycle ───────────────────────────────────────────────

    def subscribe_to_events(self) -> None:
        self._performance.subscribe_to_events()
        self._feedback.subscribe_to_events()

    def clear(self) -> None:
        self._performance.clear()
        self._feedback.clear()
        self._ranking.scores.clear()

    # ── Persistencia ────────────────────────────────────────────

    async def _persist_metric(self, metric: ExecutionMetrics) -> None:
        if self._metric_repo is None:
            return
        try:
            from sentinel.storage.models import MetricRecord

            record = MetricRecord(
                component="intelligence",
                metric_name=f"execution.{metric.model_id}.{metric.task_type}",
                value=metric.latency,
                unit="seconds",
                tags={
                    "model_id": metric.model_id,
                    "task_type": metric.task_type,
                    "success": str(metric.success),
                    "tokens_used": str(metric.tokens_used),
                    "cost": str(metric.cost),
                },
            )
            await self._metric_repo.save(record)
        except Exception as e:
            logger.debug("Failed to persist metric: %s", e)

    async def persist_observability_metrics(self, engine: Any) -> int:
        """Persist the ObservabilityEngine's registry snapshot into the official
        MetricRepository so telemetry survives restarts (FASE 7)."""
        if self._metric_repo is None:
            return 0
        try:
            records = engine.to_metric_records()
        except Exception as e:
            logger.debug("Observability records export failed: %s", e)
            return 0
        if not records:
            return 0
        try:
            await self._metric_repo.save_batch(records)
            return len(records)
        except Exception as e:
            logger.debug("Failed to persist observability metrics: %s", e)
            return 0

    async def _persist_performance_event(self, metric: ExecutionMetrics) -> None:
        if self._performance_repo is None:
            return
        try:
            from sentinel.storage.models import ModelPerformanceEvent

            await self._performance_repo.save(
                ModelPerformanceEvent(
                    model_name=metric.model_id,
                    task_type=metric.task_type,
                    latency=metric.latency,
                    success=metric.success,
                    quality_score=1.0 if metric.success else 0.0,
                    tokens_used=metric.tokens_used,
                    cost=metric.cost,
                )
            )
        except Exception as e:
            logger.debug("Failed to persist performance event: %s", e)

    async def _persist_feedback(self, feedback: UserFeedback, execution_id: Optional[str] = None) -> None:
        if self._feedback_repo is None:
            return
        try:
            from sentinel.storage.models import FeedbackRecord

            record = FeedbackRecord(
                model_id=feedback.model_id,
                task_type=feedback.task_type,
                success=feedback.score == FeedbackScore.POSITIVE,
                quality_score=1.0 if feedback.score == FeedbackScore.POSITIVE else (
                    0.0 if feedback.score == FeedbackScore.NEGATIVE else 0.5
                ),
                latency=0.0,
                error=feedback.comment,
                user_id=feedback.user_id or "",
                metadata={
                    "score": feedback.score.value,
                    "conversation_id": feedback.conversation_id or "",
                    "execution_id": execution_id or "",
                },
            )
            await self._feedback_repo.save(record)
        except Exception as e:
            logger.debug("Failed to persist feedback: %s", e)

    # ── Learning Recovery (FASE 5.8) ────────────────────────────

    async def recover_learning(self) -> Dict[str, Any]:
        """Rehidrata inteligencia desde la base de aprendizaje al arrancar."""
        recovered = {"metrics": 0, "feedback": 0, "preferences": 0}
        if self._performance_repo is not None:
            try:
                events = await self._performance_repo.list_all()
                for event in events:
                    self._performance.record_metric(
                        ExecutionMetrics(
                            model_id=event.model_name,
                            task_type=event.task_type,
                            intent="recovered",
                            latency=event.latency,
                            tokens_used=event.tokens_used,
                            cost=event.cost,
                            success=event.success,
                        )
                    )
                recovered["metrics"] = len(events)
            except Exception as e:
                logger.warning("Failed to recover performance metrics: %s", e)
        if self._feedback_repo is not None:
            try:
                records = await self._feedback_repo.list_all(limit=20000)
                for rec in records:
                    score = (
                        FeedbackScore.POSITIVE
                        if rec.success
                        else FeedbackScore.NEGATIVE
                    )
                    self._feedback.record_feedback(
                        UserFeedback(
                            model_id=rec.model_id,
                            task_type=rec.task_type,
                            score=score,
                            comment=rec.error,
                            user_id=rec.user_id or None,
                        )
                    )
                recovered["feedback"] = len(records)
            except Exception as e:
                logger.warning("Failed to recover feedback: %s", e)
        if self._preference_repo is not None:
            try:
                prefs = await self._preference_repo.list_all()
                self._restored_preferences = {
                    (p.user_id, p.key): p for p in prefs
                }
                recovered["preferences"] = len(prefs)
            except Exception as e:
                logger.warning("Failed to recover preferences: %s", e)
        try:
            self._ranking.compute_scores()
        except Exception as e:
            logger.warning("Failed to recompute rankings: %s", e)
        logger.info(
            "Learning recovery complete: %s", recovered
        )
        return recovered

    async def learning_memory_status(self) -> Dict[str, Any]:
        """Estado de la memoria de aprendizaje (health check, FASE 5.8)."""
        status: Dict[str, Any] = {
            "status": "active" if self._feedback_repo is not None else "disabled",
            "records": {},
            "last_update": None,
        }
        if self._performance is not None:
            status["records"]["metrics"] = self._performance.total_records
        if self._feedback is not None:
            status["records"]["feedback"] = self._feedback.total_feedback
        if self._registry is not None:
            try:
                status["records"]["models"] = self._registry.count()
            except Exception:
                pass
        try:
            if self._execution_repo is not None:
                status["records"]["executions"] = await self._execution_repo.count()
                last_exec = await self._execution_repo.get_last_update()
                if last_exec:
                    status["last_update"] = last_exec
            if self._performance_repo is not None:
                status["records"]["performance"] = await self._performance_repo.count()
            if self._preference_repo is not None:
                status["records"]["preferences"] = await self._preference_repo.count()
        except Exception as e:
            logger.warning("Learning memory status query failed: %s", e)
            status["status"] = "degraded"
        return status

    def get_user_preference(self, user_id: str, key: str) -> Any:
        """Lee una preferencia aprendida del usuario (en memoria)."""
        if hasattr(self, "_restored_preferences") and (user_id, key) in self._restored_preferences:
            return self._restored_preferences[(user_id, key)].value
        return None

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Todas las preferencias aprendidas de un usuario."""
        if not hasattr(self, "_restored_preferences"):
            return {}
        return {
            key: pref.value
            for (uid, key), pref in self._restored_preferences.items()
            if uid == user_id
        }

    async def set_user_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        source: str = "observed",
    ) -> None:
        """Guarda una preferencia aprendida del usuario (FASE 5.7)."""
        try:
            from datetime import datetime, timezone
            from sentinel.storage.models import UserPreference

            now = datetime.now(timezone.utc).isoformat()
            existing = self._restored_preferences.get((user_id, key))
            evidence = (existing.evidence_count + 1) if existing else 1
            confidence = 1.0 if source == "explicit" else min(0.95, (existing.confidence + 0.1) if existing else 0.5)
            created_at = existing.created_at if existing else now
            pref = UserPreference(
                user_id=user_id,
                key=key,
                value=value,
                source=source,
                evidence_count=evidence,
                confidence=confidence,
                created_at=created_at,
                updated_at=now,
            )
            self._restored_preferences[(user_id, key)] = pref
            if self._preference_repo is not None:
                await self._preference_repo.save(pref)
        except Exception as e:
            logger.warning("Failed to persist user preference: %s", e)
