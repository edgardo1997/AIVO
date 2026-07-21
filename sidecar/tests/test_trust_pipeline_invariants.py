import asyncio

from fastapi.testclient import TestClient

from conftest import TEST_IDENTITY
from main import app
from modules import get_gateway, init_sentinel_orchestrator
from modules.permissions import _svc as permissions_service
from modules.auth import IdentityContext
from sentinel.core.decision_engine import Decision, DecisionResult


client = TestClient(app)


def test_gateway_fails_closed_without_authenticated_identity():
    result = asyncio.run(get_gateway().execute("system.info", {}, {}))
    assert result.success is False
    assert "identity required" in result.error.lower()
    assert result.policy_result["policy_id"] == "identity"


def test_orchestrator_process_does_not_invent_anonymous_identity():
    orchestrator = init_sentinel_orchestrator(get_gateway())
    result = asyncio.run(orchestrator.process("cpu usage"))
    assert result.tool_result is not None
    assert result.tool_result.success is False
    assert "identity required" in result.tool_result.error.lower()


def test_v1_rejects_client_supplied_identity():
    response = client.post(
        "/v1/execute",
        json={
            "tool_id": "system.info",
            "params": {},
            "identity": {"user_id": "spoofed-admin", "is_authenticated": True},
        },
    )
    assert response.status_code == 422


def test_identity_permissions_restrict_remote_capabilities():
    permissions_service.set_level("admin")
    remote = IdentityContext.remote_identity("actor-1", "session-1").to_dict()
    allowed = asyncio.run(
        get_gateway().execute(
            "system.info",
            {},
            {"identity": remote},
        )
    )
    denied = asyncio.run(
        get_gateway().execute(
            "executor.command",
            {"command": "echo forbidden"},
            {"identity": remote},
        )
    )
    assert allowed.success is True
    assert denied.success is False
    assert denied.policy_result["policy_id"] == "identity_permissions"


def test_policy_is_authorization_authority_not_decision_recommendation():
    class AlwaysRejectDecision:
        def should_skip_decision(self, intent):
            return False

        def evaluate(self, plan, context, simulation_result=None):
            return DecisionResult(
                decision=Decision.REJECT,
                plan=plan,
                reason="risk recommendation rejects",
                base_risk_score=1.0,
                final_risk_score=1.0,
            )

    permissions_service.set_level("admin")
    orchestrator = init_sentinel_orchestrator(get_gateway())
    orchestrator._decision_engine = AlwaysRejectDecision()
    result = asyncio.run(
        orchestrator.execute_direct(
            "executor.command",
            {"command": "echo policy-authority", "timeout": 5},
            identity=TEST_IDENTITY,
        )
    )
    assert result.decision.decision == Decision.REJECT
    assert result.error is not None
    assert "rejected" in result.error.lower()
    assert result.tool_result is None or result.tool_result.success is False


def test_pipeline_audit_persists_actual_policy_and_quality_results():
    permissions_service.set_level("confirm")
    response = client.post(
        "/v1/execute",
        json={"tool_id": "system.cpu", "params": {}},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    from modules.audit import _svc as audit_service

    entries = audit_service.get_log(action_filter="pipeline.system.cpu")["entries"]
    assert entries
    pipeline = entries[0]["payload"]["pipeline"]
    assert pipeline["identity"]["is_authenticated"] is True
    assert pipeline["policy"]["effect"] == "allow"
    assert pipeline["quality"]["passed"] is True
    permissions_service.set_level("confirm")
