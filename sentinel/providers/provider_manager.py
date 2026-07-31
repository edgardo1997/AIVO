import json
import logging
import os
import time
from typing import Any, Dict, Iterator, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec, RouterDecision, PROVIDER_URLS, CALL_TIMEOUT, LOCAL_CALL_TIMEOUT, CONNECT_TIMEOUT, FIRST_TOKEN_TIMEOUT_NONLOCAL, FIRST_TOKEN_TIMEOUT_LOCAL, STREAM_IDLE_TIMEOUT

logger = logging.getLogger(__name__)


class ProviderManager:
    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._key_map: Dict[str, str] = {}

    def register_provider(self, provider_id: str, handler: Any) -> None:
        self._providers[provider_id] = handler

    def set_api_key(self, provider_id: str, key: str) -> None:
        self._key_map[provider_id] = key

    def delete_api_key(self, provider_id: str) -> bool:
        return bool(self._key_map.pop(provider_id, None))

    def has_api_key(self, provider_id: str) -> bool:
        return provider_id in self._key_map and bool(self._key_map[provider_id])

    def get_api_key(self, provider_id: str) -> Optional[str]:
        return self._key_map.get(provider_id)

    def _resolve_llm_client(self, provider_id: str, provider: Optional[ProviderSpec] = None) -> Any:
        from openai import OpenAI
        api_key = self._key_map.get(provider_id, os.environ.get(f"SENTINEL_API_KEY_{provider_id.upper()}", ""))
        if not api_key and provider and provider.is_local:
            api_key = provider_id
        base_url = PROVIDER_URLS.get(provider_id, "https://api.openai.com/v1")
        return OpenAI(api_key=api_key, base_url=base_url, timeout=CONNECT_TIMEOUT, max_retries=0)

    def call_provider(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        model = model_override or decision.model
        timeout = timeout or (LOCAL_CALL_TIMEOUT if provider.is_local else CALL_TIMEOUT)
        try:
            client = self._resolve_llm_client(provider.id, provider)
            kwargs = dict(model=model, messages=messages, timeout=timeout)
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            response = client.chat.completions.create(**kwargs)
            result: Dict[str, Any] = {"response": "", "tool_calls": [], "usage": {}}
            choice = response.choices[0] if response.choices else None
            if choice:
                if choice.message.content:
                    result["response"] = choice.message.content
                if choice.message.tool_calls:
                    result["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in choice.message.tool_calls]
            if response.usage:
                result["usage"] = {"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens, "total_tokens": response.usage.total_tokens}
            return result
        except Exception as e:
            logger.error("Provider call failed for %s: %s", provider.id, str(e)[:200])
            raise

    def call_provider_stream(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout_budget: Optional[float] = None) -> Iterator[Dict[str, Any]]:
        model = model_override or decision.model
        try:
            client = self._resolve_llm_client(provider.id, provider)
            first_token_timeout = FIRST_TOKEN_TIMEOUT_LOCAL if provider.is_local else FIRST_TOKEN_TIMEOUT_NONLOCAL
            kwargs = dict(model=model, messages=messages, stream=True, timeout=CONNECT_TIMEOUT)
            stream = client.chat.completions.create(**kwargs)
            yield {"type": "start", "provider": provider.id, "model": model}
            content_accumulated = ""
            last_chunk_time = time.monotonic()
            first_token = True
            for chunk in stream:
                if time.monotonic() - last_chunk_time > STREAM_IDLE_TIMEOUT:
                    yield {"type": "error", "error": "Stream idle timeout"}
                    return
                last_chunk_time = time.monotonic()
                if first_token:
                    elapsed = last_chunk_time - time.monotonic()
                    if elapsed > first_token_timeout:
                        yield {"type": "error", "error": f"First token timeout after {elapsed:.1f}s"}
                        return
                    first_token = False
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    content_accumulated += delta.content
                    yield {"type": "delta", "content": delta.content}
            yield {"type": "done", "content": content_accumulated}
        except Exception as e:
            logger.error("Stream error for %s: %s", provider.id, str(e)[:200])
            yield {"type": "error", "error": str(e)}
