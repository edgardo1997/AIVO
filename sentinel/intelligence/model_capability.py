"""ModelCapabilityAnalyzer — Capability Intelligence.

Entiende qué modelo sirve para qué tarea. Traduce una tarea en
capacidades requeridas y consulta el ModelRegistry para producir
una recomendación con alternativa y fallback local.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Keywords de tarea → capacidades requeridas (además del intent engine).
TASK_KEYWORD_CAPABILITIES: Dict[str, List[str]] = {
    "security": ["reasoning", "coding"],
    "vulnerab": ["reasoning", "coding"],
    "sql": ["reasoning", "coding"],
    "exploit": ["reasoning", "coding"],
    "audit": ["reasoning"],
    "review": ["reasoning"],
    "refactor": ["coding"],
    "refactoring": ["coding"],
    "debug": ["coding", "reasoning"],
    "bug": ["coding", "reasoning"],
    "optimiz": ["coding", "reasoning"],
    "performance": ["reasoning"],
    "architect": ["reasoning"],
    "test": ["coding"],
    "write code": ["coding"],
    "implement": ["coding"],
    "analy": ["reasoning"],
    "summari": ["reasoning"],
    "translat": ["conversation"],
    "extract": ["vision", "reasoning"],
    "ocr": ["vision"],
    "image": ["vision"],
    "diagram": ["vision", "reasoning"],
    "plan": ["reasoning"],
    "search": ["internet", "grounding"],
    "research": ["internet", "reasoning"],
}

# Capacidades entendidas por ModelMetadata.has_capability.
KNOWN_CAPABILITIES = {
    "coding",
    "reasoning",
    "tool_calling",
    "vision",
    "embeddings",
    "local",
}


@dataclass
class CapabilityRecommendation:
    task: str = ""
    intent: str = "CHAT"
    required_capabilities: List[str] = field(default_factory=list)
    recommended_model: str = ""
    recommended_provider: str = ""
    alternative_models: List[str] = field(default_factory=list)
    local_fallback: str = ""
    reason: str = ""
    matched_candidates: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "intent": self.intent,
            "required_capabilities": list(self.required_capabilities),
            "recommended_model": self.recommended_model,
            "recommended_provider": self.recommended_provider,
            "alternative_models": list(self.alternative_models),
            "local_fallback": self.local_fallback,
            "reason": self.reason,
            "matched_candidates": list(self.matched_candidates),
        }


class ModelCapabilityAnalyzer:
    """Analiza tareas y recomienda modelos según capacidades reales."""

    def __init__(
        self,
        registry: Any = None,
        capability_engine: Any = None,
        ranking: Any = None,
    ):
        self._registry = registry
        self._capability_engine = capability_engine
        self._ranking = ranking

    def set_registry(self, registry: Any) -> None:
        self._registry = registry

    def set_capability_engine(self, engine: Any) -> None:
        self._capability_engine = engine

    def set_ranking(self, ranking: Any) -> None:
        self._ranking = ranking

    # ── API pública ────────────────────────────────────────────

    def analyze(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityRecommendation:
        """Recomienda un modelo para una tarea (síncrono)."""
        intent, required = self._resolve_capabilities(task)
        candidates = self._find_candidates(required, context)
        return self._build_recommendation(task, intent, required, candidates)

    async def analyze_async(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityRecommendation:
        """Recomienda un modelo para una tarea (async)."""
        return self.analyze(task, context=context)

    def resolve_capabilities(self, task: str) -> List[str]:
        _, required = self._resolve_capabilities(task)
        return required

    # ── Interno ────────────────────────────────────────────────

    def _resolve_capabilities(self, task: str) -> tuple:
        task_lower = task.lower()
        cap_set = set()

        if self._capability_engine is not None:
            try:
                cap_set.update(self._capability_engine.resolve(task).to_list())
            except Exception as e:
                logger.debug("CapabilityEngine resolve failed: %s", e)

        for keyword, caps in TASK_KEYWORD_CAPABILITIES.items():
            if keyword in task_lower:
                cap_set.update(caps)

        cap_set = {c for c in cap_set if c in KNOWN_CAPABILITIES or c in ("local",)}
        if not cap_set:
            cap_set.add("reasoning")

        return "CODING" if "coding" in cap_set else "CHAT", sorted(cap_set)

    def _find_candidates(
        self,
        required: List[str],
        context: Optional[Dict[str, Any]],
    ) -> List[Any]:
        if self._registry is None:
            return []
        try:
            candidates = self._registry.find_candidates(required)
        except Exception as e:
            logger.debug("find_candidates failed: %s", e)
            return []
        if not candidates:
            try:
                candidates = self._registry.list_available()
            except Exception:
                candidates = []
        return candidates

    def _build_recommendation(
        self,
        task: str,
        intent: str,
        required: List[str],
        candidates: List[Any],
    ) -> CapabilityRecommendation:
        if not candidates:
            return CapabilityRecommendation(
                task=task,
                intent=intent,
                required_capabilities=required,
                reason="no_candidates",
            )

        ranked = self._order_candidates(candidates, required)

        best = ranked[0]
        alternatives = [m.id for m in ranked[1:]]
        local = next((m for m in ranked if m.local), None)

        reason = (
            f"{best.id} matches required capabilities {required}"
            if required
            else f"{best.id} available with declared capabilities"
        )

        return CapabilityRecommendation(
            task=task,
            intent=intent,
            required_capabilities=required,
            recommended_model=best.id,
            recommended_provider=best.provider,
            alternative_models=alternatives,
            local_fallback=local.id if local else "",
            reason=reason,
            matched_candidates=[m.id for m in ranked],
        )

    def _order_candidates(self, candidates: List[Any], required: List[str]) -> List[Any]:
        if self._ranking is not None:
            try:
                scores = {s.model_id: s for s in self._ranking.get_top_k(k=50)}
                ordered = sorted(
                    candidates,
                    key=lambda m: scores.get(m.id, None).performance_score if m.id in scores else -1.0,
                    reverse=True,
                )
                if any(m.id in scores for m in candidates):
                    return ordered
            except Exception as e:
                logger.debug("Ranking order failed: %s", e)
        return candidates
