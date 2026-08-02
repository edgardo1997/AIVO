from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_registry import ModelRegistry
from sentinel.core.capability_engine import CapabilityEngine, CapabilitySet, IntentType
from sentinel.core.intent_engine_v2 import ClassifiedIntent, IntentCategory

from sentinel.core.resource_intelligence import ResourceIntelligenceLayer, ResourceDecision

import logging

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    CHAT_ONLY = "chat_only"
    TOOL_EXECUTION = "tool_execution"
    REASONING = "reasoning"
    CODING = "coding"
    MULTI_STEP = "multi_step"


INTENT_STRATEGY_MAP: Dict[IntentCategory, ExecutionStrategy] = {
    IntentCategory.CHAT: ExecutionStrategy.CHAT_ONLY,
    IntentCategory.ACTION: ExecutionStrategy.TOOL_EXECUTION,
    IntentCategory.SYSTEM_OPERATION: ExecutionStrategy.TOOL_EXECUTION,
    IntentCategory.AUTOMATION: ExecutionStrategy.TOOL_EXECUTION,
    IntentCategory.CODING: ExecutionStrategy.CODING,
    IntentCategory.SEARCH: ExecutionStrategy.CHAT_ONLY,
    IntentCategory.DOCUMENT: ExecutionStrategy.CHAT_ONLY,
    IntentCategory.MEMORY: ExecutionStrategy.CHAT_ONLY,
    IntentCategory.REASONING: ExecutionStrategy.REASONING,
    IntentCategory.UNKNOWN: ExecutionStrategy.CHAT_ONLY,
}


@dataclass
class IntelligenceDecision:
    model_id: str = ""
    provider: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    selected_tools: List[str] = field(default_factory=list)
    execution_strategy: ExecutionStrategy = ExecutionStrategy.CHAT_ONLY
    confidence: float = 0.0
    reasoning: str = ""
    status: str = "success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "required_capabilities": list(self.required_capabilities),
            "selected_tools": list(self.selected_tools),
            "execution_strategy": self.execution_strategy.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "status": self.status,
        }


