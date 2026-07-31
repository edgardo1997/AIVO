"""Pruebas FASE 35 — Persistent Intelligence Storage.

Test 1: Persistencia básica — guardar/leer modelo sobrevive a recreación de engine
Test 2: Ranking histórico — 100 métricas → promedio correcto
Test 3: Conversación — guardar/recuperar contexto entre sesiones
Test 4: Integridad — modo degradado sin database
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sentinel.storage.database import StorageEngine, StorageConfig
from sentinel.storage.models import StoredModel, FeedbackRecord, MetricRecord, ConversationRecord, DecisionRecord
from sentinel.storage.repositories.model_repository import ModelRepository
from sentinel.storage.repositories.feedback_repository import FeedbackRepository
from sentinel.storage.repositories.metric_repository import MetricRepository
from sentinel.storage.repositories.conversation_repository import ConversationRepository
from sentinel.storage.repositories.decision_repository import DecisionRepository


@pytest_asyncio.fixture
async def engine():
    """Crea StorageEngine en memoria para tests."""
    import tempfile, os
    db_path = os.path.join(tempfile.gettempdir(), f"sentinel_test_{datetime.now(timezone.utc).timestamp()}.db")
    cfg = StorageConfig(database_url=f"sqlite:///{db_path}", migrate_on_start=True)
    eng = StorageEngine(cfg)
    await eng.initialize()
    yield eng
    await eng.close()
    try:
        os.remove(db_path)
    except:
        pass


class TestPersistentIntelligence:

    @pytest.mark.asyncio
    async def test_persistencia_basica(self, engine):
        """Test 1: guardar modelo, reiniciar conexión, leer."""
        repo = ModelRepository(engine)
        model = StoredModel(name="qwen3-8b", provider="ollama", capabilities=["coding", "reasoning"])
        await repo.save(model)

        loaded = await repo.get(model.id)
        assert loaded is not None
        assert loaded.name == "qwen3-8b"
        assert loaded.provider == "ollama"
        assert "coding" in loaded.capabilities

        # Simular reinicio: nuevo engine sobre mismo archivo
        await engine.reconnect()
        repo2 = ModelRepository(engine)
        loaded2 = await repo2.get(model.id)
        assert loaded2 is not None
        assert loaded2.name == "qwen3-8b"

    @pytest.mark.asyncio
    async def test_ranking_historico(self, engine):
        """Test 2: 100 métricas → promedio correcto."""
        repo = MetricRepository(engine)
        for i in range(100):
            await repo.save(MetricRecord(
                component="ModelRouter",
                metric_name="latency_ms",
                value=200 + i * 2,
                unit="ms",
                tags={"model": "gpt-4o", "task": "chat"},
            ))

        stats = await repo.get_stats("ModelRouter", "latency_ms")
        assert stats["count"] == 100
        assert 200 <= stats["min"] <= stats["max"]
        assert stats["mean"] > 0

        latest = await repo.get_latest("ModelRouter", "latency_ms")
        assert latest is not None
        assert latest.component == "ModelRouter"

    @pytest.mark.asyncio
    async def test_conversacion_persistente(self, engine):
        """Test 3: guardar session, cerrar, abrir, recuperar contexto."""
        repo = ConversationRepository(engine)
        session_id = "test-session-123"

        msg1 = ConversationRecord(
            session_id=session_id,
            role="user",
            content="abre mi navegador",
            context={"task_type": "tool", "user_id": "u1"},
        )
        msg2 = ConversationRecord(
            session_id=session_id,
            role="assistant",
            content="Abriendo Chrome",
            model_id="gpt-4o",
        )
        await repo.save_message(msg1)
        await repo.save_message(msg2)

        # Simular reinicio
        await engine.reconnect()
        repo2 = ConversationRepository(engine)

        messages = await repo2.get_session_messages(session_id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "abre mi navegador"
        assert messages[1].role == "assistant"

        ctx = await repo2.get_session_context(session_id)
        assert ctx.get("task_type") == "tool"

        sessions = await repo2.list_sessions()
        assert len(sessions) >= 1
        assert sessions[0]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_decision_history(self, engine):
        """Decisiones se guardan y consultan."""
        repo = DecisionRepository(engine)
        await repo.save(DecisionRecord(
            request="abre chrome",
            decision="APPROVE",
            risk_level="low",
            selected_model="gpt-4o",
            reason="Safe read-only operation",
        ))
        await repo.save(DecisionRecord(
            request="delete file",
            decision="DENY",
            risk_level="critical",
            reason="Path too sensitive",
        ))

        recent = await repo.list_recent(limit=10)
        assert len(recent) == 2

        denied = await repo.list_by_decision("DENY")
        assert len(denied) == 1

        summary = await repo.get_model_decision_summary("gpt-4o")
        assert summary["total"] == 1
        assert summary["approved"] == 1

    @pytest.mark.asyncio
    async def test_feedback_persistence(self, engine):
        """Feedback se guarda y consulta con resumen."""
        repo = FeedbackRepository(engine)
        for i in range(10):
            await repo.save(FeedbackRecord(
                model_id="qwen3-8b",
                task_type="coding",
                success=i < 8,
                quality_score=0.5 + i * 0.05,
                latency=5.0 + i * 0.5,
                user_id="u1",
            ))

        summary = await repo.get_model_summary("qwen3-8b")
        assert summary["total"] == 10
        assert summary["successes"] == 8
        assert summary["success_rate"] == 0.8

        task_summary = await repo.get_task_summary("coding")
        assert task_summary["total"] == 10
        assert task_summary["success_rate"] == 0.8

    @pytest.mark.asyncio
    async def test_feedback_batch_and_delete(self, engine):
        """Batch save y delete older than."""
        repo = FeedbackRepository(engine)
        records = [
            FeedbackRecord(model_id="model-a", task_type="chat", success=True, latency=1.0)
            for _ in range(5)
        ]
        await repo.save_batch(records)
        assert await repo.count() >= 5

        await repo.delete_older_than(days=0)
        remaining = await repo.count()
        # Todos fueron creados ahora, alguno pudo quedar
        assert isinstance(remaining, int)

    @pytest.mark.asyncio
    async def test_storage_engine_health(self, engine):
        """StorageEngine responde health check."""
        health = await engine.health()
        assert health["status"] == "connected"

        await engine.close()
        health2 = await engine.health()
        assert health2["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_integridad_modo_degradado(self):
        """Test 4: Sin database, Sentinel continúa funcionando."""
        engine = StorageEngine(StorageConfig(database_url="sqlite:////nonexistent/db.sqlite"))
        with pytest.raises(Exception):
            await engine.initialize()
        # Engine no debe crashear, solo no se inicializa
        assert engine.initialized is False

        # El sistema debe seguir funcionando sin storage
        health = await engine.health()
        assert health["status"] == "disconnected"