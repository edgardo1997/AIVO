import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Module-level flag — set to True by conftest.py to enable testing-only operations
_TESTING = False

# Retry configuration for SQLITE_BUSY / locked database
_MAX_RETRIES = 5
_BASE_RETRY_DELAY = 0.05  # 50ms
_MAX_RETRY_DELAY = 1.0    # 1s
_RETRY_BACKOFF = 2.0      # exponential backoff multiplier


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

SENTINEL_DATA_DIR = os.path.abspath(os.path.expanduser("~/.sentinel"))
SENTINEL_PRODUCTION_DB_PATH = os.path.join(SENTINEL_DATA_DIR, "sentinel.db")
LEGACY_PRODUCTION_DB_PATH = os.path.abspath(os.path.expanduser("~/.aivo.db"))
PRODUCTION_DB_PATH = SENTINEL_PRODUCTION_DB_PATH
LATEST_SCHEMA_VERSION = 4


def _schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _assert_supported_schema_version(conn: sqlite3.Connection) -> None:
    version = _schema_version(conn)
    if version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than this Sentinel build "
            f"supports ({LATEST_SCHEMA_VERSION}). Refusing to open it."
        )


def _execute_with_retry(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """Execute SQL with exponential backoff retry for SQLITE_BUSY."""
    delay = _BASE_RETRY_DELAY
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() or "SQLITE_BUSY" in str(e):
                if attempt < _MAX_RETRIES:
                    time.sleep(delay)
                    delay = min(delay * _RETRY_BACKOFF, _MAX_RETRY_DELAY)
                    continue
            raise


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
    """Fail closed if a test process attempts to open the production database.

    In production this always runs to prevent accidental database corruption.
    During testing the check is skipped because conftest.py already guarantees
    SENTINEL_DB_PATH points to an isolated temporary database.
    """
    if _TESTING:
        return
    candidate = os.path.normcase(_normalize_path(db_path))
    protected_paths = {
        os.path.normcase(SENTINEL_PRODUCTION_DB_PATH),
        os.path.normcase(LEGACY_PRODUCTION_DB_PATH),
    }
    if candidate in protected_paths:
        raise RuntimeError(
            "Refusing to open a production database path in this process. "
            "Set SENTINEL_DB_PATH to an isolated database."
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
        self._connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._connection_generation = 0
        _assert_supported_schema_version(self._get_conn())
        self._create_schema()
        self._run_migrations()
        self._protect_database_files()
        self._verify_integrity()
        self._checkpoint_wal()

    def _verify_integrity(self) -> None:
        """Verify database integrity on startup (lightweight check)."""
        try:
            conn = self._get_conn()
            # Quick integrity check (does not scan all pages)
            result = conn.execute("PRAGMA quick_check").fetchone()
            if result and result[0] != "ok":
                logger.warning("Database integrity check failed: %s", result[0])
        except Exception as e:
            logger.warning("Could not verify database integrity: %s", e)

    def _checkpoint_wal(self) -> None:
        """Checkpoint WAL to keep it bounded."""
        try:
            conn = self._get_conn()
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as e:
            logger.warning("WAL checkpoint failed: %s", e)

    def _cleanup_expired(self) -> dict:
        """Remove expired records from episodic_memory, environment_changes, pending_actions."""
        now = _utc_now()
        counts = {"episodic_memory": 0, "environment_changes": 0, "pending_actions": 0}
        try:
            conn = self._get_conn()
            with self._write_lock:
                result = conn.execute(
                    "DELETE FROM episodic_memory WHERE expires_at IS NOT NULL AND expires_at <= ?",
                    (now,)
                )
                counts["episodic_memory"] = result.rowcount

                result = conn.execute(
                    "DELETE FROM environment_changes WHERE expires_at IS NOT NULL AND expires_at <= ?",
                    (now,)
                )
                counts["environment_changes"] = result.rowcount

                result = conn.execute(
                    "DELETE FROM pending_actions WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') <= ?",
                    (now,)
                )
                counts["pending_actions"] = result.rowcount

                if any(counts.values()):
                    conn.commit()
                    logger.info("TTL cleanup: %s", counts)
        except Exception as e:
            logger.warning("TTL cleanup failed: %s", e)
        return counts

    def _protect_database_files(self):
        from windows_acl import protect_path

        for candidate in (self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"):
            if os.path.exists(candidate):
                protect_path(candidate, directory=False)

    def _get_conn(self) -> sqlite3.Connection:
        if (
            not hasattr(self._local, "conn")
            or self._local.conn is None
            or getattr(self._local, "generation", -1) != self._connection_generation
        ):
            with self._connections_lock:
                generation = self._connection_generation
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=10,
                    isolation_level=None,
                    check_same_thread=False,
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-8000")
                conn.execute("PRAGMA temp_store=MEMORY")
                conn.execute("PRAGMA mmap_size=268435456")
                self._connections.add(conn)
                self._local.conn = conn
                self._local.generation = generation
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

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
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

            CREATE TABLE IF NOT EXISTS fleet_devices (
                device_id    TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                device_type  TEXT DEFAULT 'node',
                os           TEXT DEFAULT '',
                version      TEXT DEFAULT '',
                ip           TEXT DEFAULT '',
                port         INTEGER DEFAULT 8765,
                last_seen    TEXT,
                capabilities TEXT DEFAULT '{}',
                is_self      INTEGER DEFAULT 0,
                notes        TEXT DEFAULT '',
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fleet_sync_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                direction    TEXT NOT NULL,
                peer_id      TEXT DEFAULT '',
                peer_url     TEXT DEFAULT '',
                status       TEXT DEFAULT 'pending',
                config_keys  TEXT DEFAULT '',
                error        TEXT DEFAULT '',
                started_at   TEXT DEFAULT (datetime('now')),
                completed_at TEXT
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

            -- Session-scoped preferences require an explicit owner. The legacy
            -- table remains readable for compatibility with pre-v2 databases.
            CREATE TABLE IF NOT EXISTS session_preferences (
                user_id    TEXT NOT NULL,
                session_id TEXT NOT NULL,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, session_id, key)
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

            CREATE TABLE IF NOT EXISTS conversation_threads (
                user_id    TEXT NOT NULL,
                session_id TEXT NOT NULL,
                title      TEXT NOT NULL DEFAULT 'Nueva operación',
                messages   TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_threads_user_updated
                ON conversation_threads(user_id, updated_at DESC);

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

            -- Environmental learning stores an allowlisted capability baseline,
            -- never activity, file content, browser history, paths or secrets.
            CREATE TABLE IF NOT EXISTS environment_snapshots (
                user_id         TEXT PRIMARY KEY,
                fingerprint     TEXT NOT NULL,
                data            TEXT NOT NULL DEFAULT '{}',
                source          TEXT NOT NULL,
                confidence      REAL NOT NULL DEFAULT 0,
                observed_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS environment_changes (
                change_id       TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                change_type     TEXT NOT NULL,
                subject_id      TEXT NOT NULL,
                summary         TEXT NOT NULL,
                previous        TEXT NOT NULL DEFAULT '{}',
                current         TEXT NOT NULL DEFAULT '{}',
                source          TEXT NOT NULL,
                confidence      REAL NOT NULL DEFAULT 0,
                detected_at     TEXT NOT NULL,
                expires_at      TEXT
            );

            INSERT OR IGNORE INTO emergency_stop (id, value) VALUES (1, 0);

            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_action   ON audit_log(action);
            CREATE INDEX IF NOT EXISTS idx_exec_timestamp  ON execution_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_exec_owner_session
                ON execution_history(
                    json_extract(context_summary, '$.user_id'),
                    json_extract(context_summary, '$.session_id'),
                    timestamp DESC
                );
            CREATE INDEX IF NOT EXISTS idx_episodic_user_time ON episodic_memory(user_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_session_preferences_owner
                ON session_preferences(user_id, session_id);
            CREATE INDEX IF NOT EXISTS idx_patterns_user_type ON memory_patterns(user_id, pattern_type);
            CREATE INDEX IF NOT EXISTS idx_environment_changes_user_time
                ON environment_changes(user_id, detected_at DESC);
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
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
            (LATEST_SCHEMA_VERSION - 1, "Baseline schema"),
        )
        conn.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")
        conn.commit()

    MIGRATIONS = {
        4: "Add version column to conversation_threads for merge-by-version",
    }

    def _run_migrations(self) -> None:
        """Run versioned migrations transactionally."""
        conn = self._get_conn()
        applied = set(
            row[0] for row in
            conn.execute("SELECT version FROM schema_migrations").fetchall()
        )
        for version in sorted(self.MIGRATIONS):
            if version in applied:
                continue
            desc = self.MIGRATIONS[version]
            with self.transaction(immediate=True):
                try:
                    if version == 4:
                        self._ensure_column("conversation_threads", "version", "INTEGER DEFAULT 1")
                        conn.execute(
                            "UPDATE conversation_threads SET version = 1 WHERE version IS NULL"
                        )
                    conn.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                        (version, desc),
                    )
                    logger.info("Migration v%d applied: %s", version, desc)
                except Exception:
                    logger.exception("Migration v%d failed, rolling back", version)
                    raise

    @property
    def schema_version(self) -> int:
        return _schema_version(self._get_conn())

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in self._get_conn().execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self._get_conn().execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def close_connections(self) -> None:
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
            self._connection_generation += 1
        for conn in connections:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
            except sqlite3.Error:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        self._local.conn = None
        self._local.generation = self._connection_generation

    def _execute_with_retry(self, conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute SQL with exponential backoff retry on SQLITE_BUSY / locked."""
        delay = _BASE_RETRY_DELAY
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return conn.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    if attempt < _MAX_RETRIES:
                        logger.warning("Database locked (attempt %d/%d), retrying in %.2fs: %s",
                                       attempt + 1, _MAX_RETRIES, delay, e)
                        time.sleep(delay)
                        delay = min(delay * _RETRY_BACKOFF, _MAX_RETRY_DELAY)
                        continue
                raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_conn()
        return self._execute_with_retry(conn, sql, params)

    def executemany(self, sql: str, params: list) -> sqlite3.Cursor:
        conn = self._get_conn()
        for p in params:
            self._execute_with_retry(conn, sql, p)
        return conn.cursor()

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._execute_with_retry(self._get_conn(), sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        return [dict(r) for r in self._execute_with_retry(self._get_conn(), sql, params).fetchall()]

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

    def checkpoint_wal(self, mode: str = "PASSIVE") -> int:
        """Checkpoint the WAL file. Returns number of frames checkpointed."""
        conn = self._get_conn()
        result = self._execute_with_retry(conn, f"PRAGMA wal_checkpoint({mode})").fetchone()
        return result[1] if result else 0

    def cleanup_expired(self) -> dict:
        """Remove expired records from episodic_memory, environment_changes, pending_actions.
        Returns count of deleted rows per table."""
        now = _utc_now()
        conn = self._get_conn()
        deleted = {}
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Clean episodic_memory
                result = conn.execute(
                    "DELETE FROM episodic_memory WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
                )
                deleted["episodic_memory"] = result.rowcount

                # Clean environment_changes
                result = conn.execute(
                    "DELETE FROM environment_changes WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
                )
                deleted["environment_changes"] = result.rowcount

                # Clean pending_actions (ttl_seconds from created_at)
                result = conn.execute(
                    """DELETE FROM pending_actions
                       WHERE datetime(created_at, '+' || ttl_seconds || ' seconds') <= ?""",
                    (now,)
                )
                deleted["pending_actions"] = result.rowcount

                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted

    def verify_integrity(self) -> dict:
        """Run PRAGMA integrity_check and return result."""
        conn = self._get_conn()
        result = self._execute_with_retry(conn, "PRAGMA integrity_check").fetchone()
        return {"valid": result[0] == "ok", "details": result[0]}

    def backup(self, backup_path: str) -> dict:
        """Create a consistent backup using SQLite's backup API.
        Returns dict with backup_path and size."""
        import sqlite3 as sqlite3_mod
        backup_path = _normalize_path(backup_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with self._write_lock:
            source = self._get_conn()
            dest = sqlite3_mod.connect(backup_path)
            try:
                source.backup(dest)
                dest.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                dest.commit()
            finally:
                dest.close()
        size = os.path.getsize(backup_path)
        logger.info("Database backup created: %s (%d bytes)", backup_path, size)
        return {"backup_path": backup_path, "size_bytes": size}

    def restore(self, backup_path: str) -> None:
        """Restore database from backup. Closes all connections first."""
        backup_path = _normalize_path(backup_path)
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        self.close_connections()
        # Replace the main database file
        shutil.copy2(backup_path, self.db_path)
        # Also copy WAL/SHM if they exist
        for suffix in ("-wal", "-shm"):
            src = backup_path + suffix
            dst = self.db_path + suffix
            if os.path.exists(src):
                shutil.copy2(src, dst)
        self._connection_generation += 1
        self._local.conn = None
        self._local.generation = self._connection_generation
        _assert_supported_schema_version(self._get_conn())
        logger.info("Database restored from: %s", backup_path)

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

    def list_conversations(self, user_id: str, limit: int = 100) -> list[dict]:
        rows = self.fetchall(
            """SELECT session_id, title, messages, created_at, updated_at, version
               FROM conversation_threads
               WHERE user_id = ?
               ORDER BY updated_at DESC LIMIT ?""",
            (user_id, max(1, min(limit, 200))),
        )
        for row in rows:
            try:
                row["messages"] = json.loads(row["messages"])
            except (TypeError, json.JSONDecodeError):
                row["messages"] = []
        return rows

    def get_conversation(self, user_id: str, session_id: str) -> dict | None:
        row = self.fetchone(
            """SELECT session_id, title, messages, created_at, updated_at, version
               FROM conversation_threads WHERE user_id = ? AND session_id = ?""",
            (user_id, session_id),
        )
        if row is None:
            return None
        try:
            row["messages"] = json.loads(row["messages"])
        except (TypeError, json.JSONDecodeError):
            row["messages"] = []
        return row

    def upsert_conversation(
        self,
        user_id: str,
        session_id: str,
        title: str,
        messages: list[dict],
        updated_at: str,
        expected_version: int | None = None,
    ) -> dict:
        """Upsert conversation with version-based merge.

        If *expected_version* is given, the update only applies when the stored
        version matches, preventing blind overwrites from stale clients.
        Returns the current conversation (with incremented version on success).
        """
        encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        with self.transaction(immediate=True) as conn:
            # Read current version
            existing_row = conn.execute(
                """SELECT version FROM conversation_threads
                   WHERE user_id = ? AND session_id = ?""",
                (user_id, session_id),
            ).fetchone()
            current_version = existing_row["version"] if existing_row else 0

            if expected_version is not None and current_version != expected_version:
                logger.warning(
                    "Version mismatch for conversation %s/%s: expected=%d got=%d",
                    user_id, session_id, expected_version, current_version,
                )
                # Return existing data without modification
                return self.get_conversation(user_id, session_id) or {}

            next_version = current_version + 1
            conn.execute(
                """INSERT INTO conversation_threads
                       (user_id, session_id, title, messages, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, session_id) DO UPDATE SET
                       title = excluded.title,
                       messages = excluded.messages,
                       updated_at = excluded.updated_at,
                       version = excluded.version""",
                (user_id, session_id, title, encoded, updated_at, updated_at, next_version),
            )
        result = self.get_conversation(user_id, session_id) or {}
        result["version"] = next_version
        return result

    def append_conversation_message(
        self,
        user_id: str,
        session_id: str,
        title: str,
        message: dict,
        updated_at: str,
    ) -> dict:
        """Append one completed turn without a read/write race between clients."""
        with self.transaction(immediate=True) as conn:
            row = conn.execute(
                """SELECT title, messages, created_at, version FROM conversation_threads
                   WHERE user_id = ? AND session_id = ?""",
                (user_id, session_id),
            ).fetchone()
            messages = []
            current_version = row["version"] if row else 0
            if row:
                try:
                    messages = json.loads(row["messages"])
                except (TypeError, json.JSONDecodeError):
                    messages = []
            messages = [*messages[-199:], message]
            encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
            created_at = row["created_at"] if row else updated_at
            stored_title = row["title"] if row and row["title"] != "Nueva operación" else title
            next_version = current_version + 1
            conn.execute(
                """INSERT INTO conversation_threads
                       (user_id, session_id, title, messages, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, session_id) DO UPDATE SET
                       title = excluded.title,
                       messages = excluded.messages,
                       updated_at = excluded.updated_at,
                       version = excluded.version""",
                (user_id, session_id, stored_title, encoded, created_at, updated_at, next_version),
            )
        return self.get_conversation(user_id, session_id) or {}

    def delete_conversation(self, user_id: str, session_id: str) -> bool:
        with self.transaction(immediate=True) as conn:
            cursor = conn.execute(
                "DELETE FROM conversation_threads WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
        return cursor.rowcount > 0

    def run_maintenance(self) -> dict:
        """Run periodic maintenance: WAL checkpoint + TTL cleanup + integrity check."""
        wal_frames = self.checkpoint_wal("PASSIVE")
        cleaned = self.cleanup_expired()
        integrity = self.verify_integrity()
        return {
            "wal_checkpointed_frames": wal_frames,
            "cleaned": cleaned,
            "integrity": integrity,
        }

    def vacuum_backup(self, backup_dir: str = None) -> str:
        """Create a consistent backup of the database using VACUUM INTO."""
        if backup_dir is None:
            backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = _utc_now().replace(":", "-").replace(".", "-")
        backup_path = os.path.join(backup_dir, f"sentinel-{timestamp}.db")
        with self.transaction(immediate=True) as conn:
            conn.execute(f"VACUUM INTO '{backup_path}'")
        # Also copy WAL/SHM if they exist
        for suffix in ("-wal", "-shm"):
            src = f"{self.db_path}{suffix}"
            dst = f"{backup_path}{suffix}"
            if os.path.exists(src):
                shutil.copy2(src, dst)
        logger.info("Database backed up to %s", backup_path)
        return backup_path

    def close(self):
        self.close_connections()

    def reset_for_testing(self) -> None:
        """Recreate only an explicitly isolated test database.

        Tests must never clear production tables to obtain isolation. Recreating the
        temporary database also lets append-only audit protections remain enabled in
        every environment.
        """
        if not _TESTING:
            raise RuntimeError("reset_for_testing is available only when _TESTING is True")
        _assert_safe_database_path(self.db_path)
        db_path = self.db_path
        self.close()
        for suffix in ("", "-wal", "-shm"):
            candidate = f"{db_path}{suffix}"
            if os.path.exists(candidate):
                os.remove(candidate)
        self._init(db_path)
