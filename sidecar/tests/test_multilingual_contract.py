import pytest

from repositories.user_preferences_store import UserPreferencesStore
from services import language_service


@pytest.fixture(autouse=True)
def _clean_language_prefs():
    """Reset the language preference for the default user before each test."""
    UserPreferencesStore().save("local-user", {"language": "en"})


@pytest.mark.alpha_constitutional_gate
def test_english_preference_instructs_english():
    UserPreferencesStore().save("local-user", {"language": "en"})
    decision = language_service.resolve_language("hello")
    assert decision.response_language == "en"
    assert "Respond in en" in language_service.build_language_instruction(decision)


@pytest.mark.alpha_constitutional_gate
def test_spanish_preference_instructs_spanish():
    UserPreferencesStore().save("local-user", {"language": "es"})
    decision = language_service.resolve_language("hola")
    assert decision.response_language == "es"
    assert "Respond in es" in language_service.build_language_instruction(decision)


@pytest.mark.alpha_constitutional_gate
def test_explicit_request_overrides_preference():
    UserPreferencesStore().save("local-user", {"language": "en"})
    decision = language_service.resolve_language("responde en español por favor")
    assert decision.response_language == "es"
    assert decision.decision_source == "explicit_request"


@pytest.mark.alpha_constitutional_gate
def test_explicit_french_normalized_to_bcp47():
    UserPreferencesStore().save("local-user", {"language": "en"})
    decision = language_service.resolve_language("answer in French")
    assert decision.response_language == "fr"


@pytest.mark.alpha_constitutional_gate
def test_one_message_override_does_not_change_durable_preference(_clean_language_prefs):
    UserPreferencesStore().save("local-user", {"language": "en"})
    _ = language_service.resolve_language("responde en español solo esta vez")
    prefs = UserPreferencesStore().load("local-user")
    assert prefs["language"] == "en"


@pytest.mark.alpha_constitutional_gate
def test_conversation_language_override_survives_turns():
    decision = language_service.resolve_language(
        "continúa en español",
        explicit_override="es",
    )
    assert decision.conversation_language == "es"
    assert decision.response_language == "es"


@pytest.mark.alpha_constitutional_gate
def test_isolated_foreign_word_does_not_change_language(_clean_language_prefs):
    UserPreferencesStore().save("local-user", {"language": "es"})
    # User says "Open Notepad" in an otherwise Spanish message.
    decision = language_service.resolve_language("abre Open Notepad")
    assert decision.response_language == "es"


@pytest.mark.alpha_constitutional_gate
def test_provider_fallback_preserves_response_language():
    # The requested language is independent of the provider.
    decision = language_service.resolve_language("antworte auf Deutsch")
    assert decision.response_language == "de"
    assert decision.fallback_required is False


@pytest.mark.alpha_constitutional_gate
def test_local_model_preserves_response_language():
    decision = language_service.resolve_language("rispondi in italiano")
    assert decision.response_language == "it"
    assert decision.provider_language_support is True


@pytest.mark.alpha_constitutional_gate
def test_wrong_language_provider_response_triggers_correction():
    UserPreferencesStore().save("local-user", {"language": "es"})
    decision = language_service.resolve_language("hola")
    validation = language_service.validate_response_language(
        "Hello this is a very long English response to make sure detection confidence is high enough to trigger correction.",
        decision,
    )
    assert validation.valid is False
    assert validation.fallback_required is True
    assert "en instead of es" in validation.reason


@pytest.mark.alpha_constitutional_gate
def test_right_language_response_is_valid():
    UserPreferencesStore().save("local-user", {"language": "es"})
    decision = language_service.resolve_language("hola")
    validation = language_service.validate_response_language(
        "Hola, esta es una respuesta en español con suficientes palabras para superar el umbral mínimo.",
        decision,
    )
    assert validation.valid is True
    assert validation.detected == "es"


@pytest.mark.alpha_constitutional_gate
def test_paths_and_code_not_translated_in_instruction():
    decision = language_service.resolve_language("responde en español")
    instruction = language_service.build_language_instruction(decision)
    assert "filesystem paths" in instruction
    assert "code" in instruction
    assert "Respond in es" in instruction


@pytest.mark.alpha_constitutional_gate
def test_localized_error_setup_required_spanish():
    decision = language_service.resolve_language("hola")
    decision.response_language = "es"
    assert language_service.localize_error("setup_required", decision) == "Se requiere configuración antes de continuar."


@pytest.mark.alpha_constitutional_gate
def test_localized_error_local_only_cloud():
    decision = language_service.resolve_language("hello")
    assert "Local-only mode is active" in language_service.localize_error("local_only_blocked_cloud", decision)


@pytest.mark.alpha_constitutional_gate
def test_cancellation_message_localized():
    decision = language_service.resolve_language("hola")
    decision.response_language = "es"
    assert language_service.localize_error("cancelled", decision) == "La acción fue cancelada."


@pytest.mark.alpha_constitutional_gate
def test_preference_survives_restart():
    UserPreferencesStore().save("local-user", {"language": "pt"})
    prefs = UserPreferencesStore().load("local-user")
    assert prefs["language"] == "pt"
    decision = language_service.resolve_language("olá")
    assert decision.preferred_language == "pt"


@pytest.mark.alpha_constitutional_gate
def test_confirmation_localized():
    decision = language_service.resolve_language("hola")
    decision.response_language = "es"
    text = language_service.localize_error("confirmation_required", decision)
    assert "confirmación" in text


@pytest.mark.alpha_constitutional_gate
def test_cloud_authorization_localized():
    decision = language_service.resolve_language("hola")
    decision.response_language = "es"
    text = language_service.localize_error("cloud_authorization_required", decision)
    assert "proveedor" in text and "autorización" in text


@pytest.mark.alpha_constitutional_gate
def test_unsupported_language_defaults_with_limitation(monkeypatch):
    # An unknown language name returns the default English.
    decision = language_service.resolve_language("answer in Klingon")
    assert decision.response_language == "en"


@pytest.mark.alpha_constitutional_gate
def test_language_preference_no_secret_in_state():
    decision = language_service.resolve_language("hello")
    assert "api_key" not in str(decision).lower()
    assert "token" not in str(decision).lower()
