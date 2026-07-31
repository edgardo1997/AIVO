"""Pruebas FASE 34 — Intelligence Layer Activation.

Test 1: Discovery — detecta modelos
Test 2: Ranking — elige según tarea (fast vs quality)
Test 3: Feedback — 10 ejecuciones cambian ranking
Test 4: Prediction — historial produce estimación
"""

import pytest
from sentinel.intelligence.model_discovery import ModelDiscovery, ModelCapability
from sentinel.intelligence.model_registry import ModelRegistry
from sentinel.intelligence.ranking import RankingEngine
from sentinel.intelligence.feedback import FeedbackCycle
from sentinel.intelligence.time_predictor import TaskTimePredictor, TaskProfile, TimePrediction


class TestIntelligenceActivation:

    def test_discovery_detects_ollama(self):
        """Test 1: Discovery debe detectar si Ollama está disponible."""
        discovery = ModelDiscovery()
        models = discovery.discover_ollama()
        assert isinstance(models, list)
        # Si Ollama está instalado, debe encontrar modelos
        if discovery.get_providers().get("ollama", False):
            assert len(models) > 0
            for m in models:
                assert m.provider == "ollama"
                assert m.local is True

    def test_discovery_returns_cloud_models_by_env(self):
        """Discovery retorna modelos cloud según variables de entorno."""
        discovery = ModelDiscovery()
        cloud = discovery.discover_cloud()
        assert isinstance(cloud, list)
        for m in cloud:
            assert m.local is False
            assert m.name.startswith(("gpt-", "claude-", "gemini-", "deepseek-"))

    def test_discovery_model_has_required_fields(self):
        """Cada ModelCapability tiene campos requeridos."""
        cap = ModelCapability(
            name="test-model",
            provider="ollama",
            local=True,
            context_size=4096,
            capabilities=["chat"],
        )
        assert cap.name == "test-model"
        assert cap.provider == "ollama"
        assert cap.local is True
        assert len(cap.capabilities) == 1

    def test_registry_register_and_query(self):
        """Registry almacena y responde consultas."""
        registry = ModelRegistry()
        m1 = ModelCapability(name="qwen3-8b", provider="ollama", capabilities=["coding", "reasoning"])
        m2 = ModelCapability(name="gpt-4o", provider="openai", local=False, capabilities=["coding", "reasoning", "vision"])
        registry.register(m1)
        registry.register(m2)

        available = registry.available_models()
        assert len(available) == 2

        best = registry.best_model_for("coding", required_capabilities=["coding"])
        assert best is not None
        assert "coding" in best.capabilities

    def test_registry_filters_by_capability(self):
        """Registry filtra modelos que no tienen capabilities requeridas."""
        registry = ModelRegistry()
        registry.register(ModelCapability(name="chat-model", provider="ollama", capabilities=["chat"]))
        registry.register(ModelCapability(name="code-model", provider="ollama", capabilities=["coding", "reasoning"]))

        best = registry.best_model_for("code", required_capabilities=["coding"])
        assert best is not None
        assert best.name == "code-model"

    def test_ranking_fast_vs_quality_for_chat(self):
        """Test 2: Ranking elige según tarea. Para chat, velocidad pesa más."""
        registry = ModelRegistry()
        registry.register(ModelCapability(name="fast-model", provider="local", capabilities=["chat"], latency_estimate=0.5, context_size=4096))
        registry.register(ModelCapability(name="quality-model", provider="local", capabilities=["chat", "reasoning"], latency_estimate=10.0, context_size=128000))

        ranking = RankingEngine(model_registry=registry)
        for task_type in ("chat", "reasoning"):
            results = ranking.rank_for_task(task_type, top_k=2)
            assert len(results) > 0
            for r in results:
                assert r.score > 0

    def test_feedback_changes_ranking(self):
        """Test 3: 10 ejecuciones de feedback cambian el ranking."""
        registry = ModelRegistry()
        registry.register(ModelCapability(name="model-a", provider="test", capabilities=["chat"]))
        registry.register(ModelCapability(name="model-b", provider="test", capabilities=["chat"]))

        feedback = FeedbackCycle()
        ranking = RankingEngine(model_registry=registry, feedback_engine=feedback)

        # 10 ejecuciones exitosas para model-a
        for i in range(10):
            feedback.record_outcome(
                model_id="model-a", task_type="chat",
                success=True, latency=0.5, quality_score=0.9,
            )

        # 10 ejecuciones con fallos para model-b
        for i in range(10):
            success = i < 3
            feedback.record_outcome(
                model_id="model-b", task_type="chat",
                success=success, latency=5.0, quality_score=0.3 if success else 0.1,
            )

        ranked = ranking.rank_for_task("chat", top_k=2)
        assert len(ranked) >= 2
        assert ranked[0].model_id == "model-a", "model-a debe rankear más alto tras 10 éxitos"

    def test_prediction_returns_estimate(self):
        """Test 4: TaskTimePredictor produce estimación con confianza."""
        predictor = TaskTimePredictor()

        # Sin historial — debe usar baseline
        profile = TaskProfile(task_type="chat", model_id="test-model")
        pred = predictor.predict(profile)
        assert isinstance(pred, TimePrediction)
        assert pred.estimated_seconds > 0
        assert 0 <= pred.confidence <= 1.0
        assert pred.min_estimate <= pred.estimated_seconds <= pred.max_estimate

    def test_prediction_improves_with_history(self):
        """Predicción mejora confianza con datos históricos."""
        predictor = TaskTimePredictor()

        # Registrar datos históricos
        for _ in range(20):
            predictor.record_actual("code", "gpt-4o", 8.0)

        profile = TaskProfile(task_type="code", model_id="gpt-4o")
        pred = predictor.predict(profile)
        assert pred.sample_count == 20
        assert pred.confidence > 0.5, "20 muestras deben dar confianza > 0.5"
        assert abs(pred.estimated_seconds - 8.0) < 3.0

    def test_prediction_different_tasks_different_times(self):
        """Tareas diferentes producen tiempos diferentes."""
        predictor = TaskTimePredictor()
        chat = predictor.predict(TaskProfile(task_type="chat"))
        code = predictor.predict(TaskProfile(task_type="code"))
        assert chat.estimated_seconds != code.estimated_seconds or chat.task_type != code.task_type
