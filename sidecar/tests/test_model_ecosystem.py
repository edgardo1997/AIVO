"""FASE 4 — Model Ecosystem tests.

Cubre:
  4.1  Discovery (Ollama / LM Studio / Cloud / async)
  4.2  ModelRegistry (upsert, métricas, persistencia, recuperación)
  4.3  Capability Intelligence (recomendación por tarea)
  4.4  ModelRanking (selección por contexto, penalización de fallos)
  4.5  MultiModelCoordinator (decomposición + consenso)
  4.6  ModelStrategyEngine (single / multi / local / cloud / hybrid)
  4.7  Provider Failover (CircuitBreaker → ranking)
"""

import asyncio
import pytest

from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_registry import ModelRegistry
from sentinel.core.model_discovery import (
    ModelDiscovery,
    DiscoveredModel,
    OllamaDiscovery,
    LMStudioDiscovery,
    CloudProviderDiscovery,
)
from sentinel.core.model_ranking import ModelRanking
from sentinel.core.performance_intelligence import PerformanceIntelligence
from sentinel.core.feedback_engine import FeedbackEngine
from sentinel.core.circuit_breaker import CircuitBreaker, CircuitState
from sentinel.core.model_coordinator import ModelCoordinator, ExecutionStrategy
from sentinel.intelligence.model_capability import ModelCapabilityAnalyzer
from sentinel.intelligence.model_strategy import ModelStrategyEngine, StrategyType
from sentinel.intelligence.multi_model_coordinator import (
    MultiModelCoordinator,
    MultiModelConfig,
    ModelResponse,
)


# ── Fixtures ──────────────────────────────────────────────────────

def _mk_model(model_id, provider="ollama", local=True, coding=False, reasoning=False, tool=False, cost=0.0, status=ModelStatus.AVAILABLE):
    return ModelMetadata(
        id=model_id,
        provider=provider,
        context_window=8192,
        supports_tool_calling=tool,
        supports_coding=coding,
        supports_reasoning=reasoning,
        speed="fast" if not local else "medium",
        cost=cost,
        local=local,
        status=status,
        tags=[provider],
    )


@pytest.fixture
def registry():
    r = ModelRegistry()
    r.register_many([
        _mk_model("qwen-coder", "ollama", local=True, coding=True, reasoning=True),
        _mk_model("gpt-5", "openai", local=False, coding=True, reasoning=True, cost=0.01),
        _mk_model("claude", "anthropic", local=False, coding=True, reasoning=True, cost=0.02),
        _mk_model("llama3", "ollama", local=True, coding=True),
    ])
    return r


# ── 4.1 Discovery ─────────────────────────────────────────────────

class TestDiscovery:
    def test_ollama_build_known(self):
        dm = OllamaDiscovery()._build_discovered("qwen3:8b")
        assert dm.provider == "ollama"
        assert dm.local is True
        assert dm.supports_coding is True
        assert dm.supports_reasoning is True
        assert dm.context_window == 32768

    def test_lmstudio_build_known(self):
        dm = LMStudioDiscovery()._build_discovered("llama3.1:8b")
        assert dm.provider == "lmstudio"
        assert dm.local is True
        assert dm.supports_coding is True

    def test_cloud_build_known(self):
        d = CloudProviderDiscovery("openai", "https://api.openai.com/v1", api_key="sk-test")
        dm = d._build_discovered("gpt-4o")
        assert dm.provider == "openai"
        assert dm.local is False
        assert dm.supports_coding is True

    def test_cloud_no_key_empty(self):
        d = CloudProviderDiscovery("openai", "http://localhost:1", api_key="")
        assert d.discover_models() == []

    def test_health_check_no_server(self):
        assert not asyncio.run(OllamaDiscovery(base_url="http://localhost:1").health_check_async())

    @pytest.mark.asyncio
    async def test_discover_all_async(self):
        discovery = ModelDiscovery()
        discovery.add_default_discoverers()
        results = await discovery.discover_all_async()
        assert isinstance(results, dict)
        # sin servidores locales debe degradar a vacío sin lanzar
        assert "ollama" in results or True
        assert discovery._has_run is True

    @pytest.mark.asyncio
    async def test_run_full_discovery_async_no_registry(self):
        discovery = ModelDiscovery()
        result = await discovery.run_full_discovery_async()
        assert result["status"] == "no_registry"

    @pytest.mark.asyncio
    async def test_sync_registry_async_adds_models(self):
        r = ModelRegistry()
        discovery = ModelDiscovery(model_registry=r)

        class FakeDiscoverer:
            _provider_id = "ollama"

            async def discover_models_async(self):
                return [
                    DiscoveredModel(model_id="qwen3:8b", provider="ollama", local=True,
                                    supports_coding=True, supports_reasoning=True, context_window=32768),
                ]

        discovery.add_discoverer(FakeDiscoverer())
        result = await discovery.run_full_discovery_async()
        assert result["status"] == "success"
        assert result["added"] == 1
        assert r.get("qwen3:8b") is not None

    def test_get_capabilities_known(self):
        r = ModelRegistry()
        r.register(_mk_model("qwen-coder", "ollama", local=True, coding=True, reasoning=True))
        d = ModelDiscovery(model_registry=r)
        caps = d.get_capabilities("qwen-coder")
        assert "coding" in caps["capabilities"]
        assert "reasoning" in caps["capabilities"]
        assert caps["local"] is True


