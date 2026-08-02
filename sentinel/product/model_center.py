"""User-facing model ecosystem for Sentinel Desktop.

Exposes the multi-model ecosystem the way a user sees it: a set of *cards*
with status, cost, speed and capability, plus the ability to mark a
favourite and to state what matters most (speed, quality, privacy, cost).
Favourites and priorities are persisted through the injected storage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sentinel.models import ModelMetadata, ModelStatus

log = logging.getLogger(__name__)

PRIORITIES = ("balanced", "speed", "quality", "privacy", "cost")

_SPEED_LABEL = {
    "very_fast": "Muy alta",
    "fast": "Alta",
    "medium": "Media",
    "slow": "Lenta",
    "unknown": "Desconocida",
}

_CAPABILITY_LABEL = {
    "tool_calling": "Herramientas",
    "vision": "Visión",
    "coding": "Código",
    "reasoning": "Razonamiento",
    "embeddings": "Embeddings",
    "local": "Local",
}


def _capabilities(model: ModelMetadata) -> List[str]:
    caps = []
    if model.supports_tool_calling:
        caps.append("tool_calling")
    if model.supports_vision:
        caps.append("vision")
    if model.supports_coding:
        caps.append("coding")
    if model.supports_reasoning:
        caps.append("reasoning")
    if model.supports_embeddings:
        caps.append("embeddings")
    if model.local:
        caps.append("local")
    return caps


class ModelCenterService:
    def __init__(self, storage: Optional[Any] = None, registry: Optional[Any] = None) -> None:
        self._storage = storage
        self._registry = registry
        self._favorites: List[str] = []
        self._priority = "balanced"
        self._restore()

    # --- persistence ---

    def _restore(self) -> None:
        if self._storage is None:
            return
        try:
            state = self._storage.config_get_json("product_model_center", {})
        except Exception:
            state = {}
        favorites = state.get("favorites", [])
        if isinstance(favorites, list):
            self._favorites = [f for f in favorites if isinstance(f, str)]
        priority = state.get("priority", "balanced")
        if priority in PRIORITIES:
            self._priority = priority

    def _persist(self) -> None:
        if self._storage is None:
            return
        try:
            self._storage.config_set_json(
                "product_model_center",
                {"favorites": list(self._favorites), "priority": self._priority},
            )
        except Exception:
            log.debug("failed to persist model center", exc_info=True)

    # --- registry access ---

    def _models(self) -> List[ModelMetadata]:
        if self._registry is not None:
            return self._registry.list_all()
        try:
            from sentinel.models.default_registry import get_default_registry

            return get_default_registry().list_all()
        except Exception:
            log.debug("model registry unavailable", exc_info=True)
            return []

    # --- public API ---

    def list_models(self) -> Dict[str, Any]:
        models: List[Dict[str, Any]] = []
        for model in self._models():
            caps = _capabilities(model)
            models.append(
                {
                    "id": model.id,
                    "provider": model.provider,
                    "display_name": model.id,
                    "local": model.local,
                    "kind": "local" if model.local else "cloud",
                    "status": model.status.value if isinstance(model.status, ModelStatus) else str(model.status),
                    "cost": round(float(model.cost), 4),
                    "speed": model.speed,
                    "speed_label": _SPEED_LABEL.get(model.speed, model.speed),
                    "context_window": model.context_window,
                    "capabilities": caps,
                    "capability_labels": [_CAPABILITY_LABEL.get(c, c) for c in caps],
                    "recommended_use": self._recommended_use(model),
                    "tags": list(model.tags),
                    "favorite": model.id in self._favorites,
                }
            )
        models.sort(key=lambda m: (m["local"], m["cost"]))
        return {
            "models": models,
            "favorites": list(self._favorites),
            "priority": self._priority,
            "priority_label": {
                "balanced": "Equilibrado",
                "speed": "Velocidad",
                "quality": "Calidad",
                "privacy": "Privacidad",
                "cost": "Costo",
            }.get(self._priority, self._priority),
            "count": len(models),
        }

    def set_favorite(self, model_id: str, favorite: bool) -> Dict[str, Any]:
        valid_ids = {m.id for m in self._models()}
        if model_id not in valid_ids:
            return {"success": False, "error": f"Modelo desconocido: {model_id}"}
        if favorite:
            if model_id not in self._favorites:
                self._favorites.append(model_id)
        else:
            self._favorites = [f for f in self._favorites if f != model_id]
        self._persist()
        return {"success": True, "model_id": model_id, "favorite": favorite, "favorites": list(self._favorites)}

    def set_priority(self, priority: str) -> Dict[str, Any]:
        if priority not in PRIORITIES:
            return {"success": False, "error": f"Prioridad desconocida: {priority}", "priorities": list(PRIORITIES)}
        previous = self._priority
        self._priority = priority
        self._persist()
        return {"success": True, "priority": priority, "previous": previous}

    def recommended_for(self, priority: str) -> Optional[Dict[str, Any]]:
        """Pick a model by priority (used by modes to steer model selection)."""
        models = self._models()
        if not models:
            return None
        if priority == "local":
            candidates = [m for m in models if m.local]
        elif priority == "fast":
            candidates = sorted(models, key=lambda m: (m.cost, m.speed == "slow"))
        elif priority == "quality":
            candidates = sorted(models, key=lambda m: (not m.supports_reasoning, m.cost))
        elif priority == "cost":
            candidates = sorted(models, key=lambda m: m.cost)
        else:
            candidates = models
        if not candidates:
            candidates = models
        chosen = candidates[0]
        return {
            "id": chosen.id,
            "provider": chosen.provider,
            "local": chosen.local,
            "speed": chosen.speed,
            "cost": round(float(chosen.cost), 4),
        }

    @staticmethod
    def _recommended_use(model: ModelMetadata) -> str:
        tags = set(model.tags)
        if model.local:
            return "Código" if model.supports_coding else "Privado"
        if "fast" in tags and "coding" in tags:
            return "Código"
        if "vision" in tags:
            return "Imágenes"
        if "reasoning" in tags:
            return "Análisis"
        return "Conversación"
