import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock
import pytest

from sentinel.core.model_feedback import ModelFeedbackStore, TaskType
from sentinel.core.orchestrator import Orchestrator, TOOL_TO_TASK
from sentinel.core.planner import Planner
from sentinel.core.tool_gateway import ToolGateway
from sentinel.core.intent import Intent
from sentinel.core.model_router import ModelRouter, RouterDecision


@pytest.fixture(autouse=True)
def local_services_available_for_feedback_tests(monkeypatch):
    from sentinel.core.model_router import ProviderAvailability

    def availability(router, provider_id, refresh=False):
        provider = router._providers[provider_id]
        available = (not provider.requires_key) or router.has_api_key(provider_id)
        return ProviderAvailability(
            provider_id, available,
            "test_available" if available else "missing_api_key", 0.0,
        )

    monkeypatch.setattr(ModelRouter, "provider_availability", availability)


class TestModelFeedbackStore:
    def test_record_and_count(self):
        store = ModelFeedbackStore()
        assert store.total_records == 0
        store.record("ollama", "llama3", TaskType.QUICK, True, 150.0)
        assert store.total_records == 1

    def test_get_success_rate(self):
        store = ModelFeedbackStore()
        for _ in range(3):
            store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        store.record("ollama", "llama3", TaskType.QUICK, False, 200.0)
        rate = store.get_success_rate("ollama", TaskType.QUICK)
        assert rate == 0.75

    def test_get_success_rate_no_data(self):
        store = ModelFeedbackStore()
        rate = store.get_success_rate("ollama", TaskType.QUICK)
        assert rate == 0.0

    def test_get_avg_duration(self):
        store = ModelFeedbackStore()
        store.record("openrouter", "gpt-4o", TaskType.CODE, True, 500.0)
        store.record("openrouter", "gpt-4o", TaskType.CODE, True, 1500.0)
        avg = store.get_avg_duration("openrouter", TaskType.CODE)
        assert avg == 1000.0

    def test_get_avg_duration_no_data(self):
        store = ModelFeedbackStore()
        assert store.get_avg_duration("ollama", TaskType.QUICK) is None

    def test_get_stats_groups_by_provider_and_task(self):
        store = ModelFeedbackStore()
        store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        store.record("ollama", "llama3", TaskType.REASONING, False, 5000.0)
        store.record("openrouter", "gpt-4o", TaskType.REASONING, True, 800.0)
        stats = store.get_stats()
        assert len(stats) == 3
        sr_map = {(s.provider_id, s.task_type): s for s in stats}
        assert (s := sr_map.get(("openrouter", TaskType.REASONING))) and s.success_rate == 1.0
        assert (s := sr_map.get(("ollama", TaskType.REASONING))) and s.success_rate == 0.0

    def test_get_stats_filtered(self):
        store = ModelFeedbackStore()
        store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        store.record("ollama", "llama3", TaskType.REASONING, False, 5000.0)
        stats = store.get_stats(provider_id="ollama", task_type=TaskType.QUICK)
        assert len(stats) == 1
        assert stats[0].success_rate == 1.0

    def test_max_records_evicts_oldest(self):
        store = ModelFeedbackStore(max_records=3)
        for i in range(5):
            store.record("ollama", "llama3", TaskType.QUICK, True, float(i * 100))
        assert store.total_records == 3

    def test_success_rate_rounds_to_three_decimals(self):
        store = ModelFeedbackStore()
        for _ in range(3):
            store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        rate = store.get_success_rate("ollama", TaskType.QUICK)
        assert rate == 1.0


class TestOrchestratorRecordsFeedback:
    def test_feedback_recorded_after_step(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test"}
        router.select.return_value = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="mock",
        )

        store = ModelFeedbackStore()
        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
            model_feedback_store=store,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="query", target="system.cpu",
            parameters={}, confidence=0.9, raw_input="cpu",
        )

        import asyncio
        asyncio.run(orch.process("cpu", skip_simulation=True))

        assert store.total_records >= 1
        stats = store.get_stats()
        assert any(s.provider_id == "ollama" for s in stats)

    def test_feedback_records_failure_when_step_fails(self):
        router = MagicMock(spec=ModelRouter)
        router._key_map = {"ollama": "test"}
        router.select.return_value = RouterDecision(
            provider_id="ollama", model="llama3",
            task_type=TaskType.QUICK, strategy="priority",
            reason="mock",
        )

        store = ModelFeedbackStore()
        orch = Orchestrator(
            intent_engine=MagicMock(),
            tool_gateway=ToolGateway(),
            planner=Planner(),
            model_router=router,
            context_engine=None,
            memory=None,
            model_feedback_store=store,
        )
        orch._intent_engine.parse.return_value = Intent(
            action="query", target="system.cpu",
            parameters={}, confidence=0.9, raw_input="cpu",
        )

        import asyncio
        asyncio.run(orch.process("cpu", skip_simulation=True))

        stats = store.get_stats(provider_id="ollama", task_type=TaskType.QUICK)
        assert len(stats) == 1
        assert stats[0].total >= 1