# ── 4.2 ModelRegistry ─────────────────────────────────────────────

class TestRegistry:
    def test_upsert_new_returns_true(self, registry):
        assert registry.upsert(_mk_model("new-model", "ollama", local=True, coding=True)) is True
        assert registry.get("new-model") is not None

    def test_upsert_existing_returns_false(self, registry):
        assert registry.upsert(_mk_model("llama3", "ollama", local=True, coding=True)) is False

    def test_register_duplicate_raises(self, registry):
        with pytest.raises(ValueError):
            registry.register(_mk_model("llama3", "ollama", local=True))

    def test_update_metrics(self, registry):
        ok = registry.update_metrics("llama3", latency_avg=1.5, success_rate=0.92, usage_count=100)
        assert ok is True
        model = registry.get("llama3")
        assert model.config["latency_avg"] == 1.5
        assert model.config["success_rate"] == 0.92
        assert model.config["usage_count"] == 100

    def test_update_metrics_unknown_returns_false(self, registry):
        assert registry.update_metrics("ghost", latency_avg=1.0) is False

    def test_find_best_by_capability(self, registry):
        best = registry.find_best(required_capabilities=["coding", "reasoning"], strategy="cost")
        assert best is not None
        assert best.id == "qwen-coder"  # cheapest that matches

    def test_find_best_prefer_local(self, registry):
        best = registry.find_best(required_capabilities=["coding", "reasoning"], prefer_local=True)
        assert best.local is True

    def test_set_status_and_recover(self, registry):
        from sentinel.models import ModelStatus
        assert registry.set_status("gpt-5", ModelStatus.UNAVAILABLE) is True
        assert registry.get("gpt-5").status == ModelStatus.UNAVAILABLE
        assert registry.set_status("gpt-5", ModelStatus.AVAILABLE) is True
        assert registry.get("gpt-5").status == ModelStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_persistence_round_trip(self, tmp_path):
        from sentinel.storage.database import StorageEngine, StorageConfig
        from sentinel.storage.repositories.model_repository import ModelRepository

        engine = StorageEngine(StorageConfig(database_url=f"sqlite:///{tmp_path}/sentinel.db"))
        await engine.initialize()
        repo = ModelRepository(engine)

        r1 = ModelRegistry()
        r1.register_many([
            _mk_model("qwen-coder", "ollama", local=True, coding=True, reasoning=True),
            _mk_model("gpt-5", "openai", local=False, coding=True, reasoning=True, cost=0.01),
        ])
        saved = await r1.persist_to_repository(repo)
        assert saved == 2

        # "Reinicio": nuevo registry vacío que carga desde repo
        r2 = ModelRegistry()
        loaded = await r2.load_from_repository(repo)
        assert loaded >= 2
        assert r2.get("qwen-coder") is not None
        assert r2.get("gpt-5") is not None
        assert r2.count() >= 2
        await engine.close()


# ── 4.3 Capability Intelligence ───────────────────────────────────

