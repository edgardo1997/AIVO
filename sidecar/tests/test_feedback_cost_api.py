import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from modules.sentinel_bridge import get_orchestrator, reset_bridge

client = TestClient(app)


class TestFeedbackAPI:
    def setup_method(self):
        reset_bridge()

    def test_feedback_stats_empty(self):
        resp = client.get("/api/sentinel/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data

    def test_feedback_stats_with_data(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")
        resp = client.post("/api/sentinel/process", json={"utterance": "show system info"})
        assert resp.status_code == 200
        resp2 = client.get("/api/sentinel/feedback/stats")
        assert resp2.status_code == 200
        data = resp2.json()
        assert isinstance(data["stats"], list)

    def test_feedback_records(self):
        resp = client.get("/api/sentinel/feedback/records")
        assert resp.status_code == 200
        data = resp.json()
        assert "records" in data

    def test_feedback_invalid_task_type(self):
        resp = client.get("/api/sentinel/feedback/stats?task_type=invalid")
        assert resp.status_code == 400


class TestCostAPI:
    def setup_method(self):
        reset_bridge()

    def test_cost_summary_empty(self):
        resp = client.get("/api/sentinel/cost/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_cost_total(self):
        resp = client.get("/api/sentinel/cost/total")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_cost_usd" in data
        assert "total_tokens" in data

    def test_budgets_crud(self):
        resp = client.post("/api/sentinel/cost/budgets", json={
            "name": "test-budget",
            "max_cost_usd": 50.0,
            "period": "monthly",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp2 = client.get("/api/sentinel/cost/budgets")
        assert resp2.status_code == 200
        budgets = resp2.json()["budgets"]
        assert any(b["name"] == "test-budget" for b in budgets)

        resp3 = client.delete("/api/sentinel/cost/budgets/test-budget")
        assert resp3.status_code == 200

        resp4 = client.get("/api/sentinel/cost/budgets")
        assert not any(b["name"] == "test-budget" for b in resp4.json()["budgets"])

    def test_cost_alerts(self):
        resp = client.get("/api/sentinel/cost/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    def test_budget_missing_name(self):
        resp = client.post("/api/sentinel/cost/budgets", json={
            "max_cost_usd": 10.0,
        })
        assert resp.status_code == 400
