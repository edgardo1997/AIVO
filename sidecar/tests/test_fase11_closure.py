"""FASE 11 GTM closure tests (P0).

Covers the four hard requirements that must hold before the phase can be
accepted:

  1. ``first_action`` is recorded centrally on ``ExecutionPipeline`` success
     and deduplicated per ``session_id`` (not a process-global flag).
  2. Every AI workflow transition (create/start/advance/complete/fail/cancel)
     is persisted to SQLite and survives a simulated restart.
  3. Mutating workflow/automation endpoints go through tools → pipeline →
     audit (no direct engine mutation from the API layer).
  4. ``/v1/admin/fleet`` routes exist, are admin-gated and route through the
     governed pipeline.
  5. An AST barrier rejects any new alternative mutation route.
"""

import json
import os
import subprocess
import sys
import tempfile

_temp_product_dir = tempfile.mkdtemp(prefix="sentinel-fase11-tests-")
os.environ["SENTINEL_PRODUCT_DIR"] = _temp_product_dir

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from repositories.database import DatabaseManager
from modules import get_automation_engine, get_ai_workflows
from modules import automations as automations_mod
from modules.product_metrics_probe import reset_probe, get_service, record_first_action


@pytest.fixture(autouse=True)
def reset_metrics_probe():
    reset_probe()
    yield


# ── 1. first_action centralized + dedup per session ─────────────────────────


def test_first_action_deduplicated_per_session():
    reset_probe()
    assert record_first_action(tool_id="a", session_id="closure-s1") is True
    assert record_first_action(tool_id="b", session_id="closure-s1") is False
    assert record_first_action(tool_id="c", session_id="closure-s2") is True
    assert get_service().overview()["time_to_first_action"]["recorded"] >= 2


def test_first_action_recorded_once_via_pipeline(client):
    from modules.jwt_auth import create_access_token

    reset_probe()
    before = get_service().overview()["time_to_first_action"]["recorded"]
    client.headers.pop("X-Test-Token", None)
    headers = {"Authorization": f"Bearer {create_access_token('fase11-test', role='admin')}"}
    resp = client.post("/api/sentinel/cache/clear", headers=headers)
    assert resp.status_code == 200
    assert get_service().overview()["time_to_first_action"]["recorded"] == before + 1
    client.post("/api/sentinel/cache/clear", headers=headers)
    assert get_service().overview()["time_to_first_action"]["recorded"] == before + 1


def test_first_action_recorded_from_v1_execute(client):
    reset_probe()
    resp = client.post("/v1/execute", json={"tool_id": "fleet.status", "params": {}})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    with get_service()._connect() as conn:
        rows = conn.execute("SELECT session_id FROM product_first_actions WHERE session_id = ?", ("test-session",)).fetchall()
    assert len(rows) == 1


# ── 2. workflow transitions persistence + restart ───────────────────────────


def _create_workflow(client, name="deploy", steps=None):
    resp = client.post("/api/sentinel/workflows", json={"name": name, "steps": steps or ["build", "test"]})
    assert resp.status_code == 201
    return resp.json()["workflow_id"]