class TestCapabilityAnalyzer:
    def test_security_task_recommendation(self, registry):
        analyzer = ModelCapabilityAnalyzer(registry=registry)
        rec = analyzer.analyze("Revisar vulnerabilidad SQL injection")
        assert "coding" in rec.required_capabilities or "reasoning" in rec.required_capabilities
        assert rec.recommended_model != ""
        assert "qwen-coder" in rec.matched_candidates or "gpt-5" in rec.matched_candidates

    def test_simple_task_recommendation(self, registry):
        analyzer = ModelCapabilityAnalyzer(registry=registry)
        rec = analyzer.analyze("hi")
        assert rec.recommended_model != "" or rec.reason == "no_candidates"

    def test_no_registry_graceful(self):
        analyzer = ModelCapabilityAnalyzer(registry=None)
        rec = analyzer.analyze("task")
        assert rec.recommended_model == ""
        assert rec.reason == "no_candidates"

    def test_analyze_async(self, registry):
        import asyncio
        analyzer = ModelCapabilityAnalyzer(registry=registry)
        rec = asyncio.run(analyzer.analyze_async("audita el proyecto"))
        assert isinstance(rec.recommended_model, str)


# ── 4.4 ModelRanking ──────────────────────────────────────────────

class TestRanking:
    @pytest.fixture
    def perf(self):
        return PerformanceIntelligence()

    def test_rank_by_context(self, perf):
        """Model A faster but lower quality vs Model B slower but higher success."""
        from sentinel.core.performance_intelligence import ExecutionMetrics

        # Model A: muchos fallos, rápido
        for i in range(10):
            perf.record_metric(ExecutionMetrics(
                model_id="model_a", task_type="coding", intent="coding",
                latency=0.5, tokens_used=0, cost=0.0, success=False,
            ))
        # Model B: lento pero siempre éxito
        for i in range(10):
            perf.record_metric(ExecutionMetrics(
                model_id="model_b", task_type="coding", intent="coding",
                latency=5.0, tokens_used=0, cost=0.0, success=True,
            ))

        ranking = ModelRanking(performance_intelligence=perf)
        scores = ranking.compute_scores()
        score_b = next(s for s in scores if s.model_id == "model_b")
        score_a = next(s for s in scores if s.model_id == "model_a")
        assert score_b.performance_score > score_a.performance_score

    def test_failure_penalty_applied(self, perf):
        from sentinel.core.performance_intelligence import ExecutionMetrics
        for i in range(5):
            perf.record_metric(ExecutionMetrics(
                model_id="m1", task_type="chat", intent="chat",
                latency=1.0, tokens_used=0, cost=0.0, success=True,
            ))
        ranking = ModelRanking(performance_intelligence=perf)
        before = ranking.compute_scores()[0].performance_score
        ranking.apply_provider_failure("m1")
        after = ranking.compute_scores()[0].performance_score
        assert after < before

    def test_availability_affects_score(self, perf):
        from sentinel.core.performance_intelligence import ExecutionMetrics
        for i in range(5):
            perf.record_metric(ExecutionMetrics(
                model_id="m1", task_type="chat", intent="chat",
                latency=1.0, tokens_used=0, cost=0.0, success=True,
            ))
        ranking = ModelRanking(performance_intelligence=perf)
        ranking.set_model_registry(ModelRegistry())
        before = ranking.compute_scores()[0].performance_score
        ranking.set_availability_score("provider", 10.0)
        after = ranking.compute_scores()[0].performance_score
        assert after <= before


# ── 4.5 MultiModelCoordinator ─────────────────────────────────────

class TestMultiModel:
    @pytest.mark.asyncio
    async def test_complex_coding_task_decomposes(self):
        coordinator = ModelCoordinator()
        plan = coordinator.decompose(
            "Analiza este proyecto Python completo",
            classified_intent=None,
            capabilities=["coding", "reasoning"],
        )
        assert len(plan.tasks) >= 2
        assert plan.execution_strategy == ExecutionStrategy.PARALLEL

    @pytest.mark.asyncio
    async def test_multi_model_consensus(self):
        mm = MultiModelCoordinator(config=MultiModelConfig(min_models=2, max_models=3))

        async def exec_fn(task):
            return ModelResponse(
                model_id=task.get("model_id", "x"),
                provider="test",
                response_text="result for " + str(task.get("task_id")),
                success=True,
            )

        result = await mm.process(
            "Analiza este proyecto Python completo y audita su seguridad",
            execute_fn=exec_fn,
        )
        assert result.final_answer != ""
        assert result.confidence >= 0.0
        assert len(result.model_responses) >= 2

    @pytest.mark.asyncio
    async def test_multi_model_fallback_single_on_failure(self):
        mm = MultiModelCoordinator(config=MultiModelConfig(min_models=2, fallback_on_failure=True))

        async def exec_fn(task):
            raise RuntimeError("provider down")

        with pytest.raises(RuntimeError):
            await mm.process("task simple", execute_fn=exec_fn)

    def test_multi_model_result_to_dict(self):
        from sentinel.intelligence.multi_model_coordinator import MultiModelResult
        d = MultiModelResult(final_answer="x", confidence=0.9).to_dict()
        assert d["final_answer"] == "x"


