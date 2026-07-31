import logging
from typing import Any, Dict, List, Optional
from sentinel.core.model_router import ProviderSpec, RouterDecision, PROVIDER_URLS, CALL_TIMEOUT

logger = logging.getLogger(__name__)


class OpenAIProvider:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self._api_key = api_key
        self._base_url = base_url or PROVIDER_URLS.get("openai", "https://api.openai.com/v1")

    def chat(self, messages: List[Dict[str, str]], model: str, timeout: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=timeout or CALL_TIMEOUT)
        kwargs = dict(model=model, messages=messages, timeout=timeout or CALL_TIMEOUT)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = client.chat.completions.create(**kwargs)
        result = {"response": "", "tool_calls": [], "usage": {}}
        choice = response.choices[0] if response.choices else None
        if choice:
            if choice.message.content:
                result["response"] = choice.message.content
            if choice.message.tool_calls:
                result["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in choice.message.tool_calls]
        if response.usage:
            result["usage"] = {"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens, "total_tokens": response.usage.total_tokens}
        return result