class IntelligenceOrchestrator:
    def __init__(
        self,
        model_registry: Optional[ModelRegistry] = None,
        capability_engine: Optional[CapabilityEngine] = None,
    ):
        self._model_registry = model_registry
        self._capability_engine = capability_engine
        self._resource_intelligence: Optional[ResourceIntelligenceLayer] = None
        self._performance_intelligence: Any = None
        self._model_ranking: Any = None
        self._time_predictor: Any = None
        self._audit_log: List[Dict[str, Any]] = []

    def set_model_registry(self, registry: ModelRegistry) -> None:
        self._model_registry = registry

    def set_capability_engine(self, engine: CapabilityEngine) -> None:
        self._capability_engine = engine

    def set_resource_intelligence(self, ri: ResourceIntelligenceLayer) -> None:
        self._resource_intelligence = ri

    def set_performance_intelligence(self, pi: Any) -> None:
        self._performance_intelligence = pi

    def set_model_ranking(self, mr: Any) -> None:
        self._model_ranking = mr

    def set_time_predictor(self, tp: Any) -> None:
        self._time_predictor = tp

    @property
    def audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def orchestrate(
        self,
        classified_intent: ClassifiedIntent,
        context: Optional[Dict[str, Any]] = None,
        available_tools: Optional[List[Any]] = None,
    ) -> IntelligenceDecision:
        context = context or {}

        capabilities = self._resolve_capabilities(classified_intent)
        strategy = self._select_strategy(classified_intent.category)

        if not self._model_registry:
            return IntelligenceDecision(
                execution_strategy=strategy,
                required_capabilities=capabilities.to_list(),
                confidence=classified_intent.confidence,
                reasoning="No ModelRegistry configured: returning strategy only",
                status="no_registry",
            )

        candidate, resource_decision = self._select_model(capabilities, classified_intent, context)
        if candidate is None:
            reason = "No available model supports required capabilities"
            if self._resource_intelligence is not None:
                reason += " (all candidates rejected by resource constraints)"
            return IntelligenceDecision(
                execution_strategy=strategy,
                required_capabilities=capabilities.to_list(),
                confidence=classified_intent.confidence,
                reasoning=reason,
                status="no_capable_model",
            )

        tools = self._select_tools(strategy, available_tools, candidate)
        reasoning = self._build_reasoning(candidate, classified_intent, capabilities, strategy, context, resource_decision)

        return IntelligenceDecision(
            model_id=candidate.id,
            provider=candidate.provider,
            required_capabilities=capabilities.to_list(),
            selected_tools=tools,
            execution_strategy=strategy,
            confidence=min(classified_intent.confidence, 0.95),
            reasoning=reasoning,
            status="success",
        )

    def _resolve_capabilities(self, intent: ClassifiedIntent) -> CapabilitySet:
        if self._capability_engine:
            to_type = {
                IntentCategory.CHAT: IntentType.CHAT,
                IntentCategory.ACTION: IntentType.ACTION,
                IntentCategory.CODING: IntentType.CODING,
                IntentCategory.SEARCH: IntentType.SEARCH,
                IntentCategory.DOCUMENT: IntentType.DOCUMENT,
                IntentCategory.SYSTEM_OPERATION: IntentType.ACTION,
                IntentCategory.AUTOMATION: IntentType.ACTION,
                IntentCategory.MEMORY: IntentType.CHAT,
                IntentCategory.REASONING: IntentType.CODING,
                IntentCategory.UNKNOWN: IntentType.UNKNOWN,
            }
            intent_type = to_type.get(intent.category, IntentType.UNKNOWN)
            return self._capability_engine.resolve(intent_type)
        return intent.to_capability_set()

    def _select_strategy(self, category: IntentCategory) -> ExecutionStrategy:
        return INTENT_STRATEGY_MAP.get(category, ExecutionStrategy.CHAT_ONLY)

    def _score_model(
        self, model: ModelMetadata, capabilities: CapabilitySet,
        resource_decision: Optional[ResourceDecision] = None,
    ) -> int:
        score = 0
        for cap in capabilities:
            if model.has_capability(cap):
                score += 50
        if capabilities.has("tool_calling") and model.supports_tool_calling:
            score += 30
        if model.local:
            score += 10
        if model.cost == 0:
            score += 10
        elif model.cost <= 1:
            score += 5
        if model.speed == "fast":
            score += 5
        elif model.speed == "slow":
            score -= 10
        if resource_decision is not None:
            score += resource_decision.score_modifier

        if self._model_ranking is not None:
            model_score = self._model_ranking.get_model_score(model.id)
            if model_score is not None:
                perf_bonus = int(model_score.performance_score / 10)
                score += perf_bonus
                if model_score.reliability_score < 50:
                    score -= 20

        if self._performance_intelligence is not None:
            success_rate = self._performance_intelligence.get_success_rate(model.id)
            if success_rate > 0:
                if success_rate < 0.5:
                    score -= 30
                elif success_rate < 0.7:
                    score -= 10

        return score

    def _select_model(
        self,
        capabilities: CapabilitySet,
        intent: ClassifiedIntent,
        context: Dict[str, Any],
    ) -> Tuple[Optional[ModelMetadata], Optional[ResourceDecision]]:
        candidates = self._model_registry.find_candidates(capabilities.to_list())
        if not candidates:
            logger.warning(
                "No model candidates for capabilities %s (intent=%s)",
                capabilities.to_list(), intent.category.value,
            )
            return None, None

        candidate_decisions: List[Tuple[Any, Optional[ResourceDecision]]] = [(m, None) for m in candidates]

        if self._resource_intelligence is not None:
            try:
                filtered = []
                for m, d in candidate_decisions:
                    rd = self._resource_intelligence.evaluate(m)
                    if rd.allowed:
                        filtered.append((m, rd))
                    else:
                        logger.info("Model %s rejected by resource intelligence: %s", m.id, rd.reason)
                if not filtered:
                    logger.warning(
                        "All %d candidates rejected by resource intelligence for caps %s",
                        len(candidates), capabilities.to_list(),
                    )
                    return None, None
                candidate_decisions = filtered
            except Exception as e:
                logger.warning("Resource intelligence evaluation failed: %s", e)

        best_model: Optional[ModelMetadata] = None
        best_decision: Optional[ResourceDecision] = None
        best_score = -999999

        for m, rd in candidate_decisions:
            s = self._score_model(m, capabilities, rd)
            if s > best_score or (s == best_score and (best_model is None or m.cost < best_model.cost)):
                best_score = s
                best_model = m
                best_decision = rd

        if best_model is not None:
            logger.info(
                "Model selection: %s score=%d for caps=%s",
                best_model.id, best_score, capabilities.to_list(),
            )
            self._audit_log.append({
                "action": "model_selected",
                "model_id": best_model.id,
                "score": best_score,
                "capabilities": capabilities.to_list(),
                "intent": intent.category.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return best_model, best_decision

    def _select_tools(
        self,
        strategy: ExecutionStrategy,
        available_tools: Optional[List[Any]],
        model: ModelMetadata,
    ) -> List[str]:
        if strategy != ExecutionStrategy.TOOL_EXECUTION:
            return []
        if not model.supports_tool_calling:
            return []
        if not available_tools:
            return []
        return [t.id if hasattr(t, "id") else (t.get("id") if isinstance(t, dict) else str(t)) for t in available_tools[:20]]

    def _build_reasoning(
        self,
        model: ModelMetadata,
        intent: ClassifiedIntent,
        capabilities: CapabilitySet,
        strategy: ExecutionStrategy,
        context: Dict[str, Any],
        resource_decision: Optional[ResourceDecision] = None,
    ) -> str:
        parts = [
            f"Intent: {intent.category.value}",
            f"Model: {model.id} (provider={model.provider})",
            f"Capabilities: {capabilities.to_list()}",
            f"Strategy: {strategy.value}",
        ]
        if model.supports_tool_calling:
            parts.append("Tool calling: enabled")
        if context.get("previous_intent"):
            parts.append("Context: previous intent used")
        if resource_decision is not None and resource_decision.reason and resource_decision.reason != "compatible":
            parts.append(f"Resource: {resource_decision.reason}")
        elif resource_decision is not None and resource_decision.score_modifier != 0:
            parts.append(f"Resource: score modifier {resource_decision.score_modifier:+d}")

        if self._model_ranking is not None:
            ms = self._model_ranking.get_model_score(model.id)
            if ms is not None:
                if ms.performance_score >= 80:
                    parts.append(f"Performance: {ms.performance_score}/100 (high)")
                elif ms.performance_score >= 50:
                    parts.append(f"Performance: {ms.performance_score}/100 (medium)")
                else:
                    parts.append(f"Performance: {ms.performance_score}/100 (low)")
                if ms.reliability_score >= 90:
                    parts.append(f"Reliability: {ms.reliability_score}% (high)")
                else:
                    parts.append(f"Reliability: {ms.reliability_score}%")
                if ms.total_executions > 0:
                    parts.append(f"Historical data: {ms.total_executions} executions")

        if self._performance_intelligence is not None:
            success_rate = self._performance_intelligence.get_success_rate(model.id)
            avg_latency = self._performance_intelligence.get_avg_latency(model.id)
            if success_rate > 0:
                parts.append(f"Success rate: {success_rate*100:.0f}%")
            if avg_latency > 0:
                parts.append(f"Avg latency: {avg_latency:.1f}s")

        if model.cost == 0:
            parts.append("Cost: free")
        elif model.cost > 0:
            parts.append(f"Cost: ${model.cost}/1K tokens")

        if self._time_predictor is not None:
            try:
                prediction = self._time_predictor.predict(
                    model.id, intent.category.value,
                    complexity_hint=context.get("complexity"),
                )
                parts.append(f"Estimated time: {prediction.estimated_display} (confidence: {prediction.confidence:.0%})")
            except Exception:
                logger.warning("Time prediction unavailable for model '%s'", model.id, exc_info=True)

        return " | ".join(parts)
