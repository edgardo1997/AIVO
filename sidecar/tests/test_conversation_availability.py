from sentinel.conversation import (
    ConversationAvailabilityLayer,
    ConversationRequest,
    SentinelCoreConversation,
)


class Capabilities:
    def snapshot(self):
        return {
            "models": {"available": False, "available_count": 0, "providers": []},
            "system": {"registered_count": 3, "categories": ["system", "filesystem"]},
        }


def runtime():
    return ConversationAvailabilityLayer(SentinelCoreConversation(), Capabilities())


def test_uses_real_advanced_response_when_available():
    response = runtime().respond(
        ConversationRequest(message="hello"),
        advanced=lambda: {"response": "model answer", "provider": "local", "model": "test"},
    )

    data = response.to_dict()
    assert data["response"] == "model answer"
    assert data["conversation_mode"] == "advanced"
    assert data["provider"] == "local"


def test_provider_failure_keeps_conversation_available_without_error_leakage():
    def unavailable():
        raise RuntimeError("secret provider diagnostic")

    data = runtime().respond(
        ConversationRequest(message="hola, qué puedes hacer"), advanced=unavailable
    ).to_dict()

    assert data["conversation_mode"] == "core"
    assert data["response"]
    assert "secret provider diagnostic" not in data["response"]
    assert data["capabilities"]["conversation"]["available"] is True


def test_core_reports_runtime_capabilities_truthfully():
    data = runtime().respond(ConversationRequest(message="estado de Sentinel")).to_dict()

    assert data["conversation_mode"] == "core"
    assert "3" in data["response"]
    assert data["capabilities"]["system"]["registered_count"] == 3


def test_core_formats_tool_results_without_impersonating_a_model():
    data = runtime().respond(
        ConversationRequest(
            message="muestra el estado",
            purpose="tool_result",
            tool_result={"cpu": 12},
        )
    ).to_dict()

    assert data["conversation_mode"] == "core"
    assert '"cpu": 12' in data["response"]
