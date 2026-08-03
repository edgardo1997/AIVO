import logging
from typing import Any, Dict, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec

logger = logging.getLogger(__name__)


TOOL_CALLING_MODELS: Dict[str, List[str]] = {
    "openai": ["gpt-4", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "openrouter": ["gpt-4o", "claude-3.5-sonnet", "deepseek/deepseek-v4-flash"],
    "groq": ["llama-3.3-70b-versatile", "mixtral-8x7b"],
    "gemini": ["gemini-2.5-flash"],
    "github_models": ["gpt-4o", "gpt-4o-mini"],
    "deepseek": ["deepseek/deepseek-v4-flash"],
    "nvidia-nemotron": ["nvidia/nemotron-3-super-120b-a12b"],
    "anthropic": ["claude-3.5-sonnet"],
}


class CapabilitySelector:
    def __init__(self):
        self._model_registry = None

    def set_model_registry(self, registry) -> None:
        self._model_registry = registry

    def validate_tool_call_compatibility(self, model_id: str, provider_id: str) -> bool:
        if self._model_registry is None:
            return True
        model = self._model_registry.get(model_id)
        if model is None:
            return True
        if not getattr(model, "supports_tool_calling", True):
            logger.error(
                "Tool calling rejected: model '%s' (provider=%s) has supports_tool_calling=False",
                model_id, provider_id,
            )
            return False
        return True