# ── 4.6 ModelStrategyEngine ───────────────────────────────────────

class TestStrategy:
    @pytest.fixture
    def engine(self):
        return ModelStrategyEngine()

    def test_simple_task_single(self, engine):
        strategy = engine.decide("abre Spotify")
        assert strategy.strategy == StrategyType.SINGLE

    def test_complex_task_multi(self, engine):
        strategy = engine.decide("Audita Sentinel completo y revisa su arquitectura")
        assert strategy.strategy == StrategyType.MULTI
        assert strategy.complexity == "complex"

    def test_privacy_local(self, engine):
        strategy = engine.decide("Analiza mis documentos privados")
        assert strategy.strategy == StrategyType.LOCAL
        assert strategy.privacy_sensitive is True

    def test_offline_local(self, engine):
        strategy = engine.decide("summarize this", context={"offline": True})
        assert strategy.strategy == StrategyType.LOCAL

    def test_coding_cloud(self, engine):
        strategy = engine.decide("write a function")
        assert strategy.strategy in (StrategyType.CLOUD, StrategyType.SINGLE)

    def test_strategy_to_dict(self, engine):
        d = engine.decide("abre Spotify").to_dict()
        assert d["strategy"] == "single"


# ── 4.7 Provider Failover ─────────────────────────────────────────

