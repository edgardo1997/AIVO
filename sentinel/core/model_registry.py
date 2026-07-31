from __future__ import annotations
import dataclasses
from typing import Any, Dict, List, Optional, Sequence
import logging
import threading

from sentinel.models import ModelMetadata, ModelStatus

logger = logging.getLogger(__name__)

TASK_CAPABILITY_MAP: Dict[str, List[str]] = {
    "chat": [],
    "coding": ["coding", "reasoning"],
    "action": ["tool_calling"],
    "reasoning": ["reasoning"],
    "analysis": ["reasoning"],
    "vision": ["vision"],
    "quick": [],
    "creative": [],
    "local": ["local"],
    "embeddings": ["embeddings"],
}


class ModelRegistry:
    def __init__(self) -> None:
        self._models: Dict[str, ModelMetadata] = {}
        self._lock = threading.Lock()

    def register(self, model: ModelMetadata) -> None:
        if not isinstance(model, ModelMetadata):
            raise TypeError(f"Expected ModelMetadata, got {type(model).__name__}")
        with self._lock:
            if model.id in self._models:
                raise ValueError(f"Model '{model.id}' is already registered")
            self._models[model.id] = model
            logger.info("Model registered: %s (provider=%s, tool_calling=%s)", model.id, model.provider, model.supports_tool_calling)

    def register_many(self, models: Sequence[ModelMetadata]) -> None:
        for m in models:
            self.register(m)

    def upsert(self, model: ModelMetadata) -> bool:
        """Registra o actualiza un modelo. Devuelve True si es nuevo."""
        if not isinstance(model, ModelMetadata):
            raise TypeError(f"Expected ModelMetadata, got {type(model).__name__}")
        with self._lock:
            is_new = model.id not in self._models
            self._models[model.id] = model
            return is_new

    def update(self, model: ModelMetadata) -> None:
        """Actualiza (o inserta) un modelo sin lanzar error por duplicado."""
        self.upsert(model)

    def update_metrics(
        self,
        model_id: str,
        latency_avg: Optional[float] = None,
        cost_input: Optional[float] = None,
        cost_output: Optional[float] = None,
        success_rate: Optional[float] = None,
        usage_count: Optional[int] = None,
        status: Optional[ModelStatus] = None,
    ) -> bool:
        """Actualiza métricas observadas de un modelo (ranking / failover)."""
        model = self._models.get(model_id)
        if model is None:
            return False
        changes: Dict[str, Any] = {}
        if latency_avg is not None:
            changes["config"] = {**model.config, "latency_avg": latency_avg}
        if cost_input is not None:
            changes["config"] = {**(changes.get("config") or model.config), "cost_input": cost_input}
        if cost_output is not None:
            changes["config"] = {**(changes.get("config") or model.config), "cost_output": cost_output}
        if success_rate is not None:
            changes["config"] = {**(changes.get("config") or model.config), "success_rate": success_rate}
        if usage_count is not None:
            changes["config"] = {**(changes.get("config") or model.config), "usage_count": usage_count}
        if status is not None:
            changes["status"] = status
        with self._lock:
            self._models[model_id] = dataclasses.replace(model, **changes)
        return True

    def set_status(self, model_id: str, status: ModelStatus) -> bool:
        return self.update_metrics(model_id=model_id, status=status)

    def find_best(
        self,
        task_type: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        strategy: str = "priority",
        prefer_local: bool = False,
    ) -> Optional[ModelMetadata]:
        """Elige el mejor modelo candidato según estrategia."""
        candidates = self.find_candidates(required_capabilities or [])
        if not candidates:
            return None
        if prefer_local:
            candidates.sort(key=lambda m: (not m.local, m.cost))
        elif strategy == "cost":
            candidates.sort(key=lambda m: (m.cost, m.local))
        elif strategy == "local_first":
            candidates.sort(key=lambda m: (not m.local, m.cost))
        else:
            candidates.sort(key=lambda m: m.cost)
        return candidates[0]

    def get(self, model_id: str) -> Optional[ModelMetadata]:
        return self._models.get(model_id)

    def unregister(self, model_id: str) -> None:
        with self._lock:
            if model_id not in self._models:
                raise KeyError(f"Model '{model_id}' not found in registry")
            del self._models[model_id]

    def list_all(self) -> List[ModelMetadata]:
        return list(self._models.values())

    def list_available(self) -> List[ModelMetadata]:
        return [m for m in self._models.values() if m.status == ModelStatus.AVAILABLE]

    def find_by_capability(self, capability: str) -> List[ModelMetadata]:
        return [m for m in self._models.values() if m.has_capability(capability)]

    def find_by_provider(self, provider: str) -> List[ModelMetadata]:
        return [m for m in self._models.values() if m.provider == provider]

    def find_by_tag(self, tag: str) -> List[ModelMetadata]:
        return [m for m in self._models.values() if tag in m.tags]

    def find_candidates(self, required_capabilities: List[str]) -> List[ModelMetadata]:
        if not required_capabilities:
            return self.list_available()
        candidates = []
        for m in self.list_available():
            if all(m.has_capability(cap) for cap in required_capabilities):
                candidates.append(m)
        return candidates

    def count(self) -> int:
        return len(self._models)

    def clear(self) -> None:
        with self._lock:
            self._models.clear()

    # ── Persistencia (ModelRepository) ──────────────────────────

    @staticmethod
    def to_stored_model(model: ModelMetadata) -> Any:
        from sentinel.storage.models import StoredModel

        capabilities = []
        if model.supports_tool_calling:
            capabilities.append("tool_calling")
        if model.supports_vision:
            capabilities.append("vision")
        if model.supports_coding:
            capabilities.append("coding")
        if model.supports_reasoning:
            capabilities.append("reasoning")
        if model.supports_embeddings:
            capabilities.append("embeddings")
        if model.local:
            capabilities.append("local")
        return StoredModel(
            id=model.id,
            name=model.id,
            provider=model.provider,
            local=model.local,
            capabilities=capabilities,
            context_size=model.context_window,
            cost=model.cost,
        )

    @staticmethod
    def from_stored_model(stored: Any) -> ModelMetadata:
        caps = set(stored.capabilities)
        return ModelMetadata(
            id=stored.name,
            provider=stored.provider,
            context_window=stored.context_size,
            supports_tool_calling="tool_calling" in caps,
            supports_vision="vision" in caps,
            supports_coding="coding" in caps,
            supports_reasoning="reasoning" in caps,
            supports_embeddings="embeddings" in caps,
            cost=stored.cost,
            local=stored.local,
            status=ModelStatus.AVAILABLE,
            tags=[stored.provider] + [c for c in caps if c != "local"],
            config={
                "latency_avg": stored.latency_estimate,
                "last_seen": stored.last_seen,
            },
        )

    async def load_from_repository(self, repo: Any) -> int:
        """Carga modelos persistidos desde el ModelRepository."""
        stored_models = await repo.list_all()
        loaded = 0
        for stored in stored_models:
            try:
                meta = self.from_stored_model(stored)
                is_new = self.upsert(meta)
                if is_new:
                    loaded += 1
            except Exception as e:
                logger.warning("Failed to load stored model %s: %s", getattr(stored, "id", "?"), e)
        logger.info("Registry loaded %d model(s) from repository (total=%d)", loaded, self.count())
        return loaded

    async def persist_to_repository(self, repo: Any) -> int:
        """Persiste todos los modelos del registro al ModelRepository."""
        saved = 0
        for model in self.list_all():
            try:
                await repo.save(self.to_stored_model(model))
                saved += 1
            except Exception as e:
                logger.warning("Failed to persist model %s: %s", model.id, e)
        logger.info("Registry persisted %d model(s) to repository", saved)
        return saved
