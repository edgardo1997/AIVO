import os
import sqlite3
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock
import pytest

from sentinel.core.cost_tracker import (
    CostTracker,
    CostRecord,
    CostSummary,
    BudgetConfig,
    BudgetAlert,
    MODEL_PRICING,
)
from sentinel.core.model_router import TaskType


class TestCostTrackerBasic:
    def test_close_releases_worker_connections_and_allows_reopen(self, tmp_path):
        tracker = CostTracker(db_path=str(tmp_path / "threaded-cost.db"))
        worker_connections = []

        def open_connection():
            connection = tracker._get_conn()
            connection.execute("SELECT 1")
            worker_connections.append(connection)

        worker = threading.Thread(target=open_connection)
        worker.start()
        worker.join()

        tracker.close()

        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            worker_connections[0].execute("SELECT 1")
        assert tracker.get_total_cost() == 0.0

    def test_record_and_query(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "cost.db"))
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 100, 20)
        ct.record_cost("ollama", "llama3", TaskType.LOCAL, 50, 10)
        summaries = ct.get_cost_summary()
        assert len(summaries) == 2

    def test_total_cost(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "cost2.db"))
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 1000, 200)
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 500, 100)
        total = ct.get_total_cost("openrouter")
        assert total > 0

    def test_total_tokens(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "cost3.db"))
        ct.record_cost("ollama", "llama3", TaskType.LOCAL, 100, 20)
        ct.record_cost("ollama", "llama3", TaskType.LOCAL, 200, 30)
        assert ct.get_total_tokens("ollama") == 350

    def test_filter_by_provider(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "cost4.db"))
        ct.record_cost("ollama", "llama3", TaskType.QUICK, 10, 5)
        ct.record_cost("openrouter", "gpt-4o", TaskType.CODE, 100, 20)
        summaries = ct.get_cost_summary(provider_id="ollama")
        assert len(summaries) == 1
        assert summaries[0].provider_id == "ollama"

    def test_filter_by_since(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "cost5.db"))
        ct.record_cost("ollama", "llama3", TaskType.QUICK, 10, 5)
        from datetime import datetime, timezone, timedelta

        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        summaries = ct.get_cost_summary(since=future)
        assert len(summaries) == 0


class TestPricing:
    def test_get_model_price_known(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/p.db")
        assert ct.get_model_price("ollama", "llama3") == 0.0

    def test_get_model_price_fallback_to_default(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/p2.db")
        assert ct.get_model_price("github_models", "unknown-model") == 0.00015

    def test_get_model_price_unknown_provider(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/p3.db")
        assert ct.get_model_price("nonexistent", "model") == 0.0

    def test_estimate_cost_zero_price(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/p4.db")
        assert ct.estimate_cost("ollama", "llama3", 1000, 500) == 0.0

    def test_estimate_cost_with_price(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/p5.db")
        cost = ct.estimate_cost("github_models", "gpt-4o-mini", 1000, 500)
        assert cost == pytest.approx(0.000225, rel=0.001)


class TestBudget:
    def test_set_and_get_budget(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b.db")
        ct.set_budget(BudgetConfig(name="test", max_cost_usd=10.0, period="monthly"))
        budgets = ct.get_budgets()
        assert len(budgets) == 1
        assert budgets[0].name == "test"
        assert budgets[0].max_cost_usd == 10.0

    def test_delete_budget(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b2.db")
        ct.set_budget(BudgetConfig(name="del", max_cost_usd=5.0))
        ct.delete_budget("del")
        assert len(ct.get_budgets()) == 0

    def test_budget_not_exceeded_no_alert(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b3.db")
        ct.set_budget(BudgetConfig(name="no_alarm", max_cost_usd=100.0))
        alerts = ct.check_budgets()
        assert len(alerts) == 0

    def test_budget_exceeded_triggers_alert(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b4.db")
        ct.set_budget(BudgetConfig(name="alarm", max_cost_usd=0.000001))
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 100000, 50000)
        alerts = ct.check_budgets()
        assert len(alerts) == 1
        assert alerts[0].budget_name == "alarm"
        assert alerts[0].current_cost > 0

    def test_budget_disabled_no_alert(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b5.db")
        ct.set_budget(BudgetConfig(name="disabled", max_cost_usd=0.000001, enabled=False))
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 100000, 50000)
        alerts = ct.check_budgets()
        assert len(alerts) == 0

    def test_budget_token_limit(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/b6.db")
        ct.set_budget(BudgetConfig(name="tok", max_cost_usd=100.0, max_tokens=10))
        ct.record_cost("ollama", "llama3", TaskType.QUICK, 10, 5)
        alerts = ct.check_budgets()
        assert len(alerts) == 1
        assert alerts[0].max_tokens == 10


class TestPersistentCosts:
    def test_costs_survive_reinit(self, tmp_path):
        db = str(tmp_path / "survive.db")
        ct1 = CostTracker(db_path=db)
        ct1.record_cost("ollama", "llama3", TaskType.QUICK, 100, 20)
        ct1.record_cost("openrouter", "gpt-4o", TaskType.CODE, 500, 100)

        ct2 = CostTracker(db_path=db)
        assert ct2.get_total_cost("ollama") == ct1.get_total_cost("ollama")
        assert ct2.get_total_cost("openrouter") == ct1.get_total_cost("openrouter")
        summaries = ct2.get_cost_summary()
        assert len(summaries) == 2

    def test_budgets_survive_reinit(self, tmp_path):
        db = str(tmp_path / "budget_survive.db")
        ct1 = CostTracker(db_path=db)
        ct1.set_budget(BudgetConfig(name="persist", max_cost_usd=50.0, period="monthly"))

        ct2 = CostTracker(db_path=db)
        budgets = ct2.get_budgets()
        assert len(budgets) == 1
        assert budgets[0].name == "persist"
        assert budgets[0].max_cost_usd == 50.0


class TestRealTokenTracking:
    def test_record_cost_with_estimated_flag(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path / "est.db"))
        r1 = ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 100, 20, estimated=True)
        r2 = ct.record_cost("ollama", "llama3", TaskType.LOCAL, 50, 10, estimated=False)
        assert r1.estimated is True
        assert r2.estimated is False
        # verify persistence
        conn = ct._get_conn()
        rows = conn.execute("SELECT estimated FROM cost_records ORDER BY id").fetchall()
        assert rows[0]["estimated"] == 1
        assert rows[1]["estimated"] == 0

    def test_record_cost_defaults_estimated_true(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/def_est.db")
        r = ct.record_cost("ollama", "llama3", TaskType.QUICK, 100, 20)
        assert r.estimated is True

    def test_record_cost_with_real_tokens(self, tmp_path):
        ct = CostTracker(db_path=str(tmp_path) + "/real.db")
        ct.record_cost("openrouter", "gpt-4o", TaskType.QUICK, 150, 50, estimated=False)
        summary = ct.get_cost_summary()
        assert len(summary) == 1
        assert summary[0].total_prompt_tokens == 150
        assert summary[0].total_completion_tokens == 50
        assert summary[0].total_tokens == 200
