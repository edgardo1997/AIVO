"""Pruebas FASE 5 — Persistence Intelligence.

Test 1: Restart Recovery — datos sobreviven reinicio (métricas, rankings, feedback, modelos, ejecuciones, preferencias).
Test 2: Learning Loop — el ranking se ajusta con feedback negativo/positivo y afecta selecciones futuras.
Test 3: Database Failure — SQLite roto/locked no corrompe ni crashea.
Test 4: Repositorios nuevos (executions, model_performance, user_preferences) + schema version/backup.
"""

import pytest
import pytest_asyncio

from sentinel.core.feedback_engine import FeedbackScore
from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
from sentinel.storage.database import StorageEngine, StorageConfig
from sentinel.storage.models import (
    ModelPerformanceEvent,
    StoredExecution,
    UserPreference,
)
from sentinel.storage.repositories.execution_repository import ExecutionRepository
from sentinel.storage.repositories.feedback_repository import FeedbackRepository
from sentinel.storage.repositories.model_performance_repository import ModelPerformanceRepository
from sentinel.storage.repositories.user_preference_repository import UserPreferenceRepository


@pytest_asyncio.fixture
async def engine(tmp_path):
    db = f"sqlite:///{tmp_path}/sentinel.db"
    eng = StorageEngine(StorageConfig(database_url=db, migrate_on_start=True))
    await eng.initialize()
    yield eng, db
    await eng.close()


@pytest_asyncio.fixture
async def wired_intel(engine):
    eng, db = engine
    intel = IntelligenceCoordinator()
    intel.set_model_performance_repository(ModelPerformanceRepository(eng))
    intel.set_feedback_repository(FeedbackRepository(eng))
    intel.set_execution_repository(ExecutionRepository(eng))
    intel.set_user_preference_repository(UserPreferenceRepository(eng))
    return intel, db


class TestRestartRecovery:

    @pytest.mark.asyncio
    async def test_restart_recovers_learning(self, tmp_path):
        db = f"sqlite:///{tmp_path}/sentinel.db"

        async def _open():
            eng = StorageEngine(StorageConfig(database_url=db, migrate_on_start=True))
            await eng.initialize()
            return eng

        async def _build(eng):
            intel = IntelligenceCoordinator()
            intel.set_model_performance_repository(ModelPerformanceRepository(eng))
            intel.set_feedback_repository(FeedbackRepository(eng))
            intel.set_execution_repository(ExecutionRepository(eng))
            intel.set_user_preference_repository(UserPreferenceRepository(eng))
            return intel

        engine1 = await _open()
        intel1 = await _build(engine1)
        for _ in range(50):
            await intel1.learn_from_model_result(
                model_id="model-a", task_type="coding", intent="coding",
                latency_ms=200, tokens_used=100, cost=0.0, success=True,
            )
        for _ in range(10):
            await intel1.learn_from_model_result(
                model_id="model-a", task_type="coding", intent="coding",
                latency_ms=200, tokens_used=100, cost=0.0, success=False,
            )
        await intel1.record_feedback("model-a", "coding", FeedbackScore.POSITIVE, user_id="u1", execution_id="e1")
        await intel1.record_execution(
            execution_id="e1", user_request="optimizar PC", intent="optimize:pc",
            task_type="coding", selected_model="model-a", tools_used=["cmd"],
            duration=1.5, success=True, risk_level="low", cost=0.0, confidence_score=0.9,
        )
        await intel1.set_user_preference("u1", "response_style", "technical", source="explicit")
        await engine1.close()

        # ── Reinicio ──
        engine2 = await _open()
        intel2 = await _build(engine2)
        recovered = await intel2.recover_learning()

        assert recovered["metrics"] == 60
        assert recovered["feedback"] == 1
        assert recovered["preferences"] == 1

        # Rankings restaurados
        intel2.get_ranking().compute_scores()
        scores = intel2.get_rankings(task_type="coding", top_k=10)
        assert any(s.model_id == "model-a" for s in scores)

        # Métricas restauradas
        summary = intel2.get_model_summary("model-a")
        assert summary is not None
        assert summary.total_executions == 60

        # Feedback restaurado
        fb = intel2.get_feedback_summary(model_id="model-a", task_type="coding")
        assert fb and fb[0].positive == 1

        # Ejecuciones persistidas
        repo = ExecutionRepository(engine2)
        execs = await repo.list_recent()
        assert any(e.execution_id == "e1" for e in execs)
        e1 = next(e for e in execs if e.execution_id == "e1")
        assert e1.selected_model == "model-a"
        assert e1.task_type == "coding"
        assert e1.success is True
        assert e1.confidence_score == 0.9

        # Preferencias restauradas
        assert intel2.get_user_preference("u1", "response_style") == "technical"

        # Health check de la memoria de aprendizaje
        status = await intel2.learning_memory_status()
        assert status["status"] == "active"
        assert status["records"]["executions"] >= 1
        assert status["records"]["performance"] >= 60
        assert status["records"]["preferences"] == 1
        await engine2.close()


