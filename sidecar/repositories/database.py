import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager

SENTINEL_DATA_DIR = os.path.abspath(os.path.expanduser("~/.sentinel"))
SENTINEL_PRODUCTION_DB_PATH = os.path.join(SENTINEL_DATA_DIR, "sentinel.db")
LEGACY_PRODUCTION_DB_PATH = os.path.abspath(os.path.expanduser("~/.aivo.db"))
PRODUCTION_DB_PATH = SENTINEL_PRODUCTION_DB_PATH


def _normalize_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def resolve_database_path() -> str:
    """Resolve the active SQLite path with Sentinel-first precedence."""
    explicit = os.environ.get("SENTINEL_DB_PATH")
    if explicit:
        return _normalize_path(explicit)
    legacy_explicit = os.environ.get("AIVO_DB_PATH")
    if legacy_explicit:
        return _normalize_path(legacy_explicit)
    return SENTINEL_PRODUCTION_DB_PATH


DB_PATH = resolve_database_path()


def migrate_legacy_database(
    target_path: str = DB_PATH,
    legacy_path: str = LEGACY_PRODUCTION_DB_PATH,
) -> bool:
    """Copy the legacy AIVO database to Sentinel storage once.

    The legacy database is never deleted or modified. If the Sentinel database
    already exists, migration is skipped to avoid overwriting newer data.
    """
    target = _normalize_path(target_path)
    legacy = _normalize_path(legacy_path)
    if target == legacy or os.path.exists(target) or not os.path.exists(legacy):
        return False
    target_dir = os.path.dirname(target)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)
    shutil.copy2(legacy, target)
    for suffix in ("-wal", "-shm"):
        legacy_sidecar = f"{legacy}{suffix}"
        target_sidecar = f"{target}{suffix}"
        if os.path.exists(legacy_sidecar) and not os.path.exists(target_sidecar):
            shutil.copy2(legacy_sidecar, target_sidecar)
    return True


def _assert_safe_database_path(db_path: str) -> None:
    """Fail closed if a test process attempts to open the production database."""
    if os.environ.get("AIVO_TESTING") != "1":
        return
    candidate = os.path.normcase(_normalize_path(db_path))
    protected_paths = {
        os.path.normcase(SENTINEL_PRODUCTION_DB_PATH),
        os.path.normcase(LEGACY_PRODUCTION_DB_PATH),
    }
    if candidate in protected_paths:
        raise RuntimeError(
            "Refusing to open the production database while AIVO_TESTING=1. "
            "Set SENTINEL_DB_PATH to an isolated test database."
        )