def _execute_workflow(client, workflow_id, action, **params):
    """Exercise workflow transitions through the production execute router."""
    resp = client.post(
        "/v1/execute",
        json={
            "tool_id": "workflow.execute",
            "params": {"workflow_id": workflow_id, "action": action, **params},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True, resp.json()
    return resp.json()["data"]


def _cancel_workflow(client, workflow_id):
    resp = client.post(
        "/v1/execute",
        json={"tool_id": "workflow.cancel", "params": {"workflow_id": workflow_id}},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True, resp.json()
    return resp.json()["data"]


def _reload_from_db():
    get_ai_workflows()._workflows.clear()
    get_automation_engine()._rules.clear()
    automations_mod._load_from_db()


def test_workflow_transitions_persist_start_step_complete(client):
    workflow_id = _create_workflow(client)

    assert _execute_workflow(client, workflow_id, "start")["started"] is True
    assert _execute_workflow(client, workflow_id, "step", step_result="ok")["executed"] is True
    assert _execute_workflow(client, workflow_id, "complete")["completed"] is True

    _reload_from_db()
    restored = get_ai_workflows()._workflows[workflow_id]
    assert restored["status"] == "completed"
    assert restored["current_step"] == 1


def test_workflow_fail_and_cancel_persist(client):
    workflow_id = _create_workflow(client)
    assert _execute_workflow(client, workflow_id, "start")["started"] is True
    assert _execute_workflow(client, workflow_id, "fail", error="boom")["failed"] is True

    _reload_from_db()
    restored = get_ai_workflows()._workflows[workflow_id]
    assert restored["status"] == "failed"
    assert restored["error"] == "boom"
    assert restored["resume_data"] == {"next_step": 0}

    cancel_id = _create_workflow(client, name="cancel-wf")
    assert _execute_workflow(client, cancel_id, "start")["started"] is True
    assert _cancel_workflow(client, cancel_id)["cancelled"] is True
    _reload_from_db()
    assert get_ai_workflows()._workflows[cancel_id]["status"] == "cancelled"


def test_workflow_state_survives_real_process_restart(client):
    workflow_id = _create_workflow(client, name="restart-state", steps=["collect", "apply"])
    assert _execute_workflow(client, workflow_id, "start")["started"] is True
    assert _execute_workflow(client, workflow_id, "step", step_result="snapshot-42")["executed"] is True
    assert _execute_workflow(client, workflow_id, "fail", error="dependency unavailable")["failed"] is True

    db_path = DatabaseManager().db_path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sidecar = os.path.join(root, "sidecar")
    script = """
import json, os, sys
sys.path[:0] = [os.environ['SENTINEL_TEST_ROOT'], os.environ['SENTINEL_TEST_SIDECAR']]
from repositories.database import DatabaseManager
from modules import get_ai_workflows
from modules import automations
automations.wire_dependencies(DatabaseManager())
state = get_ai_workflows()._workflows[os.environ['SENTINEL_TEST_WORKFLOW_ID']]
print(json.dumps(state, sort_keys=True))
"""
    env = dict(os.environ)
    env.update({
        "SENTINEL_DB_PATH": db_path,
        "AIVO_DB_PATH": db_path,
        "SENTINEL_TEST_ROOT": root,
        "SENTINEL_TEST_SIDECAR": sidecar,
        "SENTINEL_TEST_WORKFLOW_ID": workflow_id,
    })
    completed = subprocess.run(
        [sys.executable, "-c", script], env=env, check=True, capture_output=True, text=True, timeout=20
    )
    restored = json.loads(completed.stdout)
    assert restored["status"] == "failed"
    assert restored["current_step"] == 1
    assert restored["result_data"] == [{"step": 0, "name": "collect", "result": "snapshot-42"}]
    assert restored["error"] == "dependency unavailable"
    assert restored["resume_data"] == {"next_step": 1}


def test_cancelled_workflow_survives_real_process_restart(client):
    workflow_id = _create_workflow(client, name="restart-cancel", steps=["collect", "apply"])
    assert _execute_workflow(client, workflow_id, "start")["started"] is True
    assert _execute_workflow(client, workflow_id, "step", step_result="snapshot-42")["executed"] is True
    assert _cancel_workflow(client, workflow_id)["cancelled"] is True

    db_path = DatabaseManager().db_path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sidecar = os.path.join(root, "sidecar")
    script = """
import json, os, sys
sys.path[:0] = [os.environ['SENTINEL_TEST_ROOT'], os.environ['SENTINEL_TEST_SIDECAR']]
from repositories.database import DatabaseManager
from modules import get_ai_workflows
from modules import automations
automations.wire_dependencies(DatabaseManager())
state = get_ai_workflows()._workflows[os.environ['SENTINEL_TEST_WORKFLOW_ID']]
print(json.dumps(state, sort_keys=True))
"""
    env = dict(os.environ)
    env.update({
        "SENTINEL_DB_PATH": db_path,
        "AIVO_DB_PATH": db_path,
        "SENTINEL_TEST_ROOT": root,
        "SENTINEL_TEST_SIDECAR": sidecar,
        "SENTINEL_TEST_WORKFLOW_ID": workflow_id,
    })
    completed = subprocess.run(
        [sys.executable, "-c", script], env=env, check=True, capture_output=True, text=True, timeout=20
    )
    restored = json.loads(completed.stdout)
    assert restored["status"] == "cancelled"
    assert restored["current_step"] == 1
    assert restored["result_data"] == [{"step": 0, "name": "collect", "result": "snapshot-42"}]
    assert restored["error"] == "cancelled"
    assert restored["resume_data"] == {"next_step": 1}


def test_workflow_delete_persists(client):
    workflow_id = _create_workflow(client)
    assert DatabaseManager().fetchall("SELECT * FROM ai_workflows WHERE workflow_id = ?", (workflow_id,))
    resp = client.delete(f"/api/sentinel/workflows/{workflow_id}")
    assert resp.status_code == 200
    assert DatabaseManager().fetchall("SELECT * FROM ai_workflows WHERE workflow_id = ?", (workflow_id,)) == []


# ── 3. mutations go through tools → pipeline → audit ────────────────────────


def test_automation_creation_produces_audit_entry(client):
    from modules.audit import _svc as audit_svc

    before = audit_svc.get_log()["total"]
    rule_id = "audit-rule-1"
    try:
        resp = client.post(
            "/api/sentinel/automations",
            json={"rule_id": rule_id, "condition": "cpu>90", "action": "alert"},
        )
        assert resp.status_code == 201
        entries = audit_svc.get_log(action_filter="tool_execution").get("entries", [])
        assert any("automation.rules.add" in e.get("details", "") for e in entries)
        assert audit_svc.get_log()["total"] > before
    finally:
        client.delete(f"/api/sentinel/automations/{rule_id}")


def test_workflow_creation_produces_audit_entry(client):
    from modules.audit import _svc as audit_svc

    workflow_id = None
    try:
        workflow_id = _create_workflow(client)
        entries = audit_svc.get_log(action_filter="tool_execution").get("entries", [])
        assert any("workflow.create" in e.get("details", "") for e in entries)
    finally:
        if workflow_id:
            client.delete(f"/api/sentinel/workflows/{workflow_id}")


def test_workflow_execute_through_tool_persists(client):
    workflow_id = _create_workflow(client)
    assert _execute_workflow(client, workflow_id, "start")["started"] is True
    assert _execute_workflow(client, workflow_id, "step", step_result="ok")["executed"] is True
    _reload_from_db()
    restored = get_ai_workflows()._workflows[workflow_id]
    assert restored["status"] == "running"
    assert restored["current_step"] == 1
    client.delete(f"/api/sentinel/workflows/{workflow_id}")


# ── 4. /v1/admin/fleet routes ───────────────────────────────────────────────


def _all_app_paths(app):
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            for ctx in route.effective_route_contexts():
                p = getattr(ctx, "path", None)
                if p:
                    paths.add(p)
        else:
            p = getattr(route, "path", None)
            if p:
                paths.add(p)
    return paths


def test_admin_fleet_routes_exist():
    from main import app

    paths = _all_app_paths(app)
    expected = {
        "/v1/admin/fleet/status",
        "/v1/admin/fleet/devices",
        "/v1/admin/fleet/devices/{device_id}",
        "/v1/admin/fleet/pairing/generate",
        "/v1/admin/fleet/pairing/revoke",
        "/v1/admin/fleet/remote/toggle",
        "/v1/admin/fleet/sync/log",
    }
    assert expected <= paths


def test_admin_fleet_status_and_devices(client):
    resp = client.get("/v1/admin/fleet/status")
    assert resp.status_code == 200
    assert "remote_enabled" in resp.json()

    resp = client.get("/v1/admin/fleet/devices")
    assert resp.status_code == 200
    assert "devices" in resp.json()


def test_admin_fleet_device_crud(client):
    device_id = "fase11-node-1"
    resp = client.post(
        "/v1/admin/fleet/devices",
        json={"device_id": device_id, "name": "Fase 11 Node", "device_type": "node"},
    )
    assert resp.status_code == 201

    resp = client.get(f"/v1/admin/fleet/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["device_id"] == device_id

    resp = client.put(
        f"/v1/admin/fleet/devices/{device_id}",
        json={"notes": "updated"},
    )
    assert resp.status_code == 200

    resp = client.delete(f"/v1/admin/fleet/devices/{device_id}")
    assert resp.status_code == 200

    resp = client.get(f"/v1/admin/fleet/devices/{device_id}")
    assert resp.status_code == 404


def test_admin_fleet_requires_admin(client):
    from fastapi import Request, HTTPException
    from starlette.datastructures import State
    from modules.auth import require_admin_identity, IdentityContext

    viewer = IdentityContext(
        user_id="viewer-user",
        username="Viewer",
        role="viewer",
        permissions=frozenset({"view"}),
        authentication_method="test",
        is_authenticated=True,
        is_local=True,
    )
    req = Request({"type": "http", "method": "GET", "path": "/v1/admin/fleet/status", "headers": []})
    req.state.identity = viewer
    with pytest.raises(HTTPException) as exc:
        require_admin_identity(req)
    assert exc.value.status_code == 403


def test_admin_fleet_route_invokes_admin_gate(client, monkeypatch):
    import routers.v1.admin_fleet as admin_fleet
    from fastapi import HTTPException

    def deny(request):
        raise HTTPException(status_code=403, detail="Administrator identity required")

    monkeypatch.setattr(admin_fleet, "require_admin_identity", deny)
    resp = client.get("/v1/admin/fleet/status")
    assert resp.status_code == 403


# ── 5. AST barrier: no alternative mutation route ───────────────────────────


def test_no_direct_engine_mutation_outside_persistence_module():
    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    forbidden = (
        "get_engine().add_rule",
        "get_engine().remove_rule",
        "get_engine().trigger_rule",
        "get_workflows().create",
        "get_workflows().start",
        "get_workflows().complete",
        "get_workflows().fail",
        "get_workflows().delete",
        "_workflows[workflow_id]",
        "_rules[rule_id]",
    )
    authorized = {
        "sidecar/modules/automations.py",
    }
    violations = []
    for d in (ROOT / "sidecar" / "modules", ROOT / "sidecar" / "routers"):
        for pyfile in d.rglob("*.py"):
            rel = str(pyfile.relative_to(ROOT)).replace("\\", "/")
            if rel in authorized:
                continue
            content = pyfile.read_text(encoding="utf-8")
            for frag in forbidden:
                if frag in content:
                    violations.append(f"{rel}: contains '{frag}'")
    assert not violations, "Alternative engine-mutation routes found:\n" + "\n".join(violations)
