"""IntelligenceEngine — Coordinador único de módulos inteligentes.

Responsabilidades:
  1. Coordinar CapabilityEngine, ModelRanking, PerformanceIntelligence,
     FeedbackEngine y ModelDiscovery.
  2. Proveer recomendaciones de modelo al Planner/DecisionEngine.
  3. Mantener métricas de rendimiento para aprendizaje continuo.
  4. Exponer una interfaz única de consulta de inteligencia.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IntelligenceRecommendation:
    """Recomendación completa para una tarea."""
    model_id: str
    confidence: float
    expected_latency_ms: float
    expected_cost: float
    reasoning: str
    capabilities_met: List[str] = field(default_factory=list)
    fallback_models: List[str] = field(default_factory=list)


class IntelligenceEngine:
    """Coordinador único de todos los módulos de inteligencia.

    Antes: ModelRanking, CapabilityEngine, PerformanceIntelligence y
    FeedbackEngine operaban sin coordinación.  IntelligenceEngine unifica
    sus outputs para producir recomendaciones consistentes.
    """

    def __init__(
        self,
        capability_engine: Any = None,
        model_ranking: Any = None,
        performance_intelligence: Any = None,
        feedback_engine: Any = None,
        model_discovery: Any = None,
        storage: Any = None,
        model_repository: Any = None,
        feedback_repository: Any = None,
    ):
        self._capability = capability_engine
        self._ranking = model_ranking
        self._perf = performance_intelligence
        self._feedback = feedback_engine
        self._discovery = model_discovery
        self._storage = storage
        self._model_repo = model_repository
        self._feedback_repo = feedback_repository
        self._model_registry = None
        self._discovered = False

    # ── Setters ───────────────────────────────────────────────

    def set_capability_engine(self, engine: Any) -> None:
        self._capability = engine

    def set_model_ranking(self, ranking: Any) -> None:
        self._ranking = ranking

    def set_performance_intelligence(self, perf: Any) -> None:
        self._perf = perf

    def set_feedback_engine(self, feedback: Any) -> None:
        self._feedback = feedback

    def set_model_discovery(self, discovery: Any) -> None:
        self._discovery = discovery

    def set_storage(self, storage: Any) -> None:
        self._storage = storage

    def set_model_repository(self, repo: Any) -> None:
        self._model_repo = repo

    def set_feedback_repository(self, repo: Any) -> None:
        self._feedback_repo = repo

    def set_model_registry(self, registry: Any) -> None:
        self._model_registry = registry

    # ── Core API ──────────────────────────────────────────────

    async def recommend_async(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
        max_cost: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceRecommendation:
        """Versión async: genera recomendación con modelos desde storage persistente.

        Flujo:
          1. Cargar modelos desde storage persistente
          2. Filtrar por capabilities requeridas (CapabilityEngine)
          3. Ordenar por ranking (ModelRanking)
          4. Ajustar por rendimiento histórico (PerformanceIntelligence)
          5. Ajustar por feedback de usuario (FeedbackEngine)
          6. Persistir recomendación
          7. Retornar la mejor opción + fallbacks
        """
        await self._load_models_from_storage(task_type)
        result = self._recommend_impl(task_type, required_capabilities, max_cost, context)
        await self._persist_recommendation(task_type, result)
        return result

    def recommend(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
        max_cost: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceRecommendation:
        """Versión sync: genera recomendación sin storage (compatible)."""
        return self._recommend_impl(task_type, required_capabilities, max_cost, context)

    def _recommend_impl(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
        max_cost: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceRecommendation:
        candidates = self._find_candidates(task_type, required_capabilities)
        if not candidates:
            return IntelligenceRecommendation(
                model_id="",
                confidence=0.0,
                expected_latency_ms=0.0,
                expected_cost=0.0,
                reasoning="No candidates found",
            )

        ranked = self._rank_models(candidates, task_type)
        scored = self._score_with_performance(ranked, task_type)
        scored = self._adjust_with_feedback(scored, context)
        scored = self._apply_cost_filter(scored, max_cost)

        if not scored:
            return IntelligenceRecommendation(
                model_id="",
                confidence=0.0,
                expected_latency_ms=0.0,
                expected_cost=0.0,
                reasoning="All candidates filtered out",
            )

        best = scored[0]
        fallbacks = [s["id"] for s in scored[1:4]] if len(scored) > 1 else []

        recommendation = IntelligenceRecommendation(
            model_id=best["id"],
            confidence=best.get("score", 0.5),
            expected_latency_ms=best.get("latency", 0),
            expected_cost=best.get("cost", 0),
            reasoning=best.get("reason", "IntelligenceEngine selection"),
            capabilities_met=best.get("capabilities", []),
            fallback_models=fallbacks,
        )

        return recommendation

    async def _load_models_from_storage(self, task_type: str) -> None:
        """Carga modelos desde storage persistente."""
        if self._model_repo is None:
            return
        try:
            stored = await self._model_repo.list_all()
            if stored and not self._discovered:
                from sentinel.intelligence.model_discovery import ModelCapability
                for s in stored:
                    discovery = ModelCapability(
                        name=s.name,
                        provider=s.provider,
                        local=s.local,
                        context_size=s.context_size,
                        cost=s.cost,
                        latency_estimate=s.latency_estimate,
                        capabilities=s.capabilities or ["chat"],
                    )
                    if self._model_registry:
                        self._model_registry.register(discovery, manual=False)
                self._discovered = True
                logger.info("Loaded %d models from storage", len(stored))
        except Exception as e:
            logger.warning("Failed to load models from storage: %s", e)

    async def _persist_recommendation(self, task_type: str, rec: IntelligenceRecommendation) -> None:
        """Persiste la recomendación para aprendizaje futuro."""
        if self._storage is None:
            return
        try:
            from sentinel.storage.models import DecisionRecord
            record = DecisionRecord(
                request=f"intel_recommend:{task_type}",
                intent=f"task_type={task_type}",
                decision="RECOMMEND",
                risk_level="low",
                selected_model=rec.model_id,
                reason=rec.reasoning,
            )
            if hasattr(self._storage, "save_decision"):
                await self._storage.save_decision(record)
            elif self._model_repo:
                from sentinel.storage.models import StoredModel
                found = await self._model_repo.get_by_name(rec.model_id, "")
                if found:
                    await self._model_repo.update_last_seen(found.id)
        except Exception as e:
            logger.warning("Failed to persist recommendation: %s", e)

    # Backward-compatible sync version
    def recommend(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
        max_cost: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntelligenceRecommendation:
        return IntelligenceRecommendation(
            model_id="",
            confidence=0.0,
            expected_latency_ms=0.0,
            expected_cost=0.0,
            reasoning="Sync recommend deprecated — use await recommend_async",
        )

    def get_best_model(
        self,
        task_type: str,
        required_capabilities: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Atajo para obtener solo el ID del mejor modelo."""
        rec = self.recommend(task_type, required_capabilities)
        return rec.model_id or None

    # ── Internal pipeline ─────────────────────────────────────

    def _find_candidates(
        self, task_type: str, required_capabilities: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        if self._capability is None:
            if self._ranking:
                return [{"id": m.id} for m in self._ranking.get_top_k(10)] if hasattr(self._ranking, "get_top_k") else []
            return []

        candidates = []
        cap_set = self._capability.get_capabilities(task_type) if hasattr(self._capability, "get_capabilities") else None
        for model_id in self._list_available_models():
            caps = self._capability.get_model_capabilities(model_id) if hasattr(self._capability, "get_model_capabilities") else []
            if required_capabilities:
                if not all(c in caps for c in required_capabilities):
                    continue
            candidates.append({
                "id": model_id,
                "capabilities": caps,
                "task_type": task_type,
            })
        return candidates

    def _list_available_models(self) -> List[str]:
        models = []
        if self._ranking and hasattr(self._ranking, "get_top_k"):
            models.extend([s.get("model_id", s.id) for s in self._ranking.get_top_k(50)])
        if self._discovery and hasattr(self._discovery, "list_models"):
            models.extend(self._discovery.list_models())
        return list(dict.fromkeys(models))

    def _rank_models(self, candidates: List[Dict[str, Any]], task_type: str) -> List[Dict[str, Any]]:
        if self._ranking is None:
            return candidates
        try:
            ranked_scores = self._ranking.get_top_k(20, task_type=task_type)
            score_map = {s.get("model_id", s.id): s for s in ranked_scores}
            for c in candidates:
                s = score_map.get(c["id"])
                c["score"] = getattr(s, "score", 0.5) if s else 0.5
                c["rank"] = getattr(s, "rank", 0) if s else 0
            candidates.sort(key=lambda x: x.get("rank", 999))
        except Exception as e:
            logger.warning("Model ranking failed: %s", e)
        return candidates

    def _score_with_performance(self, candidates: List[Dict[str, Any]], task_type: str) -> List[Dict[str, Any]]:
        if self._perf is None:
            return candidates
        try:
            for c in candidates:
                metrics = self._perf.get_model_metrics(c["id"], task_type) if hasattr(self._perf, "get_model_metrics") else {}
                if metrics:
                    c["latency"] = metrics.get("avg_latency_ms", 0)
                    c["cost"] = metrics.get("avg_cost", 0)
                    c["success_rate"] = metrics.get("success_rate", 1.0)
                    c["score"] = c.get("score", 0.5) * c["success_rate"]
        except Exception as e:
            logger.warning("Performance scoring failed: %s", e)
        return candidates

    def _adjust_with_feedback(self, candidates: List[Dict[str, Any]], context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self._feedback is None or context is None:
            return candidates
        try:
            user_id = context.get("user_id", "")
            if user_id:
                prefs = self._feedback.get_user_preferences(user_id) if hasattr(self._feedback, "get_user_preferences") else {}
                preferred_model = prefs.get("preferred_model")
                if preferred_model:
                    for c in candidates:
                        if c["id"] == preferred_model:
                            c["score"] = c.get("score", 0.5) * 1.2
        except Exception as e:
            logger.warning("Feedback adjustment failed: %s", e)
        return candidates

    def _apply_cost_filter(self, candidates: List[Dict[str, Any]], max_cost: Optional[float]) -> List[Dict[str, Any]]:
        if max_cost is None:
            return candidates
        return [c for c in candidates if c.get("cost", 0) <= max_cost]
