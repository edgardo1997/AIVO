"""
E2E tests for update schema migration and failed-update recovery.

Simulates an N-1 → N upgrade by creating a database with the previous schema
version and verifying the current sidecar migrates it forward. Also simulates
a failed update by corrupting the database and verifying recovery logic.

Marked ``e2e_real`` (skipped when sidecar.exe is unavailable).
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import struct
import socket
import subprocess
from pathlib import Path

import httpx
import psutil
import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.e2e_real,
    pytest.mark.skipif(
        os.environ.get("SENTINEL_RUN_REAL_E2E") != "1",
        reason="real sidecar E2E requires SENTINEL_RUN_REAL_E2E=1",
    ),
]

SIDECAR_EXE = Path(__file__).resolve().parent.parent / "dist" / "sidecar.exe"
START_TIMEOUT = 90.0
SECRET = "e2e-update-test-secret"

CURRENT_SCHEMA_VERSION = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_process_tree(process: subprocess.Popen) -> None:
    try:
        root = psutil.Process(process.pid)
        processes = root.children(recursive=True) + [root]
    except psutil.NoSuchProcess:
        return
    for item in reversed(processes):
        try:
            item.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=10)
    for item in alive:
        try:
            item.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)


def _create_legacy_db(db_path: Path, schema_version: int):
    """Create a minimal Sentinel database with an old schema_version."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            f"""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            PRAGMA user_version = {schema_version};
            INSERT OR REPLACE INTO config (key, value) VALUES
                ('schema_version', '{schema_version}'),
                ('ai_config', '{{"provider":"openrouter","api_key":"","model":"gpt-4o","base_url":""}}'),
                ('permissions', '{{"level":"confirm","allowlist":[],"blocklist":[],"auto_safe":true}}');
            CREATE TABLE IF NOT EXISTS conversation_history (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO conversation_history (id, role, content) VALUES
                ('legacy-1', 'user', 'Hello from the old version'),
                ('legacy-2', 'assistant', 'I am legacy data');
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def find_sidecar():
    if not SIDECAR_EXE.is_file():
        pytest.skip(f"sidecar.exe not found at {SIDECAR_EXE}")
    return SIDECAR_EXE


@pytest.fixture(scope="module")
def sidecar_exe():
    return find_sidecar()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """N-1 → N upgrade: start with old schema, verify migration."""

    def test_migrate_from_v2_to_current(self, sidecar_exe, tmp_path):
        db_path = tmp_path / "sentinel-v2.db"
        _create_legacy_db(db_path, schema_version=2)

        env = {
            "SENTINEL_DB_PATH": str(db_path),
            "SENTINEL_PLUGIN_DIR": str(tmp_path / "plugins"),
            "SENTINEL_SESSION_TOKEN": SECRET,
            "SENTINEL_ENABLE_ACL": "0",
            "SENTINEL_ENABLE_FLEET_STARTUP": "0",
            "SENTINEL_PORT": str(_free_port()),
        }
        base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"
        (tmp_path / "plugins").mkdir(exist_ok=True)

        proc = subprocess.Popen(
            [str(sidecar_exe)],
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        headers = _token_header(SECRET)
        deadline = time.time() + START_TIMEOUT
        ready = False
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=2)
                if resp.status_code == 200:
                    ready = True
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.5)
        if not ready:
            _, err = proc.communicate(timeout=5)
            pytest.fail(f"sidecar did not become ready with v2 DB\nstderr:\n{err[-2000:] if err else '(empty)'}")

        resp = httpx.get(f"{base_url}/api/info", headers=headers, timeout=5)
        assert resp.status_code == 200, "Info endpoint failed after migration"

        resp = httpx.get(f"{base_url}/api/sentinel/capabilities", headers=headers, timeout=5)
        assert resp.status_code == 200

        conn = sqlite3.connect(str(db_path))
        try:
            migrated_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            assert migrated_version >= CURRENT_SCHEMA_VERSION, (
                f"Expected schema >= {CURRENT_SCHEMA_VERSION}, got {migrated_version}"
            )
            rows = conn.execute("SELECT COUNT(*) FROM conversation_history").fetchone()
            assert rows[0] >= 2, "Legacy conversation data should survive migration"
        finally:
            conn.close()

        _stop_process_tree(proc)


class TestFailedUpdateRecovery:
    """Corrupted or incomplete state after a failed update."""

    def test_start_with_corrupt_db_fails_safely(self, sidecar_exe, tmp_path):
        db_path = tmp_path / "sentinel-corrupt.db"
        db_path.write_bytes(b"this is not a valid sqlite database\x00\x01\x02" * 100)

        env = {
            "SENTINEL_DB_PATH": str(db_path),
            "SENTINEL_PLUGIN_DIR": str(tmp_path / "plugins"),
            "SENTINEL_SESSION_TOKEN": SECRET,
            "SENTINEL_ENABLE_ACL": "0",
            "SENTINEL_ENABLE_FLEET_STARTUP": "0",
            "SENTINEL_PORT": str(_free_port()),
        }
        base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"
        (tmp_path / "plugins").mkdir(exist_ok=True)

        proc = subprocess.Popen(
            [str(sidecar_exe)],
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        headers = _token_header(SECRET)
        deadline = time.time() + START_TIMEOUT
        alive = False
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=2)
                if resp.status_code == 200:
                    alive = True
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.5)

        _stop_process_tree(proc)

        if not alive:
            return

        pytest.fail("Sidecar started with corrupted DB; should have refused")

    def test_recreate_db_after_corruption(self, sidecar_exe, tmp_path):
        db_path = tmp_path / "sentinel-recreate.db"

        env = {
            "SENTINEL_DB_PATH": str(db_path),
            "SENTINEL_PLUGIN_DIR": str(tmp_path / "plugins"),
            "SENTINEL_SESSION_TOKEN": SECRET,
            "SENTINEL_ENABLE_ACL": "0",
            "SENTINEL_ENABLE_FLEET_STARTUP": "0",
            "SENTINEL_PORT": str(_free_port()),
        }
        base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"
        (tmp_path / "plugins").mkdir(exist_ok=True)

        proc = subprocess.Popen(
            [str(sidecar_exe)],
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        headers = _token_header(SECRET)
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=2)
                if resp.status_code == 200:
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.5)
        else:
            _, err = proc.communicate(timeout=5)
            pytest.fail(f"Fresh sidecar did not start\nstderr:\n{err[-2000:] if err else '(empty)'}")

        assert db_path.is_file(), "Database file should have been created"
        conn = sqlite3.connect(str(db_path))
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            assert version >= CURRENT_SCHEMA_VERSION
        finally:
            conn.close()

        _stop_process_tree(proc)
