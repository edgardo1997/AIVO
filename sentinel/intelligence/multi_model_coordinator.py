from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import asyncio
import logging
import time

from sentinel.intelligence.task_planner import TaskPlanner, TaskPlan, PlannedTask
from sentinel.intelligence.evaluation_engine import EvaluationEngine, ModelResponse, EvaluatedResponse
from sentinel.intelligence.confidence_scorer import ConfidenceScore
from sentinel.intelligence.consensus_engine import ConsensusEngine, ConsensusResult
from sentinel.intelligence.conflict_resolver import ConflictResolver, ConflictReport
from sentinel.intelligence.partial_failure_handler import PartialFailureHandler, PartialFailureReport

logger = logging.getLogger(__name__)


@dataclass
class MultiModelConfig:
    enabled: bool = True
    min_models: int = 2
    max_models: int = 3
    parallel_execution: bool = True
    consensus_required: bool = True
    fallback_on_failure: bool = True
    timeout_per_model_ms: float = 30000.0
    record_performance: bool = True


@dataclass
class MultiModelResult:
    final_answer: str = ""
    confidence: float = 0.0
    consensus: Optional[ConsensusResult] = None
    failure_report: Optional[PartialFailureReport] = None
    task_plan: Optional[TaskPlan] = None
    model_responses: List[ModelResponse] = field(default_factory=list)
    evaluations: List[EvaluatedResponse] = field(default_factory=list)
    duration_ms: float = 0.0
    config: Optional[MultiModelConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_answer": self.final_answer[:500],
            "confidence": self.confidence,
            "consensus": self.consensus.to_dict() if self.consensus else None,
            "failure_report": self.failure_report.to_dict() if self.failure_report else None,
            "task_plan": self.task_plan.to_dict() if self.task_plan else None,
            "model_responses": [r.to_dict() for r in self.model_responses],
            "evaluations": [e.to_dict() for e in self.evaluations],
            "duration_ms": self.duration_ms,
        }


DEFAULT_EXECUTE_FN = None


class MultiModelCoordinator:
    def __init__(
        self,
        task_planner: Optional[TaskPlanner] = None,
        evaluation_engine: Optional[EvaluationEngine] = None,
        consensus_engine: Optional[ConsensusEngine] = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        failure_handler: Optional[PartialFailureHandler] = None,
        config: Optional[MultiModelConfig] = None,
        model_router: Optional[Any] = None,
        model_registry: Optional[Any] = None,
        ranking_engine: Optional[Any] = None,
    ):
        self._planner = task_planner or TaskPlanner()
        self._conflict_resolver = conflict_resolver or ConflictResolver()
        self._evaluator = evaluation_engine or EvaluationEngine()
        self._consensus = consensus_engine or ConsensusEngine(self._evaluator, self._conflict_resolver)
        self._failure_handler = failure_handler or PartialFailureHandler(timeout_ms=(config or MultiModelConfig()).timeout_per_model_ms)
        self._config = config or MultiModelConfig()
        self._model_router = model_router
        self._model_registry = model_registry
        self._ranking_engine = ranking_engine

    async def process(self, user_message: str, execute_fn: Optional[Callable] = None, context: Optional[Dict[str, Any]] = None) -> MultiModelResult:
        if not self._config.enabled:
            return await self._fallback_single(user_message, execute_fn, context)
        start = time.monotonic()
        context = context or {}
        plan = self._planner.plan(user_message, context=context)
        if not plan.tasks:
            return await self._fallback_single(user_message, execute_fn, context)
        models = self._select_models_for_tasks(plan, context)
        if len(models) < self._config.min_models:
            logger.warning("Only %d model(s) available, need %d", len(models), self._config.min_models)
            return await self._fallback_single(user_message, execute_fn, context)
        try:
            result = await self._execute_with_models(user_message, plan, models, execute_fn, context)
            result.duration_ms = (time.monotonic() - start) * 1000
            result.config = self._config
            if self._config.record_performance:
                self._record_performance(result)
            return result
        except Exception as e:
            logger.error("Multi-model processing failed: %s", e)
            if self._config.fallback_on_failure:
                return await self._fallback_single(user_message, execute_fn, context)
            raise

    async def _fallback_single(self, user_message: str, execute_fn: Optional[Callable], context: Optional[Dict[str, Any]]) -> MultiModelResult:
        if execute_fn:
            result = execute_fn({"task_id": "fallback", "name": "analysis", "objective": user_message})
            if asyncio.iscoroutine(result):
                result = await result
            return MultiModelResult(final_answer=result.response_text if hasattr(result, 'response_text') else str(result), confidence=0.5, duration_ms=0.0, config=self._config)
        return MultiModelResult(final_answer="", confidence=0.0, duration_ms=0.0, config=self._config)

    def _select_models_for_tasks(self, plan: TaskPlan, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self._model_router and self._model_registry:
            return self._select_models_via_registry(plan, context)
        return self._select_models_default(plan)

    def _select_models_via_registry(self, plan: TaskPlan, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        models = []
        seen_ids = set()
        for task in plan.tasks:
            caps = task.required_capabilities
            candidates = self._model_registry.find_candidates(caps) if hasattr(self._model_registry, 'find_candidates') else []
            for c in candidates:
                if c.id not in seen_ids:
                    models.append({"model_id": c.id, "provider": c.provider, "task_ids": [task.task_id], "capabilities": caps})
                    seen_ids.add(c.id)
                    if len(models) >= self._config.max_models:
                        break
            if len(models) >= self._config.max_models:
                break
        if not models:
            models = self._select_models_default(plan)
        return models[:self._config.max_models]

    def _select_models_default(self, plan: TaskPlan) -> List[Dict[str, Any]]:
        return [
            {"model_id": f"model_{i+1}", "provider": "default", "task_ids": [t.task_id for t in plan.tasks], "capabilities": ["reasoning"]}
            for i in range(min(self._config.max_models, max(self._config.min_models, len(plan.tasks))))
        ]

    async def _execute_with_models(self, user_message: str, plan: TaskPlan, models: List[Dict[str, Any]], execute_fn: Optional[Callable], context: Optional[Dict[str, Any]]) -> MultiModelResult:
        if not execute_fn:
            return MultiModelResult(final_answer="", confidence=0.0, config=self._config)
        task_list = [{"model_id": m["model_id"], "provider": m["provider"], "task_id": m["task_ids"][0] if m["task_ids"] else "unknown", "name": "analysis", "objective": user_message, "model": m} for m in models]
        exec_result = await self._failure_handler.execute_with_partial_handling(task_list, execute_fn)
        responses: List[ModelResponse] = exec_result["results"]
        report: PartialFailureReport = exec_result["report"]
        if not responses:
            raise RuntimeError("All models failed")
        evaluations = self._evaluator.evaluate_batch(responses, instruction=user_message)
        consensus = self._consensus.build_consensus(evaluations, instruction=user_message)
        return MultiModelResult(
            final_answer=consensus.final_answer,
            confidence=consensus.confidence,
            consensus=consensus,
            failure_report=report,
            task_plan=plan,
            model_responses=responses,
            evaluations=evaluations,
            config=self._config,
        )

    def _record_performance(self, result: MultiModelResult) -> None:
        if not self._ranking_engine:
            return
        for ev in result.evaluations:
            try:
                self._ranking_engine.update_score(
                    model_id=ev.response.model_id,
                    latency=ev.response.duration_ms,
                    success=ev.response.success,
                    task_type="multi_model",
                )
            except Exception as e:
                logger.debug("Failed to record performance for %s: %s", ev.response.model_id, e)
