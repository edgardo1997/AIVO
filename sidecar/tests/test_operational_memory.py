import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
import time

import pytest
from sentinel.core.operational_memory import (
    InMemoryBackend,
    ExecutionRecord,
    PendingActionRecord,
    OperationalMemoryConfig,
)


def _make_record(execution_id="test-1", utterance="test", timestamp=None, duration=0.0):
    from datetime import datetime, timezone
    ts = timestamp or (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return ExecutionRecord(
        execution_id=execution_id,
        timestamp=ts,
        utterance=utterance,
        intent={"action": "query", "target": "system.info"},
        plan={"risk_score": 0.3, "steps": []},
        decision=None,
        context_summary={},
        step_results=[],
        tool_result=None,
        error=None,
        duration_ms=duration,
    )


class TestStoreAndRetrieve:
    def test_store_execution(self):
        mem = InMemoryBackend()
        rec = _make_record()
        mem.store_execution(rec)
        retrieved = mem.get_execution("test-1")
        assert retrieved is not None
        assert retrieved.utterance == "test"
        assert retrieved.execution_id == "test-1"

    def test_get_last_execution(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("a", "first"))
        mem.store_execution(_make_record("b", "second"))
        last = mem.get_last_execution()
        assert last is not None
        assert last.execution_id == "b"

    def test_get_last_execution_empty(self):
        mem = InMemoryBackend()
        assert mem.get_last_execution() is None

    def test_get_execution_by_id(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("find-me"))
        retrieved = mem.get_execution("find-me")
        assert retrieved is not None
        assert retrieved.execution_id == "find-me"

    def test_get_nonexistent(self):
        mem = InMemoryBackend()
        assert mem.get_execution("nope") is None

    def test_clear(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("a"))
        mem.clear()
        assert mem.get_execution("a") is None
        assert mem.get_last_execution() is None


class TestPersistentSessions:
    @staticmethod
    def session_record(execution_id, user_id, session_id, utterance):
        record = _make_record(execution_id, utterance)
        record.context_summary = {"user_id": user_id, "session_id": session_id}
        return record

    def test_sessions_are_listed_and_searched_per_user(self):
        mem = InMemoryBackend()
        mem.store_execution(self.session_record("a", "alice", "session-a", "generate quarterly report"))
        mem.store_execution(self.session_record("b", "bob", "session-b", "private bob instruction"))

        sessions = mem.list_sessions("alice")
        results = mem.search_memory("alice", "quarterly")

        assert [item["session_id"] for item in sessions] == ["session-a"]
        assert [item.execution_id for item in results] == ["a"]
        assert mem.search_memory("alice", "bob") == []

    def test_delete_session_is_owned_and_complete(self):
        mem = InMemoryBackend()
        mem.store_execution(self.session_record("a", "alice", "shared-name", "alice data"))
        mem.store_execution(self.session_record("b", "bob", "shared-name", "bob data"))
        mem.store_user_preference("shared-name", "tone", "brief")

        deleted = mem.delete_session("shared-name", "alice")

        assert deleted == 1
        assert mem.get_execution("a") is None
        assert mem.get_execution("b") is not None
        assert mem.list_sessions("alice") == []


class TestFIFOEviction:
    def test_fifo_eviction(self):
        config = OperationalMemoryConfig(max_records=3)
        mem = InMemoryBackend(config)
        mem.store_execution(_make_record("r1"))
        mem.store_execution(_make_record("r2"))
        mem.store_execution(_make_record("r3"))
        mem.store_execution(_make_record("r4"))
        assert mem.get_execution("r1") is None
        assert mem.get_execution("r2") is not None
        assert mem.get_execution("r4") is not None

    def test_fifo_keeps_correct_count(self):
        config = OperationalMemoryConfig(max_records=5)
        mem = InMemoryBackend(config)
        for i in range(10):
            mem.store_execution(_make_record(f"r{i}"))
        recent = mem.get_recent_executions(10)
        assert len(recent) == 5

    def test_update_does_not_change_order(self):
        config = OperationalMemoryConfig(max_records=2)
        mem = InMemoryBackend(config)
        mem.store_execution(_make_record("r1"))
        mem.store_execution(_make_record("r2"))
        mem.update_execution("r1", utterance="updated")
        mem.store_execution(_make_record("r3"))
        assert mem.get_execution("r1") is None
        assert mem.get_execution("r2") is not None


class TestUpdateExecution:
    def test_update_fields(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("u1", duration=0.0))
        mem.update_execution("u1", duration_ms=150.0, error="oops")
        rec = mem.get_execution("u1")
        assert rec is not None
        assert rec.duration_ms == 150.0
        assert rec.error == "oops"

    def test_update_unknown_does_nothing(self):
        mem = InMemoryBackend()
        mem.update_execution("nonexistent", error="fail")  # should not raise


class TestRecentExecutions:
    def test_get_recent(self):
        mem = InMemoryBackend()
        for i in range(5):
            mem.store_execution(_make_record(f"r{i}"))
        recent = mem.get_recent_executions(3)
        assert len(recent) == 3
        assert recent[0].execution_id == "r2"
        assert recent[-1].execution_id == "r4"

    def test_get_recent_more_than_stored(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("only"))
        recent = mem.get_recent_executions(10)
        assert len(recent) == 1


class TestPendingActions:
    def test_store_and_retrieve(self):
        mem = InMemoryBackend()
        rec = PendingActionRecord(
            action_id="pa-1", tool_id="executor.command",
            params={"command": "test"}, reason="high risk",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        )
        mem.store_pending_action(rec)
        assert mem.get_pending_action("pa-1") is not None

    def test_remove_pending_action(self):
        mem = InMemoryBackend()
        mem.store_pending_action(PendingActionRecord(
            action_id="pa-2", tool_id="executor.kill",
            params={}, reason="test",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        ))
        removed = mem.remove_pending_action("pa-2")
        assert removed is not None
        assert mem.get_pending_action("pa-2") is None

    def test_list_pending_actions(self):
        mem = InMemoryBackend()
        mem.store_pending_action(PendingActionRecord(
            action_id="pa-a", tool_id="executor.command",
            params={}, reason="a",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        ))
        mem.store_pending_action(PendingActionRecord(
            action_id="pa-b", tool_id="executor.kill",
            params={}, reason="b",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        ))
        actions = mem.list_pending_actions()
        assert len(actions) == 2

    def test_pending_action_limit(self):
        config = OperationalMemoryConfig(max_pending_actions=2)
        mem = InMemoryBackend(config)
        mem.store_pending_action(PendingActionRecord(
            action_id="pa-1", tool_id="executor.command",
            params={}, reason="r1",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        ))
        mem.store_pending_action(PendingActionRecord(
            action_id="pa-2", tool_id="executor.kill",
            params={}, reason="r2",
            created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
        ))
        with pytest.raises(RuntimeError, match="Pending action limit"):
            mem.store_pending_action(PendingActionRecord(
                action_id="pa-3", tool_id="system.info",
                params={}, reason="r3",
                created_at="2026-01-01T00:00:00Z", ttl_seconds=600,
            ))


class TestThreadSafety:
    def test_concurrent_store(self):
        mem = InMemoryBackend()
        errors = []

        def writer(prefix, count):
            try:
                for i in range(count):
                    mem.store_execution(_make_record(f"{prefix}-{i}"))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("A", 50)),
            threading.Thread(target=writer, args=("B", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent store: {errors}"
        recent = mem.get_recent_executions(200)
        assert len(recent) <= 50

    def test_concurrent_read_write(self):
        mem = InMemoryBackend()
        errors = []

        def writer():
            for i in range(20):
                try:
                    mem.store_execution(_make_record(f"w{i}"))
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(20):
                try:
                    mem.get_last_execution()
                    mem.get_recent_executions(10)
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent read/write: {errors}"


class TestClose:
    def test_close_stops_eviction(self):
        mem = InMemoryBackend()
        mem.store_execution(_make_record("keep"))
        mem.close()
        assert mem.get_execution("keep") is not None


class TestConfigDefault:
    def test_default_ttl(self):
        config = OperationalMemoryConfig()
        assert config.execution_ttl == 300
        assert config.max_records == 50
        assert config.pending_action_ttl == 600
        assert config.max_pending_actions == 100
