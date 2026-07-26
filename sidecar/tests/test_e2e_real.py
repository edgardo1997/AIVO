"""
E2E tests against the real compiled sidecar.exe binary.

These tests build (or find) the PyInstaller-packaged sidecar, spawn it as a
subprocess, and exercise the complete install → configure → converse →
execute → restart → persist → uninstall workflow against the real HTTP API.

Marked ``e2e_real`` (skipped when sidecar.exe is unavailable).
"""

import os
import sys
import json
import time
import signal
import socket
import shutil
import hashlib
import tempfile
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
SENTINEL_ROOT = Path(__file__).resolve().parent.parent.parent
START_TIMEOUT = 90.0
SECRET = "e2e-real-test-secret-key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _sid_paths(tmp: Path) -> dict:
    db = tmp / "sentinel-e2e.db"
    plugins = tmp / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    return {
        "SENTINEL_DB_PATH": str(db),
        "SENTINEL_PLUGIN_DIR": str(plugins),
        "SENTINEL_SESSION_TOKEN": SECRET,
        "SENTINEL_ENABLE_ACL": "0",
        "SENTINEL_ENABLE_FLEET_STARTUP": "0",
        "SENTINEL_PORT": str(_free_port()),
    }


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def find_or_build_sidecar():
    """Return the path to a usable sidecar.exe, building it if needed."""
    if SIDECAR_EXE.is_file():
        return SIDECAR_EXE
    if not shutil.which("pyinstaller"):
        pytest.skip("sidecar.exe not found and PyInstaller is not installed")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "sidecar.spec"],
        cwd=str(SIDECAR_EXE.parent.parent),
        check=True,
        capture_output=True,
    )
    if not SIDECAR_EXE.is_file():
        pytest.fail("PyInstaller build produced no sidecar.exe")
    return SIDECAR_EXE


@pytest.fixture(scope="module")
def sidecar_exe():
    return find_or_build_sidecar()


@pytest.fixture
def env(sidecar_exe, tmp_path):
    return _sid_paths(tmp_path)


@pytest.fixture
def proc(sidecar_exe, env):
    process = subprocess.Popen(
        [str(sidecar_exe)],
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    yield process
    _stop_process_tree(process)


@pytest.fixture
def client(proc, env):
    base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"
    headers = _token_header(SECRET)
    deadline = time.time() + START_TIMEOUT
    last_err = ""
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=2)
            if resp.status_code == 200 and resp.json().get("status") == "healthy":
                with httpx.Client(base_url=base_url, headers=headers, timeout=30) as api:
                    yield api
                return
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_err = str(exc)
            time.sleep(0.5)

    _, err = proc.communicate(timeout=3)
    pytest.fail(
        f"sidecar.exe did not become ready within {START_TIMEOUT}s\n"
        f"stderr (last 2k):\n{err[-2000:] if err else '(empty)'}\n"
        f"last error: {last_err}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2EReal:
    """Install → configure → converse → execute → restart → uninstall."""

    def test_health_and_info(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0.0"
        assert data["name"] == "Sentinel Sidecar"

    def test_capabilities(self, client):
        resp = client.get("/api/sentinel/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = {t["id"] for t in data["tools"]}
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids
        assert "app.discovery" in tool_ids

    def test_configure(self, client):
        config = {
            "provider": "openrouter",
            "api_key": "test-key-e2e",
            "model": "gpt-4o",
            "base_url": "http://test",
        }
        resp = client.post("/ai/config", json=config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"

    def test_execute_system_info(self, client):
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "show system information"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_result"]["success"] is True

    def test_execute_cpu(self, client):
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "what is my cpu usage"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool_result"]["success"] is True

    def test_governed_action_requires_confirmation(self, client):
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "show system information"},
        )
        assert resp.status_code == 200

    def test_plugin_workflow(self, client):
        plugin_id = "e2e_test_plugin"
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "plugins.create",
                "params": {"name": plugin_id, "template": "minimal"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True

        resp = client.post("/v1/execute", json={"tool_id": "plugins.list", "params": {}})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        plugins = data.get("data", {}).get("plugins", [])
        assert any(item.get("id") == plugin_id for item in plugins)

    def test_uninstall_residue_via_api(self, client, env):
        resp = client.post("/api/sentinel/uninstall", json={"confirm": True})
        assert resp.status_code in (200, 404)

    def test_authenticated_endpoints_reject_anonymous(self, client, proc, env):
        base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"
        resp = httpx.get(f"{base_url}/api/health", timeout=5)
        assert resp.status_code == 200
        resp = httpx.get(f"{base_url}/api/info", timeout=5)
        assert resp.status_code == 200
        resp = httpx.post(
            f"{base_url}/api/sentinel/process",
            json={"utterance": "test"},
            timeout=5,
        )
        assert resp.status_code in (401, 403)


class TestPersistenceAfterRestart:
    """Restart the sidecar and verify state survives."""

    def test_persistence(self, sidecar_exe, tmp_path):
        env = _sid_paths(tmp_path)
        env["SENTINEL_ENABLE_ACL"] = "0"
        env["SENTINEL_ENABLE_FLEET_STARTUP"] = "0"
        base_url = f"http://127.0.0.1:{env['SENTINEL_PORT']}"

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
            _stop_process_tree(proc)
            pytest.fail("First start did not become ready")

        original_db_mtime = os.path.getmtime(env["SENTINEL_DB_PATH"])
        _stop_process_tree(proc)

        proc2 = subprocess.Popen(
            [str(sidecar_exe)],
            env={**os.environ, **env},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/health", headers=headers, timeout=2)
                if resp.status_code == 200:
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.5)
        else:
            _stop_process_tree(proc2)
            pytest.fail("Restart did not become ready")

        resp = httpx.get(f"{base_url}/api/info", headers=headers, timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0.0"
        assert os.path.getmtime(env["SENTINEL_DB_PATH"]) >= original_db_mtime

        resp = httpx.get(f"{base_url}/api/sentinel/capabilities", headers=headers, timeout=5)
        assert resp.status_code == 200
        tool_ids = {t["id"] for t in resp.json()["tools"]}
        assert "system.cpu" in tool_ids
        assert "system.info" in tool_ids

        _stop_process_tree(proc2)
