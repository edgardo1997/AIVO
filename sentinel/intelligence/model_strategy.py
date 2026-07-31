"""ModelStrategyEngine — Estrategia de modelos (FASE 4.6).

Decide si una tarea requiere:
  - Single model  (tarea simple)
  - Multiple models (tarea compleja → coordinación)
  - Local model   (privacidad / sin red)
  - Cloud model   (tarea de alto rendimiento)
  - Hybrid        (combinación local + cloud)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    SINGLE = "single"
    MULTI = "multi"
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


@dataclass
class ModelStrategy:
    strategy: StrategyType = StrategyType.SINGLE
    task: str = ""
    task_type: str = "CHAT"
    complexity: str = "simple"
    privacy_sensitive: bool = False
    offline: bool = False
    reason: str = ""
    recommended_models: List[str] = field(default_factory=list)
    coordination_plan: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "task": self.task,
            "task_type": self.task_type,
            "complexity": self.complexity,
            "privacy_sensitive": self.privacy_sensitive,
            "offline": self.offline,
            "reason": self.reason,
            "recommended_models": list(self.recommended_models),
            "coordination_plan": self.coordination_plan.to_dict() if self.coordination_plan is not None else None,
        }


SIMPLE_ACTIONS = {
    "open",
    "abre",
    "launch",
    "close",
    "stop",
    "play",
    "pause",
    "run",
    "ejecuta",
    "delete",
    "create",
}

COMPLEX_KEYWORDS = {
    "project",
    "aplicación",
    "audit",
    "audita",
    "completo",
    "entire",
    "arquitectura",
    "architecture",
    "revisa",
    "review",
    "analiza",
    "analyze",
    "diseña",
    "design",
    "refactor",
    "seguridad",
    "security",
    "planifica",
    "plan",
    "investiga",
    "research",
}

PRIVACY_KEYWORDS = {
    "privado",
    "privada",
    "private",
    "confidencial",
    "confidential",
    "secret",
    "secreto",
    "password",
    "contraseña",
    "mis documentos",
    "my documents",
    "personal",
    "sensitive",
    "sensibles",
}


class ModelStrategyEngine:
    """Decide la estrategia de modelos para una tarea."""

    def __init__(
        self,
        registry: Any = None,
        capability_analyzer: Any = None,
        coordinator: Any = None,
        ranking: Any = None,
    ):
        self._registry = registry
        self._capability_analyzer = capability_analyzer
        self._coordinator = coordinator
        self._ranking = ranking

    def set_registry(self, registry: Any) -> None:
        self._registry = registry

    def set_capability_analyzer(self, analyzer: Any) -> None:
        self._capability_analyzer = analyzer

    def set_coordinator(self, coordinator: Any) -> None:
        self._coordinator = coordinator

    def set_ranking(self, ranking: Any) -> None:
        self._ranking = ranking

    # ── API pública ────────────────────────────────────────────

    def decide(
        self,
        task: str,
        intent: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelStrategy:
        """Decide la estrategia de modelos óptima."""
        context = context or {}
        task_lower = task.lower()
        words = len(task.split())

        complexity = self._classify_complexity(task_lower, words, intent)
        privacy = self._is_privacy_sensitive(task_lower, context)
        offline = bool(context.get("offline")) or self._is_offline(context)

        strategy = self._choose_strategy(task_lower, complexity, privacy, offline, intent)
        recommended = self._recommend_models(strategy, task)

        plan = None
        if strategy == StrategyType.MULTI and self._coordinator is not None:
            try:
                capabilities = self._resolve_capabilities(task)
                plan = self._coordinator.decompose_task(task, intent, capabilities)
                if plan and plan.tasks:
                    recommended = [t.preferred_model or t.name for t in plan.tasks[:3] if t.preferred_model]
            except Exception as e:
                logger.debug("Coordination plan failed: %s", e)

        reason = self._build_reason(strategy, complexity, privacy, offline, task_lower)

        return ModelStrategy(
            strategy=strategy,
            task=task,
            task_type=self._intent_str(intent),
            complexity=complexity,
            privacy_sensitive=privacy,
            offline=offline,
            reason=reason,
            recommended_models=recommended,
            coordination_plan=plan,
        )

    async def decide_async(
        self,
        task: str,
        intent: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelStrategy:
        return self.decide(task, intent=intent, context=context)

    # ── Interno ────────────────────────────────────────────────

    def _classify_complexity(self, task_lower: str, words: int, intent: Any) -> str:
        intent_str = self._intent_str(intent)
        if words >= 25 or any(k in task_lower for k in COMPLEX_KEYWORDS):
            return "complex"
        if words <= 4 and any(action in task_lower for action in SIMPLE_ACTIONS):
            return "simple"
        if intent_str in ("ACTION",):
            return "simple"
        if words <= 8:
            return "simple"
        return "medium"

    def _is_privacy_sensitive(self, task_lower: str, context: Dict[str, Any]) -> bool:
        if any(k in task_lower for k in PRIVACY_KEYWORDS):
            return True
        perm_level = context.get("permission_level", "")
        if perm_level in ("high", "emergency"):
            return True
        return bool(context.get("privacy_sensitive"))

    @staticmethod
    def _is_offline(context: Dict[str, Any]) -> bool:
        if context.get("offline"):
            return True
        offline_mode = context.get("offline_mode")
        if offline_mode == "force_local":
            return True
        return False

    def _choose_strategy(
        self,
        task_lower: str,
        complexity: str,
        privacy: bool,
        offline: bool,
        intent: Any,
    ) -> StrategyType:
        if privacy or offline:
            return StrategyType.LOCAL
        if complexity == "complex":
            return StrategyType.MULTI
        if complexity == "medium":
            return StrategyType.HYBRID
        intent_str = self._intent_str(intent)
        if intent_str in ("CODING", "REASONING", "ANALYSIS"):
            return StrategyType.CLOUD
        return StrategyType.SINGLE

    def _recommend_models(self, strategy: StrategyType, task: str) -> List[str]:
        if self._capability_analyzer is not None:
            try:
                rec = self._capability_analyzer.analyze(task)
                if rec.recommended_model:
                    models = [rec.recommended_model] + rec.alternative_models
                    if strategy == StrategyType.LOCAL:
                        return [rec.local_fallback] if rec.local_fallback else models[:1]
                    if strategy in (StrategyType.MULTI, StrategyType.HYBRID):
                        return models[:2]
                    return models[:1]
            except Exception as e:
                logger.debug("Recommendation failed: %s", e)
        if self._registry is not None:
            try:
                candidates = self._registry.list_available()
                if strategy == StrategyType.LOCAL:
                    local = [m.id for m in candidates if m.local]
                    if local:
                        return local[:1]
                return [m.id for m in candidates[:1]]
            except Exception:
                pass
        return []

    def _resolve_capabilities(self, task: str) -> List[str]:
        if self._capability_analyzer is not None:
            try:
                return self._capability_analyzer.resolve_capabilities(task)
            except Exception:
                pass
        return ["reasoning"]

    def _intent_str(self, intent: Any) -> str:
        if intent is None:
            return "CHAT"
        cat = getattr(intent, "category", None)
        if cat is None:
            return getattr(intent, "value", str(intent))
        return cat.value if hasattr(cat, "value") else str(cat)

    @staticmethod
    def _build_reason(
        strategy: StrategyType,
        complexity: str,
        privacy: bool,
        offline: bool,
        task_lower: str,
    ) -> str:
        if privacy:
            return "Privacy-sensitive task → local model only"
        if offline:
            return "Offline/restricted environment → local model only"
        if complexity == "complex":
            return "Complex task detected → multi-model workflow"
        if complexity == "medium":
            return "Medium complexity → hybrid local + cloud"
        if strategy == StrategyType.CLOUD:
            return "High-capability task → cloud model"
        return "Simple task → single execution model"
