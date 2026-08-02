"""Unit tests for ProductMetricsService (FASE 8)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from sentinel.product.metrics import (
    ProductMetricsService,
    EVENT_FIRST_ACTION,
    EVENT_ACTION_COMPLETED,
    EVENT_UX_ERROR,
    EVENT_AUTOMATION_CREATED,
    EVENT_MODE_USED,
    EVENT_SESSION,
)


@pytest.fixture
def metrics(tmp_path):
    clock = {"now": 1_700_000_000.0}

    def tick():
        return clock["now"]

    service = ProductMetricsService(db_path=str(tmp_path / "product_metrics.db"), clock=tick)
    return service, clock


def test_record_and_overview_empty(metrics):
    service, _clock = metrics
    overview = service.overview()
    assert overview["actions_completed"] == 0
    assert overview["ux_errors"] == 0


def test_record_first_action_average(metrics):
    service, clock = metrics
    clock["now"] += 0
    service.record(EVENT_FIRST_ACTION, {"latency_ms": 1200})
    service.record(EVENT_FIRST_ACTION, {"latency_ms": 800})
    overview = service.overview()
    assert overview["time_to_first_action"]["recorded"] == 2
    assert overview["time_to_first_action"]["avg_ms"] == 1000.0


def test_record_action_and_error(metrics):
    service, clock = metrics
    service.record(EVENT_ACTION_COMPLETED, {"action": "optimize"})
    service.record(EVENT_UX_ERROR, {"source": "ControlCenter"})
    overview = service.overview()
    assert overview["actions_completed"] == 1
    assert overview["ux_errors"] == 1
    assert overview["success_rate"] == 0.5


def test_record_automation(metrics):
    service, clock = metrics
    service.record(EVENT_AUTOMATION_CREATED, {"name": "workflow-1"})
    assert service.overview()["automations_created"] == 1


def test_mode_usage_aggregation(metrics):
    service, clock = metrics
    service.record(EVENT_MODE_USED, {"mode": "developer"})
    service.record(EVENT_MODE_USED, {"mode": "developer"})
    service.record(EVENT_MODE_USED, {"mode": "gaming"})
    overview = service.overview()
    assert overview["usage_by_mode"] == {"developer": 2, "gaming": 1}


def test_retention_days(metrics):
    service, clock = metrics
    service.record(EVENT_SESSION)
    overview = service.overview()
    assert overview["retention"]["active_days"] == 1
    assert overview["retention"]["ratio"] > 0


def test_daily_timeseries(metrics):
    service, clock = metrics
    service.record(EVENT_SESSION)
    service.record(EVENT_ACTION_COMPLETED, {"action": "x"})
    overview = service.overview()
    assert len(overview["retention"]["daily"]) >= 1
    assert overview["retention"]["daily"][-1]["actions"] >= 1


def test_invalid_event_type_rejected(metrics):
    service, _clock = metrics
    result = service.record("")
    assert result["success"] is False
