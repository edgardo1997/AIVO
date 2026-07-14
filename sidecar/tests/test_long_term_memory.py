import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.operational_memory import ExecutionRecord, InMemoryBackend, SQLiteBackend


def _record(execution_id: str, target: str = "system.cpu", error=None):
    return ExecutionRecord(
        execution_id=execution_id,
        timestamp="2026-07-12T12:00:00Z",
        utterance="show cpu usage",
        intent={"action": "query", "target": target},
        plan={"risk_score": 0.2, "steps": []},
        decision=None,
        context_summary={},
        step_results=[],
        tool_result={"tool_id": target, "success": error is None},
        error=error,
        duration_ms=12.5,
    )


class TestLongTermMemory:
    def test_episode_is_user_scoped_and_summarized(self):
        memory = InMemoryBackend()
        episode = memory.remember_execution("user-a", _record("exec-1"))
        assert episode is not None
        assert episode.outcome == "succeeded"
        assert "system.cpu" in episode.summary
        assert len(memory.get_episodes("user-a")) == 1
        assert memory.get_episodes("user-b") == []

    def test_repeated_executions_create_advisory_pattern(self):
        memory = InMemoryBackend()
        for index in range(3):
            memory.remember_execution("user-a", _record(f"exec-{index}"))
        patterns = memory.get_patterns("user-a")
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "intent_target"
        assert patterns[0].pattern_key == "system.cpu"
        assert patterns[0].evidence_count == 3

    def test_preferences_cannot_control_security_or_execution(self):
        memory = InMemoryBackend()
        memory.learn_preference("user-a", "display.units", "metric")
        assert memory.get_learned_preferences("user-a")["display.units"].value == "metric"
        import pytest

        with pytest.raises(ValueError, match="cannot control"):
            memory.learn_preference("user-a", "policy.default_effect", "allow")

    def test_sqlite_memory_persists_episodes_patterns_and_preferences(self):
        from repositories.database import DatabaseManager

        memory = SQLiteBackend(DatabaseManager())
        for index in range(3):
            memory.remember_execution("user-memory", _record(f"sqlite-{index}"))
        memory.learn_preference("user-memory", "display.units", "metric", source="observed")
        assert len(memory.get_episodes("user-memory")) == 3
        assert memory.get_patterns("user-memory")[0].evidence_count == 3
        assert memory.get_learned_preferences("user-memory")["display.units"].source == "observed"
