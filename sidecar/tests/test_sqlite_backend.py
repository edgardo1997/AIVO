import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, PropertyMock, call, ANY
from datetime import datetime, timezone
from dataclasses import dataclass

from sentinel.core.operational_memory import (
    SQLiteBackend,
    ExecutionRecord,
    PendingActionRecord,
    EpisodicMemory,
    MemoryPattern,
    LearnedPreference,
    OperationalMemoryConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_db():
    """Create a mocked DatabaseManager that stores data in a real SQLite
    in-memory database for each test."""
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS execution_history (
            execution_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            utterance TEXT DEFAULT '',
            intent TEXT DEFAULT '{}',
            plan TEXT DEFAULT '{}',
            decision TEXT,
            context_summary TEXT DEFAULT '{}',
            step_results TEXT DEFAULT '[]',
            tool_result TEXT,
            error TEXT,
            duration_ms REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS pending_actions (
            action_id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            params TEXT DEFAULT '{}',
            reason TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            ttl_seconds INTEGER DEFAULT 600,
            confirmed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_preferences (
            session_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (session_id, key)
        );
        CREATE TABLE IF NOT EXISTS episodic_memory (
            memory_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            execution_id TEXT NOT NULL UNIQUE,
            occurred_at TEXT NOT NULL,
            summary TEXT NOT NULL,
            intent_action TEXT DEFAULT '',
            intent_target TEXT DEFAULT '',
            tool_id TEXT DEFAULT '',
            outcome TEXT NOT NULL,
            risk_score REAL,
            tags TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS memory_patterns (
            pattern_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            UNIQUE(user_id, pattern_type, pattern_key)
        );
        CREATE TABLE IF NOT EXISTS learned_preferences (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        CREATE TABLE IF NOT EXISTS emergency_stop (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            value INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO emergency_stop (id, value) VALUES (1, 0);
    """)
    conn.commit()

    db = MagicMock()
    db._conn = conn

    def _execute(sql, params=()):
        return conn.execute(sql, params)

    def _fetchone(sql, params=()):
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def _fetchall(sql, params=()):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    db.execute.side_effect = _execute
    db.fetchone.side_effect = _fetchone
    db.fetchall.side_effect = _fetchall
    db.commit = MagicMock(side_effect=lambda: conn.commit())
    return db


def make_record(exec_id="e1", session="sess1", error=None):
    return ExecutionRecord(
        execution_id=exec_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        utterance="test",
        intent={"action": "query", "target": "info"},
        plan={"steps": [], "description": "test"},
        decision={"decision": "approve"},
        context_summary={"session_id": session},
        step_results=[{"step_id": "s0"}],
        tool_result={"success": True, "tool_id": "info"},
        error=error,
        duration_ms=100.0,
    )


def make_pending(aid="pa1"):
    return PendingActionRecord(
        action_id=aid,
        tool_id="sys.info",
        params={"cmd": "test"},
        reason="needs approval",
        created_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=600,
    )


# ===================================================================
# Execution Records
# ===================================================================


class TestSQLiteExecutionRecords:
    def test_store_and_get(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        rec = make_record("e1")
        bk.store_execution(rec)
        got = bk.get_execution("e1")
        assert got is not None
        assert got.execution_id == "e1"
        assert got.utterance == "test"
        assert got.intent["action"] == "query"
        assert got.duration_ms == 100.0

    def test_store_and_get_last(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_execution(make_record("e1"))
        bk.store_execution(make_record("e2"))
        last = bk.get_last_execution()
        assert last is not None
        assert last.execution_id == "e2"

    def test_get_recent(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_execution(make_record("e1"))
        bk.store_execution(make_record("e2"))
        bk.store_execution(make_record("e3"))
        recent = bk.get_recent_executions(limit=2)
        assert len(recent) == 2
        assert recent[0].execution_id == "e3"
        assert recent[1].execution_id == "e2"

    def test_get_session_history(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_execution(make_record("e1", session="sessA"))
        bk.store_execution(make_record("e2", session="sessB"))
        bk.store_execution(make_record("e3", session="sessA"))
        history = bk.get_session_history("sessA")
        assert len(history) == 2
        assert history[0].execution_id == "e3"  # latest first
        assert history[1].execution_id == "e1"

    def test_get_session_history_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        history = bk.get_session_history("unknown")
        assert history == []

    def test_update_execution(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_execution(make_record("e1"))
        bk.update_execution("e1", duration_ms=999.0)
        got = bk.get_execution("e1")
        assert got.duration_ms == 999.0

    def test_get_nonexistent(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_execution("noexist") is None

    def test_get_last_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_last_execution() is None

    def test_get_recent_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_recent_executions() == []


# ===================================================================
# Pending Actions
# ===================================================================


class TestSQLitePendingActions:
    def test_store_and_get(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        pa = make_pending("pa1")
        bk.store_pending_action(pa)
        got = bk.get_pending_action("pa1")
        assert got is not None
        assert got.action_id == "pa1"
        assert got.tool_id == "sys.info"
        assert got.params["cmd"] == "test"

    def test_remove_pending(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_pending_action(make_pending("pa1"))
        removed = bk.remove_pending_action("pa1")
        assert removed is not None
        assert removed.action_id == "pa1"
        assert bk.get_pending_action("pa1") is None

    def test_remove_nonexistent(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.remove_pending_action("noexist") is None

    def test_get_nonexistent(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_pending_action("noexist") is None

    def test_list_pending(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_pending_action(make_pending("pa1"))
        bk.store_pending_action(make_pending("pa2"))
        all_pa = bk.list_pending_actions()
        assert len(all_pa) == 2

    def test_list_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.list_pending_actions() == []


# ===================================================================
# User Preferences
# ===================================================================


class TestSQLiteUserPreferences:
    def test_store_and_get(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_user_preference("sess1", "theme", "dark")
        prefs = bk.get_user_preferences("sess1")
        assert prefs["theme"] == "dark"

    def test_overwrite(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_user_preference("sess1", "theme", "dark")
        bk.store_user_preference("sess1", "theme", "light")
        prefs = bk.get_user_preferences("sess1")
        assert prefs["theme"] == "light"

    def test_get_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_user_preferences("noexist") == {}

    def test_multiple_sessions(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_user_preference("sess1", "theme", "dark")
        bk.store_user_preference("sess2", "theme", "light")
        assert bk.get_user_preferences("sess1")["theme"] == "dark"
        assert bk.get_user_preferences("sess2")["theme"] == "light"


# ===================================================================
# Episodic Memory
# ===================================================================


class TestSQLiteEpisodicMemory:
    def test_remember_and_get(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        rec = make_record("e1", session="sess1")
        episode = bk.remember_execution("user1", rec)
        assert episode is not None
        assert episode.user_id == "user1"
        assert episode.execution_id == "e1"
        assert episode.outcome == "succeeded"

    def test_get_episodes(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.remember_execution("user1", make_record("e1"))
        bk.remember_execution("user1", make_record("e2"))
        bk.remember_execution("user2", make_record("e3"))
        episodes = bk.get_episodes("user1")
        assert len(episodes) == 2
        assert all(e.user_id == "user1" for e in episodes)

    def test_get_episodes_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_episodes("nobody") == []

    def test_remember_no_user(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.remember_execution("", make_record("e1")) is None

    def test_outcome_failed_when_error(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        rec = make_record("e_err", error="oops")
        episode = bk.remember_execution("user1", rec)
        assert episode.outcome == "failed"


# ===================================================================
# Memory Patterns
# ===================================================================


class TestSQLiteMemoryPatterns:
    def test_pattern_generated_from_episode(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        rec = make_record("e1")
        bk.remember_execution("user1", rec)
        patterns = bk.get_patterns("user1", min_evidence=1)
        assert len(patterns) >= 1
        assert patterns[0].user_id == "user1"

    def test_pattern_evidence_increments(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.remember_execution("user1", make_record("e1"))
        bk.remember_execution("user1", make_record("e2"))
        patterns = bk.get_patterns("user1", min_evidence=1)
        # first pattern should have evidence_count=2
        assert patterns[0].evidence_count == 2

    def test_patterns_filtered_by_min_evidence(self):
        db = make_db()
        bk = SQLiteBackend(db=db, config=OperationalMemoryConfig(pattern_min_evidence=3))
        bk.remember_execution("user1", make_record("e1"))
        patterns = bk.get_patterns("user1")
        assert len(patterns) == 0

    def test_get_patterns_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_patterns("nobody") == []


# ===================================================================
# Learned Preferences
# ===================================================================


class TestSQLiteLearnedPreferences:
    def test_learn_and_get(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        pref = bk.learn_preference("user1", "speed", "fast", source="explicit")
        assert pref.key == "speed"
        assert pref.value == "fast"
        assert pref.source == "explicit"
        assert pref.evidence_count == 1

    def test_learn_explicit_sets_confidence_1(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        pref = bk.learn_preference("user1", "detail", "high", source="explicit")
        assert pref.confidence == 1.0

    def test_learn_observed_increments_confidence(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        pref1 = bk.learn_preference("user1", "mode", "silent", source="observed")
        assert pref1.confidence == 0.6  # 0.5 + 0.1
        pref2 = bk.learn_preference("user1", "mode", "silent", source="observed")
        assert pref2.evidence_count == 2
        assert pref2.confidence == 0.7

    def test_get_learned(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.learn_preference("user1", "a", 1, source="explicit")
        bk.learn_preference("user1", "b", 2, source="observed")
        prefs = bk.get_learned_preferences("user1")
        assert len(prefs) == 2
        assert prefs["a"].value == 1
        assert prefs["b"].value == 2

    def test_get_learned_empty(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_learned_preferences("nobody") == {}

    def test_invalid_key_raises(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        with pytest.raises(ValueError):
            bk.learn_preference("user1", "permission.x", True)

    def test_invalid_source_raises(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        with pytest.raises(ValueError):
            bk.learn_preference("user1", "speed", "fast", source="unknown")


# ===================================================================
# Emergency Stop
# ===================================================================


class TestSQLiteEmergencyStop:
    def test_default_is_false(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        assert bk.get_emergency_stop() is False

    def test_set_true(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.set_emergency_stop(True)
        assert bk.get_emergency_stop() is True

    def test_toggle(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.set_emergency_stop(True)
        bk.set_emergency_stop(False)
        assert bk.get_emergency_stop() is False


# ===================================================================
# Clear
# ===================================================================


class TestSQLiteClear:
    def test_clear_removes_all(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.store_execution(make_record("e1"))
        bk.store_pending_action(make_pending("pa1"))
        bk.store_user_preference("s1", "k", "v")
        bk.learn_preference("u1", "k", "v", source="explicit")
        bk.set_emergency_stop(True)
        bk.clear()
        assert bk.get_execution("e1") is None
        assert bk.get_pending_action("pa1") is None
        assert bk.get_user_preferences("s1") == {}
        assert bk.get_learned_preferences("u1") == {}
        assert bk.get_emergency_stop() is False


# ===================================================================
# Close
# ===================================================================


class TestSQLiteClose:
    def test_close_does_not_raise(self):
        db = make_db()
        bk = SQLiteBackend(db=db)
        bk.close()  # should not raise
