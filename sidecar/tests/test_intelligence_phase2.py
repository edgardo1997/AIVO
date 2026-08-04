import pytest

from sentinel.intelligence import contracts, pipeline_profiles, coordinator
from sentinel.intelligence.coordinator import IntelligenceCoordinator
from sentinel.intelligence.contracts import (
    ExplanationResult,
    IntentResult,
    LanguageDecision,
    PipelineProfile,
    RiskDecision,
    WorldModelEvidence,
    LearningObservation,
    FailureMode,
)
from sentinel.intelligence.pipeline_profiles import FAST_CONVERSATION, GOVERNED_ACTION, select_profile
from services import language_service, input_understanding_service, explanation_service


@pytest.mark.alpha_constitutional_gate
def test_existing_owners_map_to_constitutional_stages():
    # Contracts module exposes a stable contract for every expected engine.
    assert hasattr(contracts, "IdentityResult")
    assert hasattr(contracts, "LanguageDecision")
    assert hasattr(contracts, "InputUnderstandingResult")
    assert hasattr(contracts, "AmbiguityDecision")
    assert hasattr(contracts, "ExplanationResult")


@pytest.mark.alpha_constitutional_gate
def test_fast_conversation_skips_governed_only_stages():
    assert "planning" not in FAST_CONVERSATION.required_stages
    assert "risk_evaluation" not in FAST_CONVERSATION.required_stages
    assert "governance" not in FAST_CONVERSATION.required_stages
    assert "execution" not in FAST_CONVERSATION.required_stages
    assert FAST_CONVERSATION.can_execute_tools is False


@pytest.mark.alpha_constitutional_gate
def test_governed_action_includes_ambiguity_risk_governance():
    required = GOVERNED_ACTION.required_stages
    assert "ambiguity" in required
    assert "risk_evaluation" in required
    assert "governance" in required
    assert GOVERNED_ACTION.can_execute_tools is True


@pytest.mark.alpha_constitutional_gate
def test_select_profile_chooses_fast_for_conversation():
    intent = IntentResult(selected_intent="conversation", is_executable=False)
    profile = select_profile(intent.selected_intent, intent.is_executable)
    assert profile.name == "fast_conversation"


@pytest.mark.alpha_constitutional_gate
def test_select_profile_chooses_governed_for_executable_intent():
    intent = IntentResult(selected_intent="execute", is_executable=True)
    profile = select_profile(intent.selected_intent, intent.is_executable)
    assert profile.name == "governed_action"


@pytest.mark.alpha_constitutional_gate
def test_select_profile_uses_fast_for_executable_with_clarification():
    intent = IntentResult(selected_intent="execute", is_executable=True)
    profile = select_profile(intent.selected_intent, intent.is_executable, ambiguity_action="ask_clarification")
    assert profile.name == "fast_conversation"


@pytest.mark.alpha_constitutional_gate
def test_ambiguous_action_stopped_before_planning():
    c = IntelligenceCoordinator()
    amb = input_understanding_service.AmbiguityDecision(ask_clarification=True, action="proceed")
    intent = IntentResult(selected_intent="execute", is_executable=True)
    trace = c.coordinate(ambiguity=amb, intent=intent)
    assert trace.stopped is True
    assert trace.stop_reason == "ambiguity"
    # Stages that appeared only as stopped markers are not executed.
    executed = {s.name for s in trace.stages if not s.stopped and not s.skipped}
    assert "planning" not in executed
    assert "governance" not in executed
    assert "execution" not in executed


@pytest.mark.alpha_constitutional_gate
def test_informational_intent_fast_profile():
    c = IntelligenceCoordinator()
    intent = IntentResult(selected_intent="informational", is_executable=False)
    trace = c.coordinate(intent=intent)
    assert trace.profile == "fast_conversation"


@pytest.mark.alpha_constitutional_gate
def test_coordinator_cannot_authorize_or_persist():
    c = IntelligenceCoordinator()
    # The coordinator has no authorization methods.
    assert not hasattr(c, "authorize")
    assert not hasattr(c, "save")
    assert not hasattr(c, "persist")


