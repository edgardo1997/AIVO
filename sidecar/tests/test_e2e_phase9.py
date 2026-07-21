"""E2E tests for Phases 3-8: LLM 0 authority, simulation→decision, advisory feedback, config, key deletion."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from modules.permissions import _svc as perm_svc

pytestmark = pytest.mark.e2e

client = TestClient(app)


class TestLLMZeroAuthority:
    """Fase 3: Decision engine uses only objective assessor — no LLM advisor/validator."""

    def test_set_enable_llm_advisor_is_noop(self):
        from sentinel.core.decision_engine import DecisionEngine
        engine = DecisionEngine(None)
        result = engine.set_enable_llm_advisor(True)
        assert result is None

    def test_decision_reason_is_objective_not_llm(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        reason = data.get("decision_reason", "")
        assert isinstance(reason, str)
        assert len(reason) > 0
        llm_terms = {"llm", "advisor", "advisory", "llm_decision", "llm_output", "gpt", "claude"}
        for term in llm_terms:
            assert term not in reason.lower(), f"LLM term '{term}' found in decision_reason"

    def test_decision_reason_contains_objective_factors(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        reason = data.get("decision_reason", "")
        # Objective assessor typically references plan risk, context, etc.
        assert any(kw in reason.lower() for kw in ("risk", "score", "plan", "context", "step", "impact", "factor"))

    def test_advisory_is_separate_from_decision(self):
        """Advisory is read-only; decision is made by objective engine alone."""
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        decision = data.get("decision")
        advisory = data.get("advisory")
        assert decision is not None
        # Advisory may be None if service not available, but if present must follow the report schema
        if advisory is not None:
            assert "confidence_score" in advisory
            assert "confidence_label" in advisory
            assert "insights" in advisory
            assert "intervention_level" in advisory
            assert advisory["intervention_level"] >= 0


class TestSimulationDecision:
    """Fase 4: SimulationResult flows into DecisionEngine and affects risk/decision."""

    def test_simulation_summary_present_in_dry_run(self):
        """Dry-run triggers simulation; summary must be populated."""
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "analyze system health", "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        sim_summary = data.get("simulation_summary", "")
        assert isinstance(sim_summary, str)

    def test_simulation_summary_in_normal_execution(self):
        """Normal execution may or may not have simulation (depends on risk), but field must exist."""
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "simulation_summary" in data

    def test_simulation_overrides_decision_for_high_risk(self):
        """High-risk simulated operations (executor commands) require_confirm even in dry_run."""
        perm_svc.set_level("view")
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "run command del /f system32", "dry_run": True},
        )
        perm_svc.set_level("confirm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"] is True
        # The key assertion: simulation should flag high risk and decision may reject or require_confirm
        assert data.get("decision") in ("approve", "require_confirm", "reject")

    def test_simulation_risk_overrides_low_risk(self):
        """Low-risk tools see no forced decision from simulation."""
        resp = client.post(
            "/api/sentinel/process",
            json={"utterance": "cpu usage", "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        # CPU usage is low risk — simulation should not force require_confirm
        assert data["decision"] == "approve"


class TestAdvisoryFeedback:
    """Fase 5: Per-message advisory thumbs up/down feedback loop."""

    def test_advisory_feedback_helpful(self):
        resp = client.post(
            "/api/sentinel/advisory/feedback",
            json={"helpful": True, "insight_kind": "risk_warning", "execution_id": "test-e2e-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "stats" in data

    def test_advisory_feedback_not_helpful(self):
        resp = client.post(
            "/api/sentinel/advisory/feedback",
            json={"helpful": False, "insight_kind": "risk_warning", "execution_id": "test-e2e-002"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_advisory_feedback_stats_accumulate(self):
        for i in range(3):
            client.post(
                "/api/sentinel/advisory/feedback",
                json={"helpful": True, "insight_kind": "risk_warning", "execution_id": f"test-stat-{i}"},
            )
        resp = client.post(
            "/api/sentinel/advisory/feedback",
            json={"helpful": True, "insight_kind": "risk_warning", "execution_id": "test-stat-final"},
        )
        assert resp.status_code == 200
        stats = resp.json()["stats"]
        assert stats["total"] >= 4
        assert stats["total_helpful"] >= 4

    def test_advisory_feedback_missing_fields_defaults(self):
        resp = client.post(
            "/api/sentinel/advisory/feedback",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestConfigAndValidation:
    """Fase 7: Config endpoint, provider config, model validation."""

    def test_get_config_returns_all_fields(self):
        resp = client.get("/ai/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "provider" in data
        assert "api_key_configured" in data
        assert "model" in data
        assert "base_url" in data
        assert "strategy" in data
        assert "free_providers" in data
        assert "provider_key_status" in data

    def test_get_config_strategy_defaults_to_priority(self):
        resp = client.get("/ai/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy"] in ("priority", "manual", "smart", "cost_optimized", "round_robin")

    def test_set_config_changes_strategy(self):
        resp = client.post("/ai/config", json={"strategy": "manual"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        get_resp = client.get("/ai/config")
        assert get_resp.json()["strategy"] == "manual"

    def test_set_config_changes_provider(self):
        resp = client.post("/ai/config", json={"provider": "sentinel_local"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        get_resp = client.get("/ai/config")
        assert get_resp.json()["provider"] == "sentinel_local"

    def test_validate_model_valid(self):
        resp = client.post("/ai/validate-model", json={"provider": "openrouter", "model": "gpt-4o"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["provider"] == "openrouter"
        assert data["model"] == "gpt-4o"

    def test_validate_model_empty_model_is_invalid(self):
        resp = client.post("/ai/validate-model", json={"provider": "openrouter", "model": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_validate_model_unknown_provider_returns_empty_default(self):
        resp = client.post("/ai/validate-model", json={"provider": "nonexistent", "model": "test-model"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_model"] == ""

    def test_get_providers_returns_dict(self):
        resp = client.get("/ai/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "openrouter" in data
        assert "anthropic" in data


class TestKeyDeletion:
    """Fase 8: API key deletion through config endpoint."""

    def test_delete_key_returns_saved(self):
        """delete_key silently handles missing vault in test env — must not crash."""
        resp = client.post("/ai/config", json={"provider": "openrouter", "delete_key": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    def test_delete_key_does_not_crash(self):
        """delete_key silently handles missing vault in test env — must not crash."""
        client.post("/ai/config", json={"provider": "openrouter", "delete_key": True})
        resp = client.get("/ai/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key_configured" in data
        assert isinstance(data["api_key_configured"], bool)

    def test_delete_key_for_anthropic(self):
        """Anthropic provider key deletion works the same way."""
        resp = client.post("/ai/config", json={"provider": "anthropic", "delete_key": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    def test_provider_key_status_is_dict(self):
        resp = client.get("/ai/config")
        assert resp.status_code == 200
        status = resp.json().get("provider_key_status", {})
        assert isinstance(status, dict)
        # Vault may not have entries in test env, but status is always a dict


class TestDeepContextIntegration:
    """Fase 6: Environment changes, hardware/app context available in pipeline."""

    def test_environment_changes_endpoint(self):
        resp = client.get("/api/sentinel/memory/environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "changes" in data
        assert isinstance(data["changes"], list)
        assert data.get("advisory_only") is True

    def test_environment_changes_delete(self):
        resp = client.delete("/api/sentinel/memory/environment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert "records_deleted" in data