class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(db_path or DB_PATH)
        return cls._instance

    def _init(self, db_path: str):
        _assert_safe_database_path(db_path)
        migrate_legacy_database(db_path)
        self.db_path = _normalize_path(db_path)
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._create_schema()
        self._protect_database_files()

    def _protect_database_files(self):
        from windows_acl import protect_path
        for candidate in (self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"):
            if os.path.exists(candidate):
                protect_path(candidate, directory=False)

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._protect_database_files()
        return self._local.conn

    def _create_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action    TEXT NOT NULL,
                details   TEXT DEFAULT '',
                status    TEXT DEFAULT 'info',
                user      TEXT DEFAULT 'local'
            );

            CREATE TABLE IF NOT EXISTS execution_history (
                execution_id TEXT PRIMARY KEY,
                timestamp    TEXT NOT NULL,
                utterance    TEXT DEFAULT '',
                intent       TEXT DEFAULT '{}',
                plan         TEXT DEFAULT '{}',
                decision     TEXT,
                context_summary TEXT DEFAULT '{}',
                step_results TEXT DEFAULT '[]',
                tool_result  TEXT,
                error        TEXT,
                duration_ms  REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS pending_actions (
                action_id   TEXT PRIMARY KEY,
                tool_id     TEXT NOT NULL,
                params      TEXT DEFAULT '{}',
                reason      TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                ttl_seconds INTEGER DEFAULT 600,
                confirmed   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS emergency_stop (
                id    INTEGER PRIMARY KEY CHECK (id = 1),
                value INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS agents (
                agent_id    TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                provider    TEXT DEFAULT 'ollama',
                model       TEXT DEFAULT '',
                capabilities TEXT DEFAULT '[]',
                allowed_tools TEXT DEFAULT '[]',
                system_prompt TEXT DEFAULT '',
                status      TEXT DEFAULT 'idle',
                max_concurrency INTEGER DEFAULT 1,
                config      TEXT DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fleet (
                plugin_id TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                enabled   INTEGER DEFAULT 1,
                config    TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS triggers (
                trigger_id      TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                conditions      TEXT NOT NULL DEFAULT '[]',
                action          TEXT,
                cooldown_seconds INTEGER DEFAULT 300,
                enabled         INTEGER DEFAULT 1,
                last_fired      REAL,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trigger_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_id      TEXT NOT NULL,
                condition_met   INTEGER NOT NULL DEFAULT 0,
                action_executed INTEGER NOT NULL DEFAULT 0,
                result          TEXT,
                timestamp       TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_triggers_enabled ON triggers(enabled);
            CREATE INDEX IF NOT EXISTS idx_trigger_history_trigger ON trigger_history(trigger_id);
            CREATE INDEX IF NOT EXISTS idx_trigger_history_ts ON trigger_history(timestamp);

            CREATE TABLE IF NOT EXISTS user_preferences (
                session_id TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (session_id, key)
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id      TEXT PRIMARY KEY,
                username     TEXT NOT NULL DEFAULT 'local-user',
                display_name TEXT NOT NULL DEFAULT 'Local User',
                avatar       TEXT DEFAULT '',
                theme        TEXT DEFAULT 'light',
                timezone     TEXT DEFAULT '',
                locale       TEXT DEFAULT 'en',
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS user_preferences_v2 (
                user_id    TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, key)
            );

            CREATE TABLE IF NOT EXISTS profile_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                action     TEXT NOT NULL,
                detail     TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_profile_history_user ON profile_history(user_id);

            CREATE TABLE IF NOT EXISTS profile_presets (
                user_id     TEXT NOT NULL,
                preset_name TEXT NOT NULL,
                payload     TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, preset_name)
            );

            -- Operational memory is deliberately separate from the audit log.
            -- It is user-scoped, editable/expirable product state; audit_log is
            -- the immutable record of authorization and execution.
            CREATE TABLE IF NOT EXISTS episodic_memory (
                memory_id       TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                execution_id    TEXT NOT NULL UNIQUE,
                occurred_at     TEXT NOT NULL,
                summary         TEXT NOT NULL,
                intent_action   TEXT DEFAULT '',
                intent_target   TEXT DEFAULT '',
                tool_id         TEXT DEFAULT '',
                outcome         TEXT NOT NULL,
                risk_score      REAL,
                tags            TEXT NOT NULL DEFAULT '[]',
                metadata        TEXT NOT NULL DEFAULT '{}',
                expires_at      TEXT
            );

            CREATE TABLE IF NOT EXISTS memory_patterns (
                pattern_id      TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                pattern_type    TEXT NOT NULL,
                pattern_key     TEXT NOT NULL,
                evidence_count  INTEGER NOT NULL DEFAULT 0,
                confidence      REAL NOT NULL DEFAULT 0,
                first_seen      TEXT NOT NULL,
                last_seen       TEXT NOT NULL,
                data            TEXT NOT NULL DEFAULT '{}',
                UNIQUE(user_id, pattern_type, pattern_key)
            );

            CREATE TABLE IF NOT EXISTS learned_preferences (
                user_id         TEXT NOT NULL,
                key             TEXT NOT NULL,
                value           TEXT NOT NULL,
                source          TEXT NOT NULL,
                evidence_count  INTEGER NOT NULL DEFAULT 1,
                confidence      REAL NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            );

            INSERT OR IGNORE INTO emergency_stop (id, value) VALUES (1, 0);

            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_action   ON audit_log(action);
            CREATE INDEX IF NOT EXISTS idx_exec_timestamp  ON execution_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_episodic_user_time ON episodic_memory(user_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_patterns_user_type ON memory_patterns(user_id, pattern_type);
        """)
        self._ensure_column("audit_log", "event_id", "TEXT")
        self._ensure_column("audit_log", "execution_id", "TEXT")
        self._ensure_column("audit_log", "payload", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column("audit_log", "previous_hash", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("audit_log", "entry_hash", "TEXT")
        conn.executescript("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_event_id
                ON audit_log(event_id) WHERE event_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_entry_hash
                ON audit_log(entry_hash) WHERE entry_hash IS NOT NULL;
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END;
        """)
        self._ensure_column("agents", "description", "TEXT DEFAULT ''")
        self._ensure_column("agents", "provider", "TEXT DEFAULT 'ollama'")
        self._ensure_column("agents", "model", "TEXT DEFAULT ''")
        self._ensure_column("agents", "capabilities", "TEXT DEFAULT '[]'")
        self._ensure_column("agents", "allowed_tools", "TEXT DEFAULT '[]'")
        self._ensure_column("agents", "system_prompt", "TEXT DEFAULT ''")
        self._ensure_column("agents", "status", "TEXT DEFAULT 'idle'")
        self._ensure_column("agents", "max_concurrency", "INTEGER DEFAULT 1")
        self._ensure_column("user_profiles", "bio", "TEXT DEFAULT ''")
        self._ensure_column("user_profiles", "tags", "TEXT DEFAULT '[]'")
        self._ensure_column("user_profiles", "custom_fields", "TEXT DEFAULT '{}'")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vault_entries (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                category        TEXT NOT NULL DEFAULT 'general',
                encrypted_value TEXT NOT NULL DEFAULT '',
                rotatable       INTEGER NOT NULL DEFAULT 0,
                rotation_days   INTEGER NOT NULL DEFAULT 90,
                last_rotated    REAL,
                notes           TEXT DEFAULT '',
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS vault_audit (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_id    TEXT NOT NULL,
                action      TEXT NOT NULL,
                timestamp   TEXT DEFAULT (datetime('now')),
                details     TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_vault_audit_id ON vault_audit(vault_id);
        """)
        conn.commit()

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {
            row["name"]
            for row in self._get_conn().execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._get_conn().execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
            )

    def close_connections(self) -> None:
        try:
            if hasattr(self._local, "conn") and self._local.conn:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self._local.conn.close()
        except Exception:
            pass
        self._local.conn = None

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params: list) -> sqlite3.Cursor:
        return self._get_conn().executemany(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._get_conn().execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        return [dict(r) for r in self._get_conn().execute(sql, params).fetchall()]

    def commit(self):
        self._get_conn().commit()

    @contextmanager
    def transaction(self, *, immediate: bool = False):
        """Serialize a write transaction and roll it back on failure."""
        with self._write_lock:
            conn = self._get_conn()
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def config_get(self, key: str, default: str = "") -> str:
        row = self.fetchone("SELECT value FROM config WHERE key = ?", (key,))
        return row["value"] if row else default

    def config_set(self, key: str, value: str):
        self.execute(
            "INSERT INTO config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value),
        )
        self.commit()

    def config_delete(self, key: str):
        self.execute("DELETE FROM config WHERE key = ?", (key,))
        self.commit()

    def config_get_json(self, key: str, default: dict = None) -> dict:
        raw = self.config_get(key)
        if not raw:
            return default or {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default or {}

    def config_set_json(self, key: str, value: dict):
        self.config_set(key, json.dumps(value))

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def reset_for_testing(self) -> None:
        """Recreate only an explicitly isolated test database.

        Tests must never clear production tables to obtain isolation. Recreating the
        temporary database also lets append-only audit protections remain enabled in
        every environment.
        """
        if os.environ.get("AIVO_TESTING") != "1":
            raise RuntimeError("reset_for_testing is available only under AIVO_TESTING=1")
        _assert_safe_database_path(self.db_path)
        db_path = self.db_path
        self.close()
        for suffix in ("", "-wal", "-shm"):
            candidate = f"{db_path}{suffix}"
            if os.path.exists(candidate):
                os.remove(candidate)
        self._init(db_path)
