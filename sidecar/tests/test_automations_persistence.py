"""Persistence, export/import and activation-metric tests (FASE 11 GTM)."""

import os
import sys
import tempfile

_temp_product_dir = tempfile.mkdtemp(prefix="sentinel-automations-tests-")
os.environ["SENTINEL_PRODUCT_DIR"] = _temp_product_dir

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from repositories.database import DatabaseManager
from modules import get_automation_engine, get_ai_workflows
from modules import automations as automations_mod
from modules.product_metrics_probe import (
    reset_probe,
    record_session,
    record_first_action,
    record_automation_created,
    get_service,
)


@pytest.fixture(autouse=True)
def reset_metrics_probe():
    reset_probe()
    yield


def test_session_recorded_once():
    reset_probe()
    before = get_service().overview()["sessions"]
    assert record_session() is True
    assert record_session() is False
    assert get_service().overview()["sessions"] == before + 1


def test_first_action_recorded_once():
    reset_probe()
    before = get_service().overview()["time_to_first_action"]["recorded"]
    assert record_first_action("cache.clear", session_id="metrics-session-1") is True
    assert record_first_action("cache.clear", session_id="metrics-session-1") is False
    overview = get_service().overview()
    assert overview["time_to_first_action"]["recorded"] == before + 1
    assert overview["time_to_first_action"]["avg_ms"] is not None


def test_first_action_is_durable_across_metric_service_restart(tmp_path):
    from sentinel.product.metrics import ProductMetricsService

    db_path = str(tmp_path / "product_metrics.db")
    first = ProductMetricsService(db_path=db_path)
    assert first.record_first_action_once("durable-session", {"tool_id": "system.info", "latency_ms": 1}) is True

    restarted = ProductMetricsService(db_path=db_path)
    assert restarted.record_first_action_once("durable-session", {"tool_id": "system.info", "latency_ms": 2}) is False
    assert restarted.overview()["time_to_first_action"]["recorded"] == 1


def test_first_action_hooks_pipeline_execution(client):
    reset_probe()
    resp = client.post("/api/sentinel/cache/clear")
    assert resp.status_code == 200
    client.post("/api/sentinel/cache/clear")
    with get_service()._connect() as conn:
        rows = conn.execute("SELECT session_id FROM product_first_actions WHERE session_id = ?", ("test-session",)).fetchall()
    assert len(rows) == 1


def test_automation_created_metric_via_api(client):
    reset_probe()
    rule_id = "metric-rule-1"
    try:
        resp = client.post(
            "/api/sentinel/automations",
            json={"rule_id": rule_id, "condition": "cpu>90", "action": "alert"},
        )
        assert resp.status_code == 201
        assert get_service().overview()["automations_created"] >= 1
    finally:
        client.delete(f"/api/sentinel/automations/{rule_id}")


def test_trigger_creation_records_automation_metric(client):
    reset_probe()
    trigger_id = "metric-trigger-1"
    try:
        resp = client.post(
            "/v1/triggers",
            json={"id": trigger_id, "conditions": [{"metric": "cpu_percent", "operator": "gt", "value": 90}]},
        )
        assert resp.status_code == 201
        assert get_service().overview()["automations_created"] >= 1
    finally:
        client.delete(f"/v1/triggers/{trigger_id}")


def test_rule_crud_and_persistence(client):
    rule_id = "persist-rule-1"
    client.post(
        "/api/sentinel/automations",
        json={"rule_id": rule_id, "condition": "cpu>80", "action": "notify"},
    )
    rows = DatabaseManager().fetchall("SELECT * FROM automation_rules WHERE rule_id = ?", (rule_id,))
    assert len(rows) == 1
    assert rows[0]["action"] == "notify"

    get_automation_engine()._rules.clear()
    automations_mod._load_from_db()
    assert rule_id in get_automation_engine()._rules
    assert get_automation_engine()._rules[rule_id]["condition"] == "cpu>80"

    resp = client.delete(f"/api/sentinel/automations/{rule_id}")
    assert resp.status_code == 200
    assert DatabaseManager().fetchall("SELECT * FROM automation_rules WHERE rule_id = ?", (rule_id,)) == []


