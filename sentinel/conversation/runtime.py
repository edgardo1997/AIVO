import logging
from typing import Any, Callable, Dict, Optional

from .contracts import ConversationMode, ConversationRequest, ConversationResponse, CoreConversation

log = logging.getLogger("sentinel.conversation")


class ConversationAvailabilityLayer:
    """Maintains a stable conversation contract across provider availability states."""

    def __init__(self, core: CoreConversation, capability_source: Optional[Any] = None):
        self._core = core
        self._capability_source = capability_source

    def capabilities(self) -> Dict[str, Any]:
        baseline = {
            "conversation": {"available": True, "mode": "core"},
            "models": {"available": False, "available_count": 0},
            "system": {"registered_count": 0, "categories": []},
            "future": {"voice": False, "multimodal": False},
        }
        if self._capability_source is None:
            return baseline
        try:
            current = self._capability_source.snapshot()
            for key, value in current.items():
                if isinstance(value, dict) and isinstance(baseline.get(key), dict):
                    baseline[key].update(value)
                else:
                    baseline[key] = value
        except Exception:
            log.exception("Capability snapshot failed")
        return baseline

    def respond(
        self,
        request: ConversationRequest,
        advanced: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> ConversationResponse:
        capabilities = self.capabilities()
        if advanced is not None:
            try:
                result = advanced()
                text = str(result.get("response") or "").strip()
                if text:
                    capabilities["conversation"]["mode"] = "advanced"
                    return ConversationResponse(
                        text=text,
                        mode=ConversationMode.ADVANCED,
                        provider=result.get("provider"),
                        model=result.get("model"),
                        capabilities=capabilities,
                    )
            except Exception:
                log.exception("Advanced conversation unavailable; continuing in core mode")

        capabilities["conversation"]["mode"] = "core"
        try:
            text = self._core.respond(request, capabilities)
        except Exception:
            log.exception("Core conversation handler failed")
            text = _COPY_SAFE["es" if any(ch in request.message.lower() for ch in "áéíóúñ¿¡") else "en"]
        return ConversationResponse(text=text, mode=ConversationMode.CORE, capabilities=capabilities)


_COPY_SAFE = {
    "en": "Sentinel conversation remains available. I can help with the capabilities active on this device.",
    "es": "La conversación de Sentinel sigue disponible. Puedo ayudarte con las capacidades activas en este dispositivo.",
}
