"""Transactional SQLite storage owned exclusively by the control boundary."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .schema import SCHEMA_SQL, SCHEMA_VERSION


class PersistentControlStorage:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            database_path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._initialize_schema()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def _initialize_schema(self) -> None:
        with self.transaction() as cursor:
            cursor.executescript(SCHEMA_SQL)
            row = cursor.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                cursor.execute(
                    "INSERT INTO schema_meta(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported persistent control schema")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()
        finally:
            cursor.close()

    def integrity_check(self) -> bool:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok"

    def close(self) -> None:
        self._connection.close()