def test_duplicate_rule_conflict(client):
    rule_id = "dup-rule-1"
    client.post("/api/sentinel/automations", json={"rule_id": rule_id, "condition": "a", "action": "b"})
    resp = client.post("/api/sentinel/automations", json={"rule_id": rule_id, "condition": "c", "action": "d"})
    assert resp.status_code == 409
    client.delete(f"/api/sentinel/automations/{rule_id}")


def test_workflow_crud_and_persistence(client):
    resp = client.post(
        "/api/sentinel/workflows",
        json={"name": "deploy", "steps": ["build", "test", "release"]},
    )
    assert resp.status_code == 201
    workflow_id = resp.json()["workflow_id"]

    rows = DatabaseManager().fetchall("SELECT * FROM ai_workflows WHERE workflow_id = ?", (workflow_id,))
    assert len(rows) == 1

    get_ai_workflows()._workflows.clear()
    automations_mod._load_from_db()
    assert workflow_id in get_ai_workflows()._workflows
    assert get_ai_workflows()._workflows[workflow_id]["steps"] == ["build", "test", "release"]

    resp = client.delete(f"/api/sentinel/workflows/{workflow_id}")
    assert resp.status_code == 200
    assert DatabaseManager().fetchall("SELECT * FROM ai_workflows WHERE workflow_id = ?", (workflow_id,)) == []


def test_export_import_roundtrip(client):
    rule_id = "share-rule-1"
    workflow_name = "cleanup"
    client.post("/api/sentinel/automations", json={"rule_id": rule_id, "condition": "mem>90", "action": "kill"})
    wf_resp = client.post("/api/sentinel/workflows", json={"name": workflow_name, "steps": ["scan", "purge"]})
    workflow_id = wf_resp.json()["workflow_id"]

    exported = client.get("/api/sentinel/automations/export").json()
    assert exported["format"] == "sentinel-automations"
    assert exported["version"] == 1
    assert any(r["rule_id"] == rule_id for r in exported["automation_rules"])
    assert any(w["workflow_id"] == workflow_id for w in exported["workflows"])

    import_payload = {
        "automation_rules": [
            {"rule_id": rule_id, "condition": "mem>90", "action": "kill"},
            {"rule_id": "imported-rule-1", "condition": "disk>95", "action": "notify"},
        ],
        "workflows": [
            {"workflow_id": workflow_id, "name": workflow_name, "steps": ["scan", "purge"]},
            {"workflow_id": "imported-wf-1", "name": "archive", "steps": ["zip", "upload"]},
        ],
    }
    resp = client.post("/api/sentinel/automations/import", json=import_payload).json()
    assert resp["imported_rules"] == 1
    assert resp["skipped_rules"] == 1
    assert resp["imported_workflows"] == 1
    assert resp["skipped_workflows"] == 1

    listing = client.get("/api/sentinel/automations").json()
    rule_ids = {r["id"] for r in listing["automation_rules"]}
    workflow_ids = {w["id"] for w in listing["workflows"]}
    assert rule_id in rule_ids
    assert "imported-rule-1" in rule_ids
    assert workflow_id in workflow_ids
    assert "imported-wf-1" in workflow_ids

    client.delete(f"/api/sentinel/automations/{rule_id}")
    client.delete("/api/sentinel/automations/imported-rule-1")
    client.delete(f"/api/sentinel/workflows/{workflow_id}")
    client.delete("/api/sentinel/workflows/imported-wf-1")


def test_import_rejects_bad_payload(client):
    resp = client.post("/api/sentinel/automations/import", json={"automation_rules": "nope"})
    assert resp.status_code == 400


