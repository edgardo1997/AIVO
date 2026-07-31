"""FASE 6 — Production test environment.

Isolated from the unit/integration suites: no SentinelRuntime, no stubs.
Sets up temp DB paths so every "real" component (DatabaseManager, StorageEngine,
SQLiteBackend) writes to an isolated SQLite file.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR = _REPO_ROOT / "sidecar"
_TMP = Path(tempfile.mkdtemp(prefix="sentinel-production-"))

if str(_SIDECAR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("SENTINEL_DB_PATH", str(_TMP / "operational.db"))
os.environ.setdefault("AIVO_DB_PATH", str(_TMP / "aivo.db"))
os.environ.setdefault("SENTINEL_DATABASE_URL", f"sqlite:///{_TMP / 'sentinel.db'}")
os.environ.setdefault("SENTINEL_DATA_DIR", str(_TMP))
os.environ.setdefault("SENTINEL_ENABLE_ACL", "0")
os.environ.setdefault("SENTINEL_ENABLE_FLEET_STARTUP", "0")
os.environ.setdefault("SENTINEL_JWT_SECRET", "production-test-secret")


@pytest.fixture(scope="session")
def production_db_dir() -> Path:
    return _TMP


@pytest_asyncio.fixture
async def stack(tmp_path):
    """Real production stack (orchestrator, gateway, pipeline, storage, router)."""
    from tests.production.harness import build_production_stack

    s = build_production_stack(tmp_path)
    await s.initialize()
    yield s
    try:
        await s.close()
    except Exception:
        pass


@pytest.fixture(scope="module")
def fastapi_client():
    """Real FastAPI app + real runtime wiring, isolated temp DB."""
    import repositories.database as db_mod
    import windows_acl

    windows_acl.ACL_ENABLED = False
    db_mod._TESTING = True

    from main import app, initialize_runtime
    from modules.permissions import _svc as perm_svc

    app.state._test_mode = True
    app.state._test_secret = "valid-test-token"
    initialize_runtime()
    perm_svc.set_level("admin")

    with TestClient(app) as tc:
        tc.headers.update({"X-Test-Token": "valid-test-token"})
        yield tc


def pytest_configure(config):
    for name in ("production", "stress", "chaos"):
        config.addinivalue_line("markers", f"{name}: FASE 6 real-component test")
    from tests.production import report

    report.register(config.pluginmanager)
