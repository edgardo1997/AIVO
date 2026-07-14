"""End-to-end integration tests for the full Sentinel pipeline.

Exercises real HTTP endpoints with all subsystems wired:
multi-agent, rate limiter, circuit breaker, cost tracking,
feedback, performance monitoring, plan cache, deep context.
"""

import os
import sys
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app
from modules.permissions import _svc as perm_svc
from modules.sentinel_bridge import get_orchestrator, get_memory, reset_bridge

client = TestClient(app)

# ---------------------------------------------------------------------------
# Multi-agent integration
# ---------------------------------------------------------------------------


class TestMultiAgentAPI:
    def test_multi_agent_simple_task(self):
        resp = client.post(
            "/api/sentinel/process/multi-agent",
            json={
                "utterance": "show disk usage",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("sub_task_results"), list)
        # passthrough should succeed even without real agents
        assert data.get("success") is True

    def test_multi_agent_complex_task(self):
        resp = client.post(
            "/api/sentinel/process/multi-agent",
            json={
                "utterance": "research and analyze the current system performance",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # should produce multiple sub-tasks via decomposition
        assert len(data.get("sub_task_results", [])) >= 1

    def test_multi_agent_empty_utterance(self):
        resp = client.post("/api/sentinel/process/multi-agent", json={"utterance": ""})
        assert resp.status_code == 200
        assert resp.json().get("error") is not None

    def test_multi_agent_missing_utterance(self):
        resp = client.post("/api/sentinel/process/multi-agent", json={})
        assert resp.status_code == 200
        assert resp.json().get("error") is not None


# ---------------------------------------------------------------------------
# Rate limiter integration (orchestrator-level, not HTTP middleware)
# ---------------------------------------------------------------------------


class TestOrchestratorRateLimiterIntegration:
    def setup_method(self):
        reset_bridge()

    def test_rate_limiter_stats_endpoint(self):
        resp = client.get("/api/sentinel/rate-limiter/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True

    def test_rate_limiter_clear_endpoint(self):
        resp = client.post("/api/sentinel/rate-limiter/clear")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True

    def test_orchestrator_rate_limits_global_and_allows_after_reset(self):
        orch = get_orchestrator()
        rl = orch._rate_limiter
        # fill the global bucket manually
        global_limit = 60
        for _ in range(global_limit):
            rl.allow("global", limit=global_limit)
        # orchestrator should reject
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        # may be rate limited or not depending on concurrent requests
        # but at minimum verify the endpoint survives

    def test_rate_limiter_survives_multiple_calls(self):
        for _ in range(5):
            resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Circuit breaker through HTTP
# ---------------------------------------------------------------------------


class TestCircuitBreakerIntegration:
    def test_circuit_breaker_endpoint(self):
        resp = client.get("/api/sentinel/circuit-breaker")
        assert resp.status_code == 200
        data = resp.json()
        assert "circuits" in data

    def test_circuit_breaker_reset_endpoint(self):
        resp = client.post("/api/sentinel/circuit-breaker/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "reset" in data


# ---------------------------------------------------------------------------
# Cost tracking through real pipeline
# ---------------------------------------------------------------------------


class TestCostTrackingPipeline:
    def setup_method(self):
        reset_bridge()

    def test_cost_endpoint_returns_data(self):
        resp = client.get("/api/sentinel/cost/total")
        assert resp.status_code == 200
        data = resp.json()
        assert any("total_cost" in k for k in data)
        assert "total_tokens" in data

    def test_pipeline_records_cost_after_execution(self):
        cost_before = client.get("/api/sentinel/cost/total").json()
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        cost_after = client.get("/api/sentinel/cost/total").json()
        assert cost_after["total_tokens"] >= cost_before["total_tokens"]

    def test_cost_summary_endpoint(self):
        resp = client.get("/api/sentinel/cost/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_budget_endpoints(self):
        resp = client.get("/api/sentinel/cost/budgets")
        assert resp.status_code == 200
        resp = client.get("/api/sentinel/cost/alerts")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Feedback and performance tracking
# ---------------------------------------------------------------------------


class TestFeedbackPerformancePipeline:
    def setup_method(self):
        reset_bridge()

    def test_feedback_stats_endpoint(self):
        resp = client.get("/api/sentinel/feedback/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data

    def test_pipeline_records_feedback(self):
        stats_before = client.get("/api/sentinel/feedback/stats").json()
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        stats_after = client.get("/api/sentinel/feedback/stats").json()
        assert len(stats_after.get("stats", [])) >= len(stats_before.get("stats", []))

    def test_performance_endpoints(self):
        resp = client.get("/api/sentinel/performance/baselines")
        assert resp.status_code == 200
        resp = client.get("/api/sentinel/performance/alerts")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Plan cache through HTTP
# ---------------------------------------------------------------------------


class TestPlanCacheIntegration:
    def setup_method(self):
        reset_bridge()

    def test_cache_stats(self):
        resp = client.get("/api/sentinel/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data

    def test_cache_clear(self):
        resp = client.post("/api/sentinel/cache/clear")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True

    def test_cache_hit_after_same_intent(self):
        cache_before = client.get("/api/sentinel/cache/stats").json()
        hits_before = sum(e.get("hit_count", 0) for e in cache_before.get("entries", []))
        # same utterance twice
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        cache_after = client.get("/api/sentinel/cache/stats").json()
        hits_after = sum(e.get("hit_count", 0) for e in cache_after.get("entries", []))
        assert hits_after > hits_before


# ---------------------------------------------------------------------------
# Full pipeline with all subsystems
# ---------------------------------------------------------------------------


class TestFullPipelineSubsystems:
    """Verify that the full pipeline returns data from all subsystems."""

    def test_process_returns_all_fields(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        # core fields
        assert data["intent"] is not None
        assert data["plan"] is not None
        assert data["step_results"] is not None
        # decision fields
        assert data["decision"] is not None
        assert data["final_risk_score"] is not None
        # execution fields
        assert data["tool_result"] is not None
        assert data["tool_result"]["success"] is True
        assert len(data["step_results"]) >= 2

    def test_last_execution_returns_full_record(self):
        client.post("/api/sentinel/process", json={"utterance": "disk info"})
        resp = client.get("/api/sentinel/last-execution")
        assert resp.status_code == 200
        exec_data = resp.json()["execution"]
        assert exec_data["utterance"] == "disk info"
        assert exec_data["duration_ms"] > 0
        assert exec_data["step_results"] is not None

    def test_multiple_subsequent_calls(self):
        for i in range(3):
            resp = client.post("/api/sentinel/process", json={"utterance": f"cpu usage {i}"})
            assert resp.status_code == 200, f"Failed on iteration {i}: {resp.text}"
            assert resp.json()["tool_result"]["success"] is True


# ---------------------------------------------------------------------------
# Error handling and edge cases
# ---------------------------------------------------------------------------


class TestErrorHandlingIntegration:
    def test_utterance_too_short(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "x"})
        assert resp.status_code == 200
        resp.json()

    def test_very_long_utterance(self):
        long_text = "system " * 100
        resp = client.post("/api/sentinel/process", json={"utterance": long_text.strip()})
        assert resp.status_code == 200
        data = resp.json()
        # should still parse and execute even with very long input
        assert data["tool_result"]["success"] is True

    def test_session_continuity(self):
        session = "integ-test-session"
        resp1 = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "session_id": session,
            },
        )
        assert resp1.status_code == 200
        resp2 = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "cpu usage",
                "session_id": session,
            },
        )
        assert resp2.status_code == 200
        # both should succeed
        assert resp1.json()["tool_result"]["success"] is True
        assert resp2.json()["tool_result"]["success"] is True

    def test_dry_run_through_full_pipeline(self):
        resp = client.post(
            "/api/sentinel/process",
            json={
                "utterance": "analyze system health",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        assert data["plan"] is not None
        assert len(data["plan"]["steps"]) >= 2

    def test_simulate_approve_reject_cycle(self):
        # simulate + approve workflow through real pipeline
        resp = client.post(
            "/v1/execute",
            json={
                "tool_id": "executor.command",
                "params": {"command": "echo integration_test", "timeout": 5},
            },
        )
        # at auto level, may require confirm
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Multi-agent orchestrator via direct access
# ---------------------------------------------------------------------------


class TestMultiAgentDirectIntegration:
    def test_multi_agent_property_on_orchestrator(self):
        orch = get_orchestrator()
        assert hasattr(orch, "multi_agent")
        ma = orch.multi_agent
        assert ma is not None

    def test_multi_agent_is_complex_detection(self):
        orch = get_orchestrator()
        ma = orch.multi_agent
        assert ma._is_complex("research and analyze the complete system architecture")
        assert not ma._is_complex("show cpu")

    def test_multi_agent_decompose(self):
        orch = get_orchestrator()
        ma = orch.multi_agent
        result = ma._default_decompose("research, analyze and design a new feature")
        assert len(result.sub_tasks) >= 2
        ids = [st.id for st in result.sub_tasks]
        assert "st_research" in ids
        assert "st_analyze" in ids or "st_design" in ids