def test_rule_created_through_tool_persists(client):
    import asyncio

    from modules.auth import IdentityContext
    from modules.sentinel_bridge_helpers import _pipeline_execute

    rule_id = "tool-rule-1"
    try:
        result = asyncio.run(
            _pipeline_execute(
                "automation.rules.add",
                {"rule_id": rule_id, "condition": "cpu>80", "action": "notify"},
                {"identity": IdentityContext.test_identity().to_dict()},
            )
        )
        assert result.success is True
        rows = DatabaseManager().fetchall("SELECT * FROM automation_rules WHERE rule_id = ?", (rule_id,))
        assert len(rows) == 1
        assert rows[0]["condition"] == "cpu>80"
    finally:
        client.delete(f"/api/sentinel/automations/{rule_id}")


def test_bound_rule_rejects_trigger_without_revalidated_context(client):
    import asyncio

    from modules.auth import IdentityContext
    from modules import automations as automations_mod
    from modules.sentinel_bridge_helpers import _pipeline_execute

    rule_id = "bound-rule-1"
    binding = {"identity": IdentityContext.test_identity().to_dict()}
    automations_mod.ensure_wired()

    asyncio.run(
        _pipeline_execute(
            "automation.rules.add",
            {"rule_id": rule_id, "condition": "cpu>90", "action": "alert"},
            binding,
        )
    )
    owner = DatabaseManager().fetchone(
        "SELECT owner_session_id, owner_identity_hash FROM automation_rules WHERE rule_id = ?", (rule_id,)
    )
    assert owner and (owner["owner_session_id"] or owner["owner_identity_hash"])

    engine = get_automation_engine()
    stored = engine._rules[rule_id]
    assert stored.get("owner_session_id") or stored.get("owner_identity_hash")

    # The original identity re-validates the binding and trigger succeeds.
    try:
        automations_mod._mod_request_ctx.set(
            automations_mod._RequestBinding(
                session_id=stored.get("owner_session_id", ""),
                identity_hash=stored.get("owner_identity_hash", ""),
            )
        )
        ok = engine.trigger_rule(rule_id, session_id=stored.get("owner_session_id", ""))
        assert ok.get("triggered") is True
    finally:
        automations_mod._mod_request_ctx.set(None)

    # A fresh, unrelated identity cannot fire the bound automation (fail-closed).
    get_automation_engine()._rules[rule_id]["trigger_count"] = 0
    try:
        automations_mod._mod_request_ctx.set(automations_mod._RequestBinding(session_id="", identity_hash="unrelated"))
        blocked = engine.trigger_rule(rule_id, session_id="other-session")
        assert blocked.get("triggered") is False
        assert blocked.get("revalidation_required") is True
    finally:
        automations_mod._mod_request_ctx.set(None)

    client.delete(f"/api/sentinel/automations/{rule_id}")


def test_restored_unbound_rule_still_triggers(client):
    # Rules without an owner binding retain legacy behavior and always trigger.
    import asyncio

    from modules.auth import IdentityContext
    from modules.sentinel_bridge_helpers import _pipeline_execute

    rule_id = "legacy-rule-1"
    try:
        asyncio.run(
            _pipeline_execute(
                "automation.rules.add",
                {"rule_id": rule_id, "condition": "cpu>50", "action": "notify"},
                {"identity": IdentityContext.test_identity().to_dict()},
            )
        )
        DatabaseManager().execute(
            "UPDATE automation_rules SET owner_session_id = '', owner_identity_hash = '' WHERE rule_id = ?",
            (rule_id,),
        )
        DatabaseManager().commit()
        get_automation_engine()._rules.pop(rule_id, None)
        automations_mod._load_from_db()
        ok = get_automation_engine().trigger_rule(rule_id)
        assert ok.get("triggered") is True
    finally:
        client.delete(f"/api/sentinel/automations/{rule_id}")
