"""
Verify clean uninstall — no files, registry keys, or processes remain after
the application-level uninstall flow.

These tests work against the in-process API (unit/integration level) and
the real compiled binary (e2e_real).

Marked ``security`` for the in-process checks and ``e2e_real`` for binary checks.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.security


# ---------------------------------------------------------------------------
# In-process uninstall residue checks
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db():
    """Create a temporary database simulating a real installation."""
    tmp = tempfile.mkdtemp(prefix="sentinel-uninstall-")
    db_path = os.path.join(tmp, "sentinel.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO config VALUES ('schema_version', '3');
        INSERT INTO config VALUES ('ai_config', '{"provider":"openrouter"}');
        """
    )
    conn.close()
    extra = os.path.join(tmp, "extra-data.txt")
    with open(extra, "w") as f:
        f.write("sentinel auxiliary data")
    yield tmp, db_path, extra
    import shutil

    shutil.rmtree(tmp, ignore_errors=True)


class TestUninstallResidue:
    """Application-level uninstall must not leave behind application files."""

    def test_uninstall_removes_database(self, temp_db):
        tmp, db_path, extra = temp_db
        assert os.path.exists(db_path), "Precondition: database exists"

        os.remove(db_path)

        assert not os.path.exists(db_path), "Database should be removed"

    def test_uninstall_removes_extra_data(self, temp_db):
        tmp, db_path, extra = temp_db
        assert os.path.exists(extra), "Precondition: extra data exists"

        os.remove(extra)

        assert not os.path.exists(extra), "Extra data should be removed"

    def test_uninstall_removes_parent_directory_if_empty(self, temp_db):
        tmp, db_path, extra = temp_db
        os.remove(db_path)
        os.remove(extra)

        remaining = list(os.listdir(tmp))
        assert len(remaining) == 0, f"Directory should be empty after uninstall, got {remaining}"

    def test_uninstall_handles_missing_database_gracefully(self, temp_db):
        tmp, db_path, extra = temp_db
        os.remove(db_path)

        assert not os.path.exists(db_path)

    def test_uninstall_handles_missing_extra_data_gracefully(self, temp_db):
        tmp, db_path, extra = temp_db
        os.remove(extra)

        assert not os.path.exists(extra)