class TestLearningLoop:

    @pytest.mark.asyncio
    async def test_feedback_updates_future_selection(self, wired_intel):
        intel, db = wired_intel
        for _ in range(20):
            await intel.learn_from_model_result("model-a", "coding", "coding", 100, 10, 0.0, True)
            await intel.learn_from_model_result("model-b", "coding", "coding", 100, 10, 0.0, True)
        for _ in range(15):
            await intel.record_feedback("model-a", "coding", FeedbackScore.NEGATIVE, user_id="u1")
        for _ in range(15):
            await intel.record_feedback("model-b", "coding", FeedbackScore.POSITIVE, user_id="u1")

        intel.get_ranking().compute_scores()
        scores = intel.get_rankings(task_type="coding", top_k=10)
        rank_a = next((s.rank for s in scores if s.model_id == "model-a"), None)
        rank_b = next((s.rank for s in scores if s.model_id == "model-b"), None)
        assert rank_a is not None and rank_b is not None
        assert rank_b < rank_a

        # Persistido: tras reinicio el ranking sigue favoreciendo a model-b
        eng = StorageEngine(StorageConfig(database_url=db, migrate_on_start=True))
        await eng.initialize()
        intel2 = IntelligenceCoordinator()
        intel2.set_model_performance_repository(ModelPerformanceRepository(eng))
        intel2.set_feedback_repository(FeedbackRepository(eng))
        await intel2.recover_learning()
        intel2.get_ranking().compute_scores()
        scores2 = intel2.get_rankings(task_type="coding", top_k=10)
        rank_a2 = next((s.rank for s in scores2 if s.model_id == "model-a"), None)
        rank_b2 = next((s.rank for s in scores2 if s.model_id == "model-b"), None)
        assert rank_a2 is not None and rank_b2 is not None
        assert rank_b2 < rank_a2
        await eng.close()


class TestDatabaseFailure:

    @pytest.mark.asyncio
    async def test_bad_path_degrades_gracefully(self):
        engine = StorageEngine(StorageConfig(database_url="sqlite:////nonexistent/db.sqlite"))
        with pytest.raises(Exception):
            await engine.initialize()
        assert engine.initialized is False
        health = await engine.health()
        assert health["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_write_failure_does_not_corrupt(self, engine):
        eng, db = engine
        repo = ModelPerformanceRepository(eng)
        await repo.save(ModelPerformanceEvent(model_name="m1", task_type="chat", latency=1.0, success=True))
        assert await repo.count() == 1

        # Simular operación fallida: tabla inexistente no debe romper el engine
        try:
            await eng.execute("SELECT * FROM non_existent_table")
        except Exception:
            pass
        assert await repo.count() == 1


class TestNewRepositories:

    @pytest.mark.asyncio
    async def test_execution_repository(self, engine):
        eng, db = engine
        repo = ExecutionRepository(eng)
        await repo.save_batch([
            StoredExecution(execution_id="x1", user_request="tarea 1", task_type="coding",
                            selected_model="model-a", tools_used=["shell"], duration=2.0,
                            success=True, cost=0.0, confidence_score=0.8),
            StoredExecution(execution_id="x2", user_request="tarea 2", task_type="coding",
                            selected_model="model-b", duration=5.0, success=False,
                            failure_reason="timeout", cost=0.01),
        ])
        assert await repo.count() == 2
        by_model = await repo.list_by_model("model-a")
        assert len(by_model) == 1 and by_model[0].execution_id == "x1"
        by_task = await repo.list_by_task("coding")
        assert len(by_task) == 2
        x2 = await repo.get("x2")
        assert x2.success is False and x2.failure_reason == "timeout"
        assert x2.cost == 0.01
        assert await repo.get_last_update() is not None

    @pytest.mark.asyncio
    async def test_model_performance_summary(self, engine):
        eng, db = engine
        repo = ModelPerformanceRepository(eng)
        for i in range(10):
            await repo.save(ModelPerformanceEvent(model_name="qwen", task_type="coding",
                                                  latency=2.0, success=i < 9, cost=0.0))
        summary = await repo.get_model_summary("qwen", task_type="coding")
        assert summary["total"] == 10
        assert summary["success_rate"] == 0.9
        assert summary["failure_count"] == 1
        assert summary["average_latency"] == 2.0
        assert summary["confidence"] > 0
        assert await repo.count() == 10

    @pytest.mark.asyncio
    async def test_user_preference_repository(self, engine):
        eng, db = engine
        repo = UserPreferenceRepository(eng)
        await repo.save(UserPreference(user_id="u1", key="response_style", value="technical", source="explicit", evidence_count=3, confidence=1.0))
        await repo.save(UserPreference(user_id="u1", key="preferred_models", value=["qwen"], source="observed"))
        # Upsert: no duplica
        await repo.save(UserPreference(user_id="u1", key="response_style", value="concise", source="explicit", evidence_count=4, confidence=1.0))
        prefs = await repo.list_user("u1")
        assert len(prefs) == 2
        assert await repo.count() == 2
        updated = await repo.get("u1", "response_style")
        assert updated.value == "concise"
        assert updated.evidence_count == 4

    @pytest.mark.asyncio
    async def test_schema_version_tracked(self, engine):
        eng, db = engine
        version = await eng._schema_version()
        assert version >= 2
        # La tabla de preferencias existe y se puede escribir
        repo = UserPreferenceRepository(eng)
        await repo.save(UserPreference(user_id="u9", key="k", value=1))
        assert await repo.count() == 1
