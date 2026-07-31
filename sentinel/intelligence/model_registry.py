"""ModelRegistry — Mantiene el catálogo de modelos disponibles.

Responsabilidades:
  - Almacenar modelos descubiertos manual y automáticamente
  - Responder available_models() y best_model_for(task, criteria)
  - Integrar con ModelDiscovery, ModelRanking, IntelligenceEngine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sentinel.intelligence.model_discovery import ModelCapability

logger = logging.getLogger(__name__)


@dataclass
class RegistryEntry:
    model: ModelCapability
    enabled: bool = True
    manual: bool = False
    tags: Set[str] = field(default_factory=set)
    priority: int = 0


class ModelRegistry:
    """Catálogo central de modelos disponibles.

    Mantiene tanto modelos descubiertos automáticamente como
    modelos registrados manualmente.
    """

    def __init__(self):
        self._entries: Dict[str, RegistryEntry] = {}

    # ── Registration ──────────────────────────────────────────

    def register(self, model: ModelCapability, manual: bool = False, tags: Optional[List[str]] = None) -> None:
        key = f"{model.provider}/{model.name}"
        self._entries[key] = RegistryEntry(
            model=model,
            manual=manual,
            tags=set(tags or []),
        )
        logger.info("Registry: registered %s (%s)", key, "manual" if manual else "auto")

    def register_batch(self, models: List[ModelCapability], manual: bool = False) -> None:
        for m in models:
            self.register(m, manual=manual)

    def remove(self, model_name: str, provider: str) -> bool:
        key = f"{provider}/{model_name}"
        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def enable(self, model_name: str, provider: str) -> bool:
        entry = self._get_entry(model_name, provider)
        if entry:
            entry.enabled = True
            return True
        return False

    def disable(self, model_name: str, provider: str) -> bool:
        entry = self._get_entry(model_name, provider)
        if entry:
            entry.enabled = False
            return True
        return False

    # ── Queries ───────────────────────────────────────────────

    def available_models(self, include_disabled: bool = False) -> List[ModelCapability]:
        """Retorna todos los modelos disponibles."""
        models = []
        for entry in self._entries.values():
            if include_disabled or entry.enabled:
                models.append(entry.model)
        return models

    def best_model_for(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
        prefer_local: bool = False,
        max_cost: Optional[float] = None,
    ) -> Optional[ModelCapability]:
        """Selecciona el mejor modelo para una tarea según criterios."""
        candidates = self._filter_candidates(required_capabilities, prefer_local, max_cost)
        if not candidates:
            return None
        candidates.sort(key=lambda x: self._score_model_for_task(x, task_type), reverse=True)
        return candidates[0]

    def get_model(self, model_name: str, provider: str) -> Optional[ModelCapability]:
        entry = self._get_entry(model_name, provider)
        return entry.model if entry else None

    def get_by_provider(self, provider: str) -> List[ModelCapability]:
        prefix = f"{provider}/"
        return [
            entry.model for key, entry in self._entries.items()
            if key.startswith(prefix) and entry.enabled
        ]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    # ── Internal ──────────────────────────────────────────────

    def _get_entry(self, model_name: str, provider: str) -> Optional[RegistryEntry]:
        key = f"{provider}/{model_name}"
        return self._entries.get(key)

    def _filter_candidates(
        self,
        required_capabilities: Optional[List[str]],
        prefer_local: bool,
        max_cost: Optional[float],
    ) -> List[ModelCapability]:
        candidates = []
        for entry in self._entries.values():
            if not entry.enabled:
                continue
            m = entry.model
            if required_capabilities:
                if not all(c in m.capabilities for c in required_capabilities):
                    continue
            if max_cost is not None and m.cost > max_cost:
                continue
            if prefer_local and not m.local:
                continue
            candidates.append(m)
        return candidates

    def _score_model_for_task(self, model: ModelCapability, task_type: str) -> float:
        """Puntúa un modelo para una tarea específica (0-100)."""
        score = 50.0
        task_caps = {
            "coding": ["coding", "reasoning"],
            "chat": ["chat", "conversation"],
            "reasoning": ["reasoning", "analysis"],
            "tool": ["tool_calling"],
            "search": ["internet", "grounding"],
            "vision": ["vision"],
            "embedding": ["embedding"],
        }
        needed = task_caps.get(task_type, [])
        if needed:
            matches = sum(1 for c in needed if c in model.capabilities)
            score += (matches / len(needed)) * 30
        if model.local:
            score += 10
        if model.cost == 0:
            score += 5
        elif model.cost < 1:
            score += 3
        return score