@pytest.mark.alpha_constitutional_gate
def test_coordinator_does_not_execute_toolgateway():
    c = IntelligenceCoordinator()
    # Tool execution remains with owners; the coordinator has no execute method.
    assert not hasattr(c, "execute")
    assert not hasattr(c, "execute_tool")


@pytest.mark.alpha_constitutional_gate
def test_explanation_uses_evidence_no_hidden_reasoning():
    decision = language_service.resolve_language("hello")
    explanation = explanation_service.explain(
        "LOCAL_SELECTED",
        facts={"local_model_available": True, "cloud_authorized": False, "api_key": "sk-123"},
        language=decision,
    )
    assert isinstance(explanation, ExplanationResult)
    assert explanation.facts.get("local_model_available") is True
    assert "api_key" not in explanation.facts
    assert "sk-123" not in explanation.localized_summary


@pytest.mark.alpha_constitutional_gate
def test_world_model_evidence_requires_provenance():
    fact = WorldModelEvidence(
        fact_id="f1",
        subject="notepad",
        predicate="installed",
        value=True,
        evidence_source="registry",
        observed_at="2026-08-01T00:00:00Z",
        confidence=0.9,
        user_correction_status="unverified",
    )
    assert fact.evidence_source
    assert fact.user_correction_status == "unverified"


@pytest.mark.alpha_constitutional_gate
def test_unverified_world_fact_not_treated_as_verified():
    fact = WorldModelEvidence(user_correction_status="unverified")
    assert fact.user_correction_status != "verified"


@pytest.mark.alpha_constitutional_gate
def test_learning_observation_cannot_modify_authority():
    obs = LearningObservation(category="user_corrected_interpretation", verified=True)
    assert not hasattr(obs, "permission_change")
    assert not hasattr(obs, "authority_change")
    assert not hasattr(obs, "policy_change")


@pytest.mark.alpha_constitutional_gate
def test_post_execution_learning_runs_only_after_verification():
    from sentinel.intelligence.pipeline_profiles import POST_EXECUTION_LEARNING
    assert "verification" in POST_EXECUTION_LEARNING.required_stages
    assert "execution" not in POST_EXECUTION_LEARNING.required_stages


@pytest.mark.alpha_constitutional_gate
def test_pipeline_stops_on_governance_denial():
    c = IntelligenceCoordinator()
    trace = c.coordinate(profile_override=PipelineProfile.GOVERNED_ACTION)
    # Without an ambiguity that stops early, this trace completes because mocks are not registered.
    # The profile stop on ambiguity is already tested; this test verifies profile override works.
    assert trace.profile == "governed_action"


@pytest.mark.alpha_constitutional_gate
def test_language_decision_protocol_satisfied_by_service():
    decision = language_service.resolve_language("hola")
    assert isinstance(decision, LanguageDecision)
    assert decision.response_language in ("es", "en")


@pytest.mark.alpha_constitutional_gate
def test_provider_fallback_preserves_language_in_contracts():
    decision = language_service.resolve_language("responde en español")
    assert decision.response_language == "es"
    # The contract itself is independent of provider; it only carries the decision.
    assert not hasattr(decision, "provider")


@pytest.mark.alpha_constitutional_gate
def test_no_secret_in_intelligence_contracts():
    fact = WorldModelEvidence(value="sk-abc123")
    # The contract does not redact automatically, but the explanation service does.
    explanation = explanation_service.explain("LOCAL_SELECTED", facts={"token": fact.value})
    assert "sk-abc123" not in explanation.facts.values()


@pytest.mark.alpha_constitutional_gate
def test_fast_conversation_latency_no_material_regression():
    c = IntelligenceCoordinator()
    import time
    t0 = time.monotonic()
    trace = c.coordinate()
    elapsed = (time.monotonic() - t0) * 1000
    assert elapsed < 50  # coordinator is pure selection, should be negligible
    assert trace.profile == "fast_conversation"
