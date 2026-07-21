import json
import re
from typing import Any, Dict

from .contracts import ConversationRequest


_COPY = {
    "en": {
        "empty": "Write a message and I’ll help with the capabilities available on this device.",
        "hello": "Sentinel is ready. I can keep this conversation available and use the capabilities currently active on this device.",
        "status": "Sentinel Core is available. {models} {tools}",
        "models_on": "Advanced reasoning is available through {count} model provider(s).",
        "models_off": "Advanced reasoning is unavailable right now; core conversation remains active.",
        "tools": "{count} system capability(ies) are registered.",
        "help": "I can report availability, explain Sentinel, and route supported system actions. Active categories: {categories}.",
        "limited": "I can keep helping with Sentinel and the active system capabilities, but this request needs advanced reasoning that is not available right now. You can ask for system status, available capabilities, or retry when a model provider becomes available.",
        "done": "The action completed successfully.",
        "result": "The action completed successfully:\n{result}",
    },
    "es": {
        "empty": "Escribe un mensaje y te ayudaré con las capacidades disponibles en este dispositivo.",
        "hello": "Sentinel está listo. Puedo mantener esta conversación disponible y usar las capacidades activas en este dispositivo.",
        "status": "Sentinel Core está disponible. {models} {tools}",
        "models_on": "El razonamiento avanzado está disponible mediante {count} proveedor(es) de modelos.",
        "models_off": "El razonamiento avanzado no está disponible ahora; la conversación esencial sigue activa.",
        "tools": "Hay {count} capacidad(es) del sistema registradas.",
        "help": "Puedo informar disponibilidad, explicar Sentinel y dirigir acciones compatibles del sistema. Categorías activas: {categories}.",
        "limited": "Puedo seguir ayudando con Sentinel y las capacidades activas del sistema, pero esta solicitud necesita razonamiento avanzado que no está disponible ahora. Puedes consultar el estado del sistema, las capacidades disponibles o reintentar cuando haya un proveedor de modelos disponible.",
        "done": "La acción se completó correctamente.",
        "result": "La acción se completó correctamente:\n{result}",
    },
}


class SentinelCoreConversation:
    """Deterministic, truthful conversation kernel. It is not an LLM emulator."""

    def respond(self, request: ConversationRequest, capabilities: Dict[str, Any]) -> str:
        language = self._language(request.message)
        copy = _COPY[language]
        message = request.message.strip().lower()

        if request.tool_result is not None:
            rendered = self._render_result(request.tool_result)
            return copy["result"].format(result=rendered) if rendered else copy["done"]
        if not message:
            return copy["empty"]
        if re.search(r"\b(hello|hi|hey|hola|buenas|buenos días)\b", message):
            return copy["hello"]
        if re.search(r"\b(status|estado|available|disponible|provider|proveedor)\b", message):
            return self._status(copy, capabilities)
        if re.search(r"\b(help|ayuda|capabilities|capacidades|qué puedes|que puedes)\b", message):
            categories = capabilities.get("system", {}).get("categories") or ["conversation"]
            return copy["help"].format(categories=", ".join(categories))
        return copy["limited"]

    @staticmethod
    def _language(message: str) -> str:
        return "es" if re.search(r"[áéíóúñ¿¡]|\b(hola|que|qué|puedes|ayuda|estado|sistema)\b", message.lower()) else "en"

    @staticmethod
    def _status(copy: Dict[str, str], capabilities: Dict[str, Any]) -> str:
        models = capabilities.get("models", {})
        count = int(models.get("available_count", 0))
        model_text = copy["models_on"].format(count=count) if count else copy["models_off"]
        tool_count = int(capabilities.get("system", {}).get("registered_count", 0))
        return copy["status"].format(models=model_text, tools=copy["tools"].format(count=tool_count))

    @staticmethod
    def _render_result(value: Any) -> str:
        if value is None or value == {} or value == []:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
