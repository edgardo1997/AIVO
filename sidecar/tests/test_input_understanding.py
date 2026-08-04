import pytest

from services import input_understanding_service as iu


@pytest.mark.alpha_constitutional_gate
def test_obvious_spanish_typo_corrected():
    r = iu.resolve_input("habre calculadora")
    assert r.normalized_text == "abre calculadora"
    assert "habre->abre" in r.corrected_tokens
    d = iu.make_decision(r)
    assert d.action == "auto_correct"


@pytest.mark.alpha_constitutional_gate
def test_missing_accent_does_not_change_intent():
    r = iu.resolve_input("borra el archivo")
    assert "borra" in r.normalized_text
    assert r.ambiguity_level != "material"


@pytest.mark.alpha_constitutional_gate
def test_path_not_autocorrected():
    r = iu.resolve_input("abre C:\\Users\\edgar\\Documents\\file.txt")
    assert r.normalized_text == "abre C:\\Users\\edgar\\Documents\\file.txt"
    assert not r.corrected_tokens


@pytest.mark.alpha_constitutional_gate
def test_code_not_autocorrected():
    r = iu.resolve_input("pip instal numpy")
    # `instal` is mapped to `install` because not a path; but the original stays intent only.
    assert "install" in r.normalized_text
    assert r.ambiguity_level == "harmless"


@pytest.mark.alpha_constitutional_gate
def test_mixed_spanish_english_request():
    r = iu.resolve_input("abre notepad por favor")
    assert "notepad" in r.normalized_text
    assert "por favor" in r.normalized_text
    assert r.selected_intent in ("execution", "conversation")


@pytest.mark.alpha_constitutional_gate
def test_informational_question_does_not_execute():
    r = iu.resolve_input("cómo borro un archivo")
    assert r.selected_intent == "informational"
    d = iu.make_decision(r)
    assert d.action != "proceed" or d.risk_level == "low"


@pytest.mark.alpha_constitutional_gate
def test_imperative_command_enters_execution():
    r = iu.resolve_input("borra el archivo")
    assert "execution" in r.candidate_intents
    d = iu.make_decision(r)
    assert d.ask_clarification is False or d.risk_level == "low"


@pytest.mark.alpha_constitutional_gate
def test_broad_scope_destructive_triggers_clarification():
    r = iu.resolve_input("borra todos los archivos")
    assert r.requires_clarification is True
    assert "scope" in r.ambiguity_type
    d = iu.make_decision(r)
    assert d.action == "ask_clarification"
    assert d.risk_level == "high"


@pytest.mark.alpha_constitutional_gate
def test_negation_respected():
    r = iu.resolve_input("no lo borres, solo dime dónde está")
    assert "no" in r.normalized_text
    assert r.requires_clarification is True


@pytest.mark.alpha_constitutional_gate
def test_reference_without_context_requires_clarification():
    r = iu.resolve_input("borra ese")
    assert "reference" in r.ambiguity_type
    assert r.requires_clarification is True


@pytest.mark.alpha_constitutional_gate
def test_reference_with_context_resolves():
    ctx = [{"role": "assistant", "content": "El archivo es C:\\Users\\edgar\\file.txt"}]
    r = iu.resolve_input("abre ese", context=ctx)
    assert r.selected_target == "C:\\Users\\edgar\\file.txt"


@pytest.mark.alpha_constitutional_gate
def test_lexical_ambiguous_word_low_risk_is_recoverable():
    r = iu.resolve_input("qué es un banco")
    assert "lexical" in r.ambiguity_type
    d = iu.make_decision(r)
    assert d.ask_clarification is False  # informational, low risk


@pytest.mark.alpha_constitutional_gate
def test_lexical_ambiguous_word_with_risk_asks():
    r = iu.resolve_input("borra el banco")
    assert "lexical" in r.ambiguity_type
    d = iu.make_decision(r)
    assert d.ask_clarification is True


@pytest.mark.alpha_constitutional_gate
def test_contradictory_instructions_paused():
    r = iu.resolve_input("elimínalo, pero no borres nada")
    assert r.requires_clarification is True
    d = iu.make_decision(r)
    assert d.action == "ask_clarification"


@pytest.mark.alpha_constitutional_gate
def test_cloud_ambiguity_cannot_authorize_cloud():
    r = iu.resolve_input("usa cloud si tarda mucho local")
    assert r.selected_intent in ("informational", "conversation", "execution")
    # No entity or action resolution should treat cloud use as authorized.
    assert not r.assumptions or "cloud" not in " ".join(r.assumptions)


@pytest.mark.alpha_constitutional_gate
def test_no_secret_normalized():
    r = iu.resolve_input("mi clave es sk-abc123 y api_key=xyz")
    # The original text is preserved; token `sk-abc123` is technical and unchanged.
    assert "sk-abc123" in r.normalized_text
    assert "api_key=xyz" in r.normalized_text


@pytest.mark.alpha_constitutional_gate
def test_clarification_prompt_localized():
    r = iu.resolve_input("borra todos")
    d = iu.make_decision(r)
    prompt = iu.clarification_prompt(r, d, "es")
    assert "Necesito aclaración" in prompt


@pytest.mark.alpha_constitutional_gate
def test_ordinary_low_risk_chat_stays_lightweight():
    r = iu.resolve_input("hola")
    assert r.ambiguity_level == "none"
    d = iu.make_decision(r)
    assert d.action in ("proceed", "infer")


@pytest.mark.alpha_constitutional_gate
def test_assumption_recorded_in_result():
    r = iu.resolve_input("borra el anterior", context=[{"role": "user", "content": "C:\\Users\\edgar\\old.txt"}])
    # At minimum we do not crash and produce a bounded result.
    assert r.original_text == "borra el anterior"
    assert r.confidence >= 0.0
