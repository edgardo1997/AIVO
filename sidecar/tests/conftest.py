import pytest
import os
import sys
import json
import shutil
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch

os.environ["SENTINEL_ENABLE_ACL"] = "0"
os.environ["SENTINEL_ENABLE_FLEET_STARTUP"] = "0"
os.environ.setdefault("SENTINEL_JWT_SECRET", "sentinel-test-jwt-secret-not-for-production")
_test_data_dir = tempfile.mkdtemp(prefix="sentinel-tests-")
os.environ["SENTINEL_DB_PATH"] = os.path.join(_test_data_dir, "sentinel-test.db")
os.environ["AIVO_DB_PATH"] = os.environ["SENTINEL_DB_PATH"]
_sidecar_dir = os.path.join(os.path.dirname(__file__), "..")
_aivo_dir = os.path.join(_sidecar_dir, "..")
sys.path.insert(0, os.path.abspath(_sidecar_dir))
sys.path.insert(0, os.path.abspath(_aivo_dir))

from main import app, _rate_limiter, initialize_runtime
from modules.auth import IdentityContext
from modules.permissions import _svc as perm_svc

import windows_acl
import repositories.database as db_mod

windows_acl.ACL_ENABLED = False
db_mod._TESTING = True

app.state._test_mode = True
app.state._test_secret = "valid-test-token"

TEST_IDENTITY = IdentityContext.test_identity().to_dict()


@pytest.fixture(scope="session", autouse=True)
def initialized_test_runtime():
    """Tests opt into runtime registration instead of relying on import side effects."""
    initialize_runtime()


def admin_mode():
    perm_svc.set_level("admin")


def confirm_mode():
    perm_svc.set_level("confirm")


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database():
    """Keep the entire test session away from the user's persistent database."""
    from repositories.database import DatabaseManager, PRODUCTION_DB_PATH

    db = DatabaseManager()
    assert os.path.normcase(os.path.abspath(db.db_path)) != os.path.normcase(PRODUCTION_DB_PATH)
    yield
    db.close()
    shutil.rmtree(_test_data_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state():
    perm_svc.pending_actions.clear()
    perm_svc.emergency_stop_flag = False
    _rate_limiter.clear()
    default_perms = {"level": "confirm", "allowlist": [], "blocklist": [], "auto_safe": True}
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    db.config_set_json("permissions", default_perms)
    db.config_set_json(
        "fleet_config",
        {
            "remote_enabled": False,
            "pairing_token": "",
            "pairing_token_hash": "",
            "local_ip": "",
            "api_port": 8765,
            "fleet_port": 8766,
        },
    )
    db.config_set_json(
        "ai_config",
        {"provider": "openrouter", "api_key": "", "model": "gpt-4o", "base_url": ""},
    )
    try:
        from modules.sentinel_bridge import get_orchestrator

        orch = get_orchestrator()
        rl = getattr(orch, "_rate_limiter", None)
        if rl is not None:
            rl.clear()
    except Exception:
        pass
    try:
        from modules.sentinel_bridge import get_memory

        mem = get_memory()
        if mem is not None:
            mem.clear()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def disable_external_model_probes(monkeypatch):
    """Unit and integration tests must never discover services on the host."""
    from sentinel.core.model_router import ModelRouter

    monkeypatch.setattr(
        ModelRouter,
        "check_health",
        lambda self, provider_id, timeout=0.75: {
            "provider_id": provider_id,
            "available": False,
            "reason": "disabled_in_tests",
        },
    )


@pytest.fixture
def client():
    with TestClient(app) as tc:
        tc.headers.update({"X-Test-Token": "valid-test-token"})
        yield tc


@pytest.fixture
def temp_config(tmp_path):
    old = os.environ.get("AIVO_CONFIG")
    cfg = {"provider": "openrouter", "api_key": "test-key", "model": "test-model", "base_url": "http://test"}
    path = str(tmp_path / "aivo-test-config.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    os.environ["AIVO_CONFIG"] = path
    yield path
    if old is None:
        del os.environ["AIVO_CONFIG"]
    else:
        os.environ["AIVO_CONFIG"] = old
    if os.path.exists(path):
        os.remove(path)
