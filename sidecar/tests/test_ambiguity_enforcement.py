import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sentinel.security.models import ExecutionGrantContext, SecurityDecision, ToolRequest
from sentinel.security.tool_guard import ToolExecutionGuard
from services import input_understanding_service as iu


def _run(coro):
    return asyncio.run(coro)


def _fresh_guard(gateway=None):
    audit = MagicMock()
    audit.log_action = AsyncMock(return_value=None)
    return ToolExecutionGuard(tool_gateway=gateway, audit_service=audit)


def _req(tool="app.open", arguments=None, *, ambiguity=None, understanding=None, session="s1", user="u1", grant=None):
    return ToolRequest(
        tool_name=tool,
        arguments=arguments or {},
        source="orchestrator",
        user_id=user,
        session_id=session,
        user_context={
            "ambiguity_decision": ambiguity,
            "input_understanding": understanding,
            "execution_grant": grant,
        },
    )


@pytest.mark.alpha_constitutional_gate
def test_material_ambiguity_rejected_by_guard():
    understanding = iu.resolve_input("borra todos los archivos")
    decision = iu.make_decision(understanding)
    req = _req(ambiguity=decision, understanding=understanding)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error
    assert result.decision == SecurityDecision.DENIED


@pytest.mark.alpha_constitutional_gate
def test_requires_clarification_cannot_reach_gateway():
    understanding = iu.resolve_input("borra ese")
    decision = iu.make_decision(understanding)
    gateway = AsyncMock()
    guard = _fresh_guard(gateway=gateway)
    req = _req(ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error
    gateway.execute.assert_not_awaited()


@pytest.mark.alpha_constitutional_gate
def test_missing_target_rejected_for_target_dependent_action():
    understanding = iu.resolve_input("abre la aplicación")
    understanding.selected_target = ""
    decision = iu.make_decision(understanding)
    decision.ask_clarification = False
    decision.action = "proceed"
    req = _req(tool="app.open", arguments={"app": ""}, ambiguity=decision, understanding=understanding)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "exact target missing" in result.error


@pytest.mark.alpha_constitutional_gate
def test_informational_intent_cannot_execute():
    understanding = iu.resolve_input("cómo borro un archivo")
    decision = iu.make_decision(understanding)
    req = _req(ambiguity=decision, understanding=understanding)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "informational" in result.error


@pytest.mark.alpha_constitutional_gate
def test_contradictory_request_cannot_execute():
    understanding = iu.resolve_input("elimínalo, pero no borres nada")
    decision = iu.make_decision(understanding)
    req = _req(ambiguity=decision, understanding=understanding)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error


@pytest.mark.alpha_constitutional_gate
def test_forged_resolved_flag_without_matching_evidence_rejected():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z",
        ambiguity_decision_id="different-id",
    )
    req = _req(ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "mismatch" in result.error


@pytest.mark.alpha_constitutional_gate
def test_ambiguity_evidence_from_another_request_rejected():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z",
        input_understanding_id="different-id",
    )
    req = _req(ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False
    assert "mismatch" in result.error


@pytest.mark.alpha_constitutional_gate
def test_ambiguity_evidence_from_another_session_user_rejected():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    req = _req(ambiguity=decision, understanding=understanding, user="u2", session="s2")
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_changed_target_invalidates_grant():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z",
    )
    req = _req(tool="app.open", arguments={"app": "calculator"}, ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_changed_action_invalidates_grant():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z",
    )
    req = _req(tool="app.close", arguments={"app": "notepad"}, ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_changed_scope_invalidates_grant():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z",
    )
    req = _req(tool="app.open", arguments={"app": "notepad", "scope": "all"}, ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_clarification_denial_creates_no_side_effect():
    understanding = iu.resolve_input("borra ese")
    decision = iu.make_decision(understanding)
    gateway = AsyncMock()
    guard = _fresh_guard(gateway=gateway)
    req = _req(ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.success is False
    assert result.error.startswith("AMBIGUITY_UNRESOLVED")
    gateway.execute.assert_not_awaited()


@pytest.mark.alpha_constitutional_gate
def test_clarification_denial_does_not_trigger_provider_fallback():
    understanding = iu.resolve_input("borra ese")
    decision = iu.make_decision(understanding)
    guard = _fresh_guard()
    req = _req(ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error
    assert "provider" not in result.error.lower()
    assert "unavailable" not in result.error.lower()


@pytest.mark.alpha_constitutional_gate
def test_valid_low_risk_request_can_execute():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    gateway = AsyncMock()
    gateway.execute = AsyncMock(return_value={"success": True, "data": "ok"})
    guard = _fresh_guard(gateway=gateway)
    req = _req(tool="app.open", arguments={"app": "notepad"}, ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.decision in (SecurityDecision.APPROVED, SecurityDecision.REQUIRE_CONFIRMATION) or result.success is True
    assert "AMBIGUITY_UNRESOLVED" not in (result.error or "")


@pytest.mark.alpha_constitutional_gate
def test_typo_auto_correction_still_proceeds_for_clear_low_risk_intent():
    understanding = iu.resolve_input("habre calculadora")
    decision = iu.make_decision(understanding)
    assert decision.action == "auto_correct"
    guard = _fresh_guard()
    req = _req(tool="app.open", arguments={"app": "calculadora"}, ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert "AMBIGUITY_UNRESOLVED" not in (result.error or "")


@pytest.mark.alpha_constitutional_gate
def test_clarification_question_uses_selected_language():
    understanding = iu.resolve_input("borra ese")
    decision = iu.make_decision(understanding)
    prompt = iu.clarification_prompt(understanding, decision, "es")
    assert "Necesito aclaración" in prompt
    prompt = iu.clarification_prompt(understanding, decision, "en")
    assert "I need clarification" in prompt


@pytest.mark.alpha_constitutional_gate
def test_candidate_options_contain_stable_ids():
    understanding = iu.resolve_input("borra ese")
    assert understanding.decision_id
    decision = iu.make_decision(understanding)
    assert decision.id
    assert decision.id != understanding.decision_id


@pytest.mark.alpha_constitutional_gate
def test_stale_execution_grant_rejected():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2026-01-01T00:00:00Z", expires_at="2020-01-01T00:00:00Z",
    )
    req = _req(tool="app.open", arguments={"app": "notepad"}, ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_expired_grant_cannot_be_replayed():
    understanding = iu.resolve_input("abre notepad")
    decision = iu.make_decision(understanding)
    grant = ExecutionGrantContext(
        grant_id="g1", plan_grant_id="pg1", step_grant_id="sg1",
        user_id="u1", session_id="s1", identity_hash="h1", plan_id="p1",
        plan_hash="h2", step_id="st1", step_index=0, tool_id="app.open",
        params_hash="h3", approved_at="2020-01-01T00:00:00Z", expires_at="2020-01-02T00:00:00Z",
    )
    req = _req(tool="app.open", arguments={"app": "notepad"}, ambiguity=decision, understanding=understanding, grant=grant)
    guard = _fresh_guard()
    result = _run(guard.execute(req))
    assert result.success is False


@pytest.mark.alpha_constitutional_gate
def test_user_cancellation_leaves_action_unexecuted():
    understanding = iu.resolve_input("borra ese")
    decision = iu.make_decision(understanding)
    decision.action = "reject"
    gateway = AsyncMock()
    guard = _fresh_guard(gateway=gateway)
    req = _req(ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error
    gateway.execute.assert_not_awaited()


@pytest.mark.alpha_constitutional_gate
def test_no_secret_appears_in_clarification_context():
    understanding = iu.resolve_input("mi api key es sk-12345 y el archivo es C:\\secret.txt")
    assert "sk-12345" in understanding.original_text
    assert "sk-12345" in understanding.normalized_text  # preserved because it is technical
    decision = iu.make_decision(understanding)
    prompt = iu.clarification_prompt(understanding, decision, "en")
    assert "sk-12345" not in prompt


@pytest.mark.alpha_constitutional_gate
def test_code_and_paths_unchanged_after_normalization():
    text = "pip install numpy desde C:\\Users\\edgar\\venv"
    understanding = iu.resolve_input(text)
    assert "pip install numpy" in understanding.normalized_text
    assert "C:\\Users\\edgar\\venv" in understanding.normalized_text
    assert not understanding.corrected_tokens


@pytest.mark.alpha_constitutional_gate
def test_guard_rejects_when_ambiguity_level_is_high():
    understanding = iu.resolve_input("abre")
    understanding.ambiguity_level = "high"
    understanding.requires_clarification = True
    decision = iu.make_decision(understanding)
    guard = _fresh_guard()
    req = _req(ambiguity=decision, understanding=understanding)
    result = _run(guard.execute(req))
    assert result.success is False
    assert "AMBIGUITY_UNRESOLVED" in result.error
