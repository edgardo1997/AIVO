from typing import Any, Dict, List, Optional

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from .loader import load_or_default


_DEFAULT_CONFIG = {
    "max_input_tokens": 128000,
    "max_output_tokens": 4096,
    "blocked_model_ids": [],
    "allowed_providers": ["openai", "anthropic", "ollama", "groq", "mistral", "google"],
    "require_safe_output": True,
}


class AIModelPolicy(Policy):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_config()

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        return load_or_default("ai_policy.yaml", default_factory=lambda: dict(_DEFAULT_CONFIG))

    def policy_id(self) -> str:
        return "ai_model"

    def description(self) -> str:
        return "Restricts which AI models and providers can be used"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        # Configuring a provider is governed by ai.config permissions, but it
        # does not invoke that provider. Provider allowlists apply when a model
        # is actually used, not while an administrator stores a configuration.
        if tool_id == "ai.config":
            return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "AI configuration authorized")
        model = params.get("model") or context.get("ai_model", "")
        provider = params.get("provider") or context.get("ai_provider", "")

        if model and model in self._config.get("blocked_model_ids", []):
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Model '{model}' is blocked",
                {"model": model},
            )

        if provider and provider not in self._config.get("allowed_providers", []):
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Provider '{provider}' is not in the allowed list",
                {"provider": provider},
            )

        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "AI model allowed")


class AIContentPolicy(Policy):
    def policy_id(self) -> str:
        return "ai_content"

    def description(self) -> str:
        return "Enforces token limits and content safety for AI interactions"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        input_tokens = params.get("input_tokens") or 0
        output_tokens = params.get("max_tokens") or 0

        max_input = _DEFAULT_CONFIG["max_input_tokens"]
        max_output = _DEFAULT_CONFIG["max_output_tokens"]

        if isinstance(input_tokens, (int, float)) and input_tokens > max_input:
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Input of {input_tokens} tokens exceeds limit of {max_input}",
                {"input_tokens": input_tokens, "max_input": max_input},
            )

        if isinstance(output_tokens, (int, float)) and output_tokens > max_output:
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Requested output of {output_tokens} tokens exceeds limit of {max_output}",
                {"output_tokens": output_tokens, "max_output": max_output},
            )

        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "AI content allowed")


AI_POLICIES = [AIModelPolicy, AIContentPolicy]