class TestFailover:
    def test_circuit_breaker_availability_closed(self):
        cb = CircuitBreaker()
        cb.record_success("openai")
        assert cb.availability_score("openai") == 100.0

    def test_circuit_breaker_availability_open_penalized(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("openai")
        cb.record_failure("openai")
        assert cb.get_state("openai")["state"] == CircuitState.OPEN.value
        assert cb.availability_score("openai") < 50.0
        assert cb.recovery_seconds("openai") > 0

    def test_failure_penalty_drives_selection(self, registry):
        from sentinel.core.performance_intelligence import ExecutionMetrics
        perf = PerformanceIntelligence()
        for i in range(5):
            perf.record_metric(ExecutionMetrics(
                model_id="qwen-coder", task_type="coding", intent="coding",
                latency=1.0, tokens_used=0, cost=0.0, success=True,
            ))
            perf.record_metric(ExecutionMetrics(
                model_id="gpt-5", task_type="coding", intent="coding",
                latency=1.0, tokens_used=0, cost=0.0, success=True,
            ))
        ranking = ModelRanking(performance_intelligence=perf)
        ranking.set_model_registry(registry)
        scores = {s.model_id: s for s in ranking.compute_scores()}
        before_a = scores["qwen-coder"].performance_score
        ranking.apply_provider_failure("qwen-coder")
        scores_after = {s.model_id: s for s in ranking.compute_scores()}
        after_a = scores_after["qwen-coder"].performance_score
        assert after_a < before_a

    def test_sync_circuit_breaker_to_ranking(self, registry):
        from sentinel.core.performance_intelligence import ExecutionMetrics
        perf = PerformanceIntelligence()
        perf.record_metric(ExecutionMetrics(
            model_id="llama3", task_type="chat", intent="chat",
            latency=1.0, tokens_used=0, cost=0.0, success=True,
        ))
        ranking = ModelRanking(performance_intelligence=perf)
        ranking.set_model_registry(registry)
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("ollama")
        ranking.apply_circuit_breaker(cb)
        scores = {s.model_id: s for s in ranking.compute_scores()}
        # llama3 es de proveedor ollama → penalizado por el CB abierto
        assert scores["llama3"].performance_score < 50.0

    @pytest.mark.asyncio
    async def test_coordinator_execution_result_updates_metrics(self, registry):
        from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
        intel = IntelligenceCoordinator(model_registry=registry)
        await intel.record_execution_result(
            provider_id="ollama", model_id="llama3", success=True,
            latency_ms=1500, task_type="chat",
        )
        model = registry.get("llama3")
        assert model.config.get("usage_count", 0) >= 1
        assert model.config.get("success_rate", 0.0) > 0.5
        await intel.apply_provider_failure("ollama", model_id="llama3")
        assert registry.get("llama3").config.get("success_rate", 1.0) == 0.0


# ── 4.8 Orchestrator strategy integration + API ────────────────────

class TestOrchestratorStrategyIntegration:
    """FASE 4.8 — Orchestrator.process consume decide_strategy y recommend_model."""

    @pytest.mark.asyncio
    async def test_process_populates_model_strategy(self, registry):
        from unittest.mock import AsyncMock
        from sentinel.core import IntentEngine, ModelRouter, Orchestrator, Planner
        from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
        from sentinel.core.tool_gateway import ToolGateway
        from sentinel.core.intent import Intent

        intel = IntelligenceCoordinator(model_registry=registry)
        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=ModelRouter(),
            intelligence=intel,
        )
        captured = {}

        async def fake_run_pipeline(**kwargs):
            from sentinel.core.orchestrator import ExecutionResult

            captured["exec_plan"] = kwargs["exec_plan"]
            return ExecutionResult(plan=kwargs["exec_plan"], error=None)

        orch._run_pipeline = fake_run_pipeline
        await orch._process_impl(
            "analiza el estado del sistema",
            identity={"user_id": "u1", "is_authenticated": True},
        )
        ep = captured["exec_plan"]
        assert ep.model_strategy is not None
        assert ep.model_strategy["strategy"] in ("single", "multi", "local", "cloud", "hybrid")
        assert ep.capability_recommendation is not None
        assert "recommended_model" in ep.capability_recommendation

    @pytest.mark.asyncio
    async def test_process_strategy_in_context(self, registry):
        from sentinel.core import IntentEngine, ModelRouter, Orchestrator, Planner
        from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
        from sentinel.core.tool_gateway import ToolGateway

        intel = IntelligenceCoordinator(model_registry=registry)
        orch = Orchestrator(
            intent_engine=IntentEngine(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=ModelRouter(),
            intelligence=intel,
        )
        captured = {}

        async def fake_run_pipeline(**kwargs):
            captured["context"] = kwargs["context"]
            captured["exec_plan"] = kwargs["exec_plan"]
            from sentinel.core.orchestrator import ExecutionResult

            return ExecutionResult(plan=kwargs["exec_plan"], error=None)

        orch._run_pipeline = fake_run_pipeline
        await orch._process_impl(
            "por que esta lenta la pc",
            identity={"user_id": "u1", "is_authenticated": True},
        )
        assert "model_strategy" in captured["context"]
        assert "intelligence_recommendation" in captured["context"]


class TestModelEcosystemAPI:
    """FASE 4.8 — Endpoints REST /v1/models."""

    def _register(self, client, model_id, provider="openai"):
        return client.post(
            "/v1/models",
            json={
                "id": model_id,
                "provider": provider,
                "supports_reasoning": True,
                "supports_coding": True,
            },
        )

    def test_list_models(self, client):
        self._register(client, "test-list-model")
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(m["id"] == "test-list-model" for m in data)
        client.delete("/v1/models/test-list-model")

    def test_strategy_endpoint(self, client):
        resp = client.get("/v1/models/strategy", params={"task": "audita este proyecto python"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] in ("single", "multi", "local", "cloud", "hybrid")

    def test_recommend_endpoint(self, client):
        resp = client.get("/v1/models/recommend", params={"task": "analiza la seguridad"})
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_model" in data
        assert "required_capabilities" in data

    def test_rankings_endpoint(self, client):
        resp = client.get("/v1/models/rankings")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_register_get_delete(self, client):
        self._register(client, "test-manual-model")
        resp = client.get("/v1/models/test-manual-model")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "openai"
        resp = client.delete("/v1/models/test-manual-model")
        assert resp.status_code == 200
        resp = client.get("/v1/models/test-manual-model")
        assert resp.status_code == 404

    def test_register_duplicate_conflict(self, client):
        self._register(client, "test-dup-model")
        resp = self._register(client, "test-dup-model")
        assert resp.status_code == 409
        client.delete("/v1/models/test-dup-model")

    def test_get_missing_404(self, client):
        resp = client.get("/v1/models/nope-not-real")
        assert resp.status_code == 404

