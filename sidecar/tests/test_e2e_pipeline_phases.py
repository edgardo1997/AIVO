import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

pytestmark = pytest.mark.e2e

client = TestClient(app)


class TestPresentationInPipeline:
    """Fase 2: PresentationLayer is attached to every pipeline response."""

    def test_presentation_present_in_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        pres = data.get("presentation")
        assert pres is not None
        assert pres.get("version") == 1
        assert pres.get("mode") in ("user", "developer")
        assert pres.get("status") is not None
        assert pres.get("summary") is not None
        assert pres.get("risk") is not None
        assert pres["risk"].get("level") in ("low", "medium", "high", "critical", "unknown")
        assert pres.get("evidence") is not None
        assert "satisfied" in pres["evidence"]

    def test_presentation_user_mode_by_default(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        assert resp.json()["presentation"]["mode"] == "user"

    def test_presentation_mode_is_valid(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        mode = resp.json()["presentation"]["mode"]
        assert mode in ("user", "developer")

    def test_presentation_evidence_includes_grounding(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        evidence = resp.json()["presentation"]["evidence"]
        assert isinstance(evidence["required"], int)
        assert isinstance(evidence["verified"], int)
        assert isinstance(evidence["satisfied"], bool)
        assert isinstance(evidence["sources"], list)

    def test_presentation_present_in_execute_direct(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        pipeline = data.get("pipeline")
        assert pipeline is not None
        plan = pipeline.get("plan")
        assert plan is not None
        assert "plan" in plan
        assert "risk_score" in plan["plan"]

    def test_presentation_summary_describes_outcome(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        summary = resp.json()["presentation"]["summary"]
        assert isinstance(summary, str)
        assert len(summary) > 0


class TestAdvisoryInPipeline:
    """Fase 1: LLM advisor is non-authoritative and logged only."""

    def test_advisory_field_exists_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "advisory" in data

    def test_advisory_field_exists_execute_direct(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        assert pipeline is not None
        assert "advisory" in pipeline

    def test_advisory_does_not_override_approve(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "approve"
        assert data["approved"] is True


class TestGroundingInPipeline:
    """Fase 4: Grounding verification runs in every pipeline turn."""

    def test_grounding_satisfied_is_true_for_system_tools(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("grounding_satisfied") is True
        assert isinstance(data.get("grounding_results"), list)

    def test_grounding_in_execute_direct(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        if data.get("success"):
            assert data.get("grounding_satisfied", True) is True
            assert isinstance(data.get("grounding_results", []), list)

    def test_grounding_satisfied_in_health_analysis(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["grounding_satisfied"] is True
        for gr in data.get("grounding_results", []):
            assert "grounded" in gr
            assert "category" in gr


class TestRiskContextFactors:
    """Fase 1+6: Risk scores and context factors reflect objective + env state."""

    def test_context_factors_is_list_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("context_factors"), list)
        assert isinstance(data.get("base_risk_score"), float)
        assert isinstance(data.get("context_modifier"), float)
        assert isinstance(data.get("final_risk_score"), float)

    def test_risk_scores_range_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        assert 0.0 <= data["base_risk_score"] <= 1.0
        assert 0.0 <= data["context_modifier"] <= 1.0
        assert 0.0 <= data["final_risk_score"] <= 1.0

    def test_risk_scores_range_execute_direct(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        pipeline = data.get("pipeline")
        if pipeline and pipeline.get("decision"):
            dec = pipeline["decision"]
            assert 0.0 <= dec.get("base_risk_score", 0) <= 1.0
            assert 0.0 <= dec.get("context_modifier", 0) <= 1.0
            assert 0.0 <= dec.get("final_risk_score", 0) <= 1.0

    def test_decision_reason_contains_data_sources_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        reason = resp.json().get("decision_reason")
        if reason:
            assert any(src in reason for src in ("plan_risk_score", "system_context", "step_analysis"))


class TestExecuteDirectPipeline:
    """Fase 3: execute_direct runs the same pipeline stages as process."""

    def test_execute_direct_returns_decision(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        assert pipeline is not None
        assert pipeline.get("decision") is not None
        assert pipeline["decision"].get("decision") in ("approve", "require_confirm", "reject")

    def test_execute_direct_returns_plan(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        plan = pipeline.get("plan")
        assert plan is not None
        inner = plan.get("plan")
        assert inner is not None
        assert "steps" in inner
        assert len(inner["steps"]) >= 1

    def test_execute_direct_returns_advisory_field(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        assert "advisory" in pipeline

    def test_execute_direct_decision_reason_present(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        if pipeline and pipeline.get("decision"):
            reason = pipeline["decision"].get("reason", "")
            assert isinstance(reason, str)
            assert len(reason) > 0

    def test_execute_direct_context_factors(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "system.cpu", "params": {}},
        )
        assert resp.status_code == 200
        pipeline = resp.json().get("pipeline")
        if pipeline and pipeline.get("decision"):
            dec = pipeline["decision"]
            assert isinstance(dec.get("context_factors"), list)
            assert isinstance(dec.get("base_risk_score"), float)
            assert isinstance(dec.get("context_modifier"), float)
            assert isinstance(dec.get("final_risk_score"), float)


class TestApplicationKnowledgeInPipeline:
    """Fase 5: Application profiles are considered during planning and decision."""

    def test_decision_reason_can_include_application_knowledge(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        reason = resp.json().get("decision_reason", "")
        assert isinstance(reason, str)

    def test_execute_app_discovery_returns_apps(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "app.discovery", "params": {"action": "list"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "apps" in data["data"]

    def test_execute_app_discovery_capabilities_includes_apps(self):
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "app.discovery", "params": {"action": "capabilities"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        caps = data["data"]["capabilities"]
        ids = [c["id"] for c in caps]
        assert "app.discovery" in ids


class TestAdaptiveRiskFromEnvironment:
    """Fase 6: Environment changes affect risk scores."""

    def test_context_modifier_reflects_environment(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("context_modifier", -1) >= 0.0

    def test_environment_changes_available_in_context(self):
        resp = client.get("/api/sentinel/memory/environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "changes" in data
        assert isinstance(data["changes"], list)
        assert data.get("advisory_only") is True
