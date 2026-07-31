"""StorageEngine — Conexión, sesiones, migraciones, transacciones.

Soporta:
  - Desarrollo: SQLite (aiosqlite)
  - Producción: PostgreSQL (asyncpg) — intercambiable vía StorageConfig
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    database_url: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False
    migrate_on_start: bool = True
    timeout: float = 30.0


class StorageEngine:
    """Motor de almacenamiento persistente.

    Gestiona conexión, sesiones y migraciones tanto para SQLite
    como para PostgreSQL.

    Uso:
      config = StorageConfig(database_url="sqlite:///sentinel.db")
      engine = StorageEngine(config)
      await engine.initialize()
      # ... operaciones ...
      await engine.close()
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self._config = config or StorageConfig()
        self._conn = None
        self._initialized = False
        self._in_transaction = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def config(self) -> StorageConfig:
        return self._config

    # ── Lifecycle ─────────────────────────────────────────────

    async def initialize(self) -> None:
        """Inicializa conexión y ejecuta migraciones."""
        if self._initialized:
            return
        db_url = self._resolve_url()
        self._conn = await self._connect(db_url)
        if self._config.migrate_on_start:
            await self._run_migrations()
        self._initialized = True
        logger.info("StorageEngine initialized: %s", self._mask_url(db_url))

    async def close(self) -> None:
        """Cierra conexión."""
        if self._conn:
            try:
                await self._conn.close()
            except Exception as e:
                logger.warning("StorageEngine close error: %s", e)
        self._initialized = False
        logger.info("StorageEngine closed")

    async def reconnect(self) -> None:
        """Reconecta (útil para modo degradado → normal)."""
        await self.close()
        await self.initialize()

    # ── Connection ────────────────────────────────────────────

    async def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Ejecuta SQL directamente (para migraciones)."""
        if not self._conn:
            raise RuntimeError("StorageEngine not initialized")
        try:
            cursor = await self._conn.execute(sql, params or {})
            if sql.strip().upper().startswith(("SELECT", "WITH")):
                rows = await cursor.fetchall()
                await cursor.close()
                return rows
            await cursor.close()
            if not self._in_transaction:
                await self._conn.commit()
            return cursor
        except Exception as e:
            logger.error("SQL execution error: %s", str(e)[:200])
            raise

    async def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> None:
        if not self._conn:
            raise RuntimeError("StorageEngine not initialized")
        for params in params_list:
            await self._conn.execute(sql, params)

    # ── Transactions ──────────────────────────────────────────

    async def begin(self) -> None:
        if self._in_transaction:
            return
        if self._conn:
            await self._conn.execute("BEGIN")
        self._in_transaction = True

    async def commit(self) -> None:
        if not self._in_transaction:
            return
        if self._conn:
            await self._conn.commit()
        self._in_transaction = False

    async def rollback(self) -> None:
        if not self._in_transaction:
            return
        if self._conn:
            await self._conn.rollback()
        self._in_transaction = False

    async def __aenter__(self):
        await self.begin()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()

    # ── Health ────────────────────────────────────────────────

    async def health(self) -> Dict[str, Any]:
        if not self._initialized or not self._conn:
            return {"status": "disconnected", "error": "Not initialized"}
        try:
            await self._conn.execute("SELECT 1")
            return {"status": "connected", "database": self._mask_url(self._resolve_url())}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Internal ──────────────────────────────────────────────

    def _resolve_url(self) -> str:
        url = self._config.database_url
        if not url:
            url = os.environ.get("SENTINEL_DATABASE_URL", "")
        if not url:
            data_dir = os.environ.get("SENTINEL_DATA_DIR", "")
            if data_dir:
                db_path = Path(data_dir) / "sentinel.db"
            else:
                db_path = Path(os.environ.get("LOCALAPPDATA", ".")) / "Sentinel" / "sentinel.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{db_path}"
        return url

    async def _connect(self, url: str) -> Any:
        if url.startswith("sqlite"):
            return await self._connect_sqlite(url)
        elif url.startswith("postgresql"):
            return await self._connect_postgres(url)
        raise ValueError(f"Unsupported database: {url}")

    async def _connect_sqlite(self, url: str) -> Any:
        import aiosqlite
        path = url.replace("sqlite:///", "")
        conn = await aiosqlite.connect(path, timeout=self._config.timeout)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def _connect_postgres(self, url: str) -> Any:
        try:
            import asyncpg
            conn = await asyncpg.connect(url.replace("postgresql://", "postgres://"))
            return conn
        except ImportError:
            raise RuntimeError("asyncpg not installed — install with: pip install asyncpg")

    async def _run_migrations(self) -> None:
        """Ejecuta migraciones desde sentinel/storage/migrations/.

        Versiona el esquema vía PRAGMA user_version y hace backup del archivo
        antes de aplicar migraciones nuevas (FASE 5.9).
        """
        import importlib.resources as pkg_resources
        try:
            from sentinel.storage import migrations as migrations_pkg
            try:
                files = sorted(pkg_resources.files(migrations_pkg).glob("*.sql"))
            except (AttributeError, TypeError):
                # Python 3.12 MultiplexedPath fallback
                pkg_path = list(migrations_pkg.__path__)[0]
                files = sorted(Path(pkg_path).glob("*.sql"))
            current = await self._schema_version()
            versions = []
            for f in files:
                try:
                    versions.append((int(Path(f.name).name.split("_")[0]), f))
                except (ValueError, IndexError):
                    versions.append((0, f))
            max_version = max((v for v, _ in versions), default=0)
            pending = [(v, f) for v, f in versions if v > current]
            if pending:
                await self._backup_before_migration()
            for v, f in versions:
                if v > current:
                    sql = f.read_text()
                    logger.info("Running migration: %s (version %d)", f.name, v)
                    statements = [s.strip() for s in sql.split(";") if s.strip()]
                    for stmt in statements:
                        try:
                            await self._conn.execute(stmt)
                        except Exception as e:
                            logger.warning("Migration statement failed (may be idempotent): %s", str(e)[:100])
            await self._conn.commit()
            if max_version > current:
                await self._set_schema_version(max_version)
                logger.info("Schema upgraded: %d -> %d", current, max_version)
        except (ImportError, ModuleNotFoundError):
            # Fallback: inline migrations
            await self._run_inline_migrations()
            await self._conn.commit()

    async def _schema_version(self) -> int:
        rows = await self._conn.execute("PRAGMA user_version")
        row = await rows.fetchone()
        return int(row[0]) if row else 0

    async def _set_schema_version(self, version: int) -> None:
        await self._conn.execute(f"PRAGMA user_version = {int(version)}")

    async def _backup_before_migration(self) -> None:
        """Copia de seguridad del archivo SQLite antes de migraciones nuevas."""
        url = self._resolve_url()
        if not url.startswith("sqlite"):
            return
        path = url.replace("sqlite:///", "")
        if not os.path.isfile(path):
            return
        try:
            import shutil
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = f"{path}.backup-{ts}"
            shutil.copy2(path, target)
            logger.info("Database backup created: %s", target)
        except Exception as e:
            logger.warning("Backup before migration failed: %s", e)

    async def _run_inline_migrations(self) -> None:
        """Migraciones inline si no hay archivos .sql."""
        migrations = [
            # models
            "CREATE TABLE IF NOT EXISTS stored_models (id TEXT PRIMARY KEY, name TEXT, provider TEXT, local INTEGER, capabilities TEXT, context_size INTEGER, cost REAL, latency_estimate REAL, last_seen TEXT, created_at TEXT)",
            # feedback
            "CREATE TABLE IF NOT EXISTS feedback_records (id TEXT PRIMARY KEY, model_id TEXT, task_type TEXT, success INTEGER, quality_score REAL, latency REAL, error TEXT, user_id TEXT, session_id TEXT, metadata TEXT, created_at TEXT)",
            # metrics
            "CREATE TABLE IF NOT EXISTS metric_records (id TEXT PRIMARY KEY, component TEXT, metric_name TEXT, value REAL, unit TEXT, tags TEXT, timestamp TEXT)",
            # conversations
            "CREATE TABLE IF NOT EXISTS conversations (session_id TEXT, message_id TEXT, role TEXT, content TEXT, context TEXT, model_id TEXT, created_at TEXT, PRIMARY KEY (session_id, message_id))",
            # decisions
            "CREATE TABLE IF NOT EXISTS decision_history (id TEXT PRIMARY KEY, request TEXT, intent TEXT, decision TEXT, risk_level TEXT, selected_model TEXT, reason TEXT, execution_id TEXT, created_at TEXT)",
            # intelligence
            "CREATE TABLE IF NOT EXISTS model_performance (id INTEGER PRIMARY KEY AUTOINCREMENT, model_name TEXT, task_type TEXT, latency REAL, success INTEGER, quality_score REAL, resource_usage REAL, tokens_used INTEGER, cost REAL, created_at TEXT)",
            # executions (FASE 5.4)
            "CREATE TABLE IF NOT EXISTS executions (execution_id TEXT PRIMARY KEY, timestamp TEXT, user_request TEXT DEFAULT '', intent TEXT DEFAULT '', task_type TEXT DEFAULT '', selected_model TEXT DEFAULT '', tools_used TEXT DEFAULT '[]', duration REAL DEFAULT 0.0, success INTEGER DEFAULT 1, failure_reason TEXT, risk_level TEXT DEFAULT '', cost REAL DEFAULT 0.0, confidence_score REAL DEFAULT 0.0, error TEXT)",
            "CREATE INDEX IF NOT EXISTS idx_executions_timestamp ON executions(timestamp)",
            # user preferences (FASE 5.7)
            "CREATE TABLE IF NOT EXISTS user_preferences (user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT DEFAULT 'null', source TEXT DEFAULT 'observed', evidence_count INTEGER DEFAULT 1, confidence REAL DEFAULT 0.5, created_at TEXT, updated_at TEXT, PRIMARY KEY (user_id, key))",
            "CREATE INDEX IF NOT EXISTS idx_perf_model_task ON model_performance(model_name, task_type)",
        ]
        for sql in migrations:
            try:
                await self._conn.execute(sql)
            except Exception as e:
                logger.warning("Migration: %s", str(e)[:100])
        await self._set_schema_version(2)

    @staticmethod
    def _mask_url(url: str) -> str:
        if "://" not in url:
            return url
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            userinfo, host = rest.rsplit("@", 1)
            return f"{scheme}://***@{host}"
        return f"{scheme}://{rest[:20]}..."