class TestSmartSelectUsesFeedback:
    def test_high_success_rate_boosts_score(self):
        store = ModelFeedbackStore()
        for _ in range(10):
            store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        store.record("openrouter", "gpt-4o", TaskType.QUICK, False, 2000.0)

        router = ModelRouter(providers=[])
        router.set_feedback_store(store)

        from sentinel.core.model_router import ProviderSpec
        router._providers["ollama"] = ProviderSpec(
            id="ollama", name="Ollama",
            task_types=[TaskType.QUICK, TaskType.LOCAL],
            requires_key=False, is_local=True,
            default_model="llama3", priority=10,
        )
        router._providers["openrouter"] = ProviderSpec(
            id="openrouter", name="OpenRouter",
            task_types=[TaskType.QUICK, TaskType.REASONING, TaskType.CODE],
            requires_key=True, is_local=False,
            default_model="gpt-4o", priority=20,
        )
        router._key_map = {"openrouter": "sk-test"}
        router._strategy = "smart"

        decision = router.select(TaskType.QUICK, context={"permission_level": "admin"})
        assert decision.provider_id == "ollama"

    def test_low_success_rate_penalizes(self):
        store = ModelFeedbackStore()
        for _ in range(5):
            store.record("ollama", "llama3", TaskType.QUICK, False, 5000.0)
        for _ in range(5):
            store.record("openrouter", "gpt-4o", TaskType.QUICK, True, 500.0)

        router = ModelRouter(providers=[])
        router.set_feedback_store(store)

        from sentinel.core.model_router import ProviderSpec
        router._providers["ollama"] = ProviderSpec(
            id="ollama", name="Ollama",
            task_types=[TaskType.QUICK, TaskType.LOCAL],
            requires_key=False, is_local=True,
            default_model="llama3", priority=10,
        )
        router._providers["openrouter"] = ProviderSpec(
            id="openrouter", name="OpenRouter",
            task_types=[TaskType.QUICK, TaskType.REASONING, TaskType.CODE],
            requires_key=True, is_local=False,
            default_model="gpt-4o", priority=20,
        )
        router._key_map = {"openrouter": "sk-test"}
        router._strategy = "smart"

        decision = router.select(TaskType.QUICK, context={"permission_level": "admin"})
        assert decision.provider_id == "openrouter"

    def test_no_feedback_falls_back_to_normal_scoring(self):
        router = ModelRouter(providers=[])
        from sentinel.core.model_router import ProviderSpec
        router._providers["ollama"] = ProviderSpec(
            id="ollama", name="Ollama",
            task_types=[TaskType.QUICK, TaskType.LOCAL],
            requires_key=False, is_local=True,
            default_model="llama3", priority=30,
        )
        router._providers["openrouter"] = ProviderSpec(
            id="openrouter", name="OpenRouter",
            task_types=[TaskType.QUICK, TaskType.REASONING, TaskType.CODE],
            requires_key=True, is_local=False,
            default_model="gpt-4o", priority=20,
        )
        router._key_map = {"openrouter": "sk-test"}
        router._strategy = "smart"

        store = ModelFeedbackStore()
        router.set_feedback_store(store)

        decision = router.select(TaskType.QUICK, context={"permission_level": "admin"})
        assert decision.provider_id == "ollama"

class TestPersistence:
    def test_db_path_creates_sqlite_file(self, tmp_path):
        db = tmp_path / "test_feedback.db"
        store = ModelFeedbackStore(db_path=str(db))
        assert db.exists()
        store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        assert store.total_records == 1

    def test_records_survive_reinit(self, tmp_path):
        db = tmp_path / "survive.db"
        store1 = ModelFeedbackStore(db_path=str(db))
        store1.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        store1.record("openrouter", "gpt-4o", TaskType.CODE, False, 2500.0)
        assert store1.total_records == 2

        store2 = ModelFeedbackStore(db_path=str(db))
        assert store2.total_records == 2
        rate = store2.get_success_rate("ollama", TaskType.QUICK)
        assert rate == 1.0
        avg = store2.get_avg_duration("openrouter", TaskType.CODE)
        assert avg == 2500.0

    def test_mixed_memory_and_db(self, tmp_path):
        db = tmp_path / "mixed.db"
        store = ModelFeedbackStore(db_path=str(db))
        store.record("ollama", "llama3", TaskType.LOCAL, True, 50.0)
        assert store.total_records == 1

        store2 = ModelFeedbackStore(db_path=str(db))
        assert store2.total_records == 1
        store2.record("openrouter", "gpt-4o", TaskType.REASONING, True, 800.0)
        assert store2.total_records == 2

        store3 = ModelFeedbackStore(db_path=str(db))
        assert store3.total_records == 2

    def test_in_memory_fallback_when_no_db_path(self):
        store = ModelFeedbackStore()
        store.record("ollama", "llama3", TaskType.QUICK, True, 100.0)
        assert store.total_records == 1
        assert store.get_success_rate("ollama", TaskType.QUICK) == 1.0

    def test_max_records_still_works_with_db(self, tmp_path):
        db = tmp_path / "max.db"
        store = ModelFeedbackStore(max_records=3, db_path=str(db))
        for i in range(5):
            store.record("ollama", "llama3", TaskType.QUICK, True, float(i * 100))
        assert store.total_records == 3
