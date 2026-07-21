import json
import sqlite3

from sentinel.core.operational_memory import SQLiteBackend


class _RecordingDatabase:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.fetchall_calls = 0
        self.fetchone_calls = 0
        self.connection.execute(
            """CREATE TABLE execution_history (
                   execution_id TEXT PRIMARY KEY,
                   timestamp TEXT NOT NULL,
                   utterance TEXT NOT NULL,
                   context_summary TEXT NOT NULL
               )"""
        )

    def execute(self, sql, params=()):
        return self.connection.execute(sql, params)

    def fetchall(self, sql, params=()):
        self.fetchall_calls += 1
        return [dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def fetchone(self, sql, params=()):
        self.fetchone_calls += 1
        row = self.connection.execute(sql, params).fetchone()
        return dict(row) if row else None


def test_sqlite_list_sessions_uses_one_query_and_preserves_contract():
    db = _RecordingDatabase()
    rows = (
        ("a-1", "2026-01-01T00:00:00Z", "alpha first", "user-a", "alpha"),
        ("a-2", "2026-01-03T00:00:00Z", "alpha latest", "user-a", "alpha"),
        ("b-1", "2026-01-04T00:00:00Z", "beta latest", "user-a", "beta"),
        ("other", "2026-01-05T00:00:00Z", "not visible", "user-b", "alpha"),
    )
    for execution_id, timestamp, utterance, user_id, session_id in rows:
        db.execute(
            "INSERT INTO execution_history VALUES (?, ?, ?, ?)",
            (
                execution_id,
                timestamp,
                utterance,
                json.dumps({"user_id": user_id, "session_id": session_id}),
            ),
        )

    sessions = SQLiteBackend(db=db).list_sessions("user-a", limit=50)

    assert sessions == [
        {
            "session_id": "beta",
            "created_at": "2026-01-04T00:00:00Z",
            "updated_at": "2026-01-04T00:00:00Z",
            "execution_count": 1,
            "last_utterance": "beta latest",
        },
        {
            "session_id": "alpha",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-03T00:00:00Z",
            "execution_count": 2,
            "last_utterance": "alpha latest",
        },
    ]
    assert db.fetchall_calls == 1
    assert db.fetchone_calls == 0
