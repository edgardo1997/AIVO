import json
import logging
import os
import time
from typing import Any, Callable, Dict, Iterator, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec, RouterDecision, PROVIDER_URLS, CALL_TIMEOUT, LOCAL_CALL_TIMEOUT, CONNECT_TIMEOUT, FIRST_TOKEN_TIMEOUT_NONLOCAL, FIRST_TOKEN_TIMEOUT_LOCAL, STREAM_IDLE_TIMEOUT, classify_provider_error
from sentinel.core.provider_performance import ProviderPerformanceObservation, ProviderPerformanceStore

logger = logging.getLogger(__name__)


class ProviderManager:
    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._key_map: Dict[str, str] = {}
        self._performance_store: Optional[ProviderPerformanceStore] = None
        self._clients: Dict[str, Any] = {}
        self._client_configs: Dict[str, tuple] = {}

    def close(self):
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                logger.debug("Failed to close OpenAI client for %s", client, exc_info=True)
        self._clients.clear()
        self._client_configs.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def set_performance_store(self, store: Optional[ProviderPerformanceStore]) -> None:
        self._performance_store = store

    def _record(
        self,
        provider_id: str,
        model_id: str,
        success: bool,
        timeout: bool = False,
        cancelled: bool = False,
        error: Optional[Exception] = None,
        **timings: Any,
    ) -> None:
        if self._performance_store is None:
            return
        try:
            error_category = None
            if error is not None:
                error_category = classify_provider_error(error, provider_id).get("category")
            obs = ProviderPerformanceObservation(
                provider_id=provider_id,
                model_id=model_id,
                success=success,
                timeout=timeout,
                cancelled=cancelled,
                error_category=error_category,
                **timings,
            )
            self._performance_store.record(obs)
        except Exception:
            logger.debug("Failed to record performance observation for %s", provider_id)

    def register_provider(self, provider_id: str, handler: Any) -> None:
        self._providers[provider_id] = handler

    def _drop_client(self, provider_id: str) -> None:
        client = self._clients.pop(provider_id, None)
        if client is not None:
            try:
                client.close()
            except Exception:
                logger.debug("Failed to close OpenAI client for %s", provider_id, exc_info=True)
        self._client_configs.pop(provider_id, None)

    def set_api_key(self, provider_id: str, key: str) -> None:
        self._key_map[provider_id] = key
        self._drop_client(provider_id)

    def delete_api_key(self, provider_id: str) -> bool:
        had = provider_id in self._key_map
        if had:
            self._drop_client(provider_id)
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
        config = (api_key, base_url)
        cached = self._clients.get(provider_id)
        if cached is not None and self._client_configs.get(provider_id) == config:
            return cached
        self._drop_client(provider_id)
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=CONNECT_TIMEOUT, max_retries=0)
        self._clients[provider_id] = client
        self._client_configs[provider_id] = config
        return client

    def call_provider(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        model = model_override or decision.model
        timeout = timeout or (LOCAL_CALL_TIMEOUT if provider.is_local else CALL_TIMEOUT)
        start = time.monotonic()
        try:
            client = self._resolve_llm_client(provider.id, provider)
            max_tokens = 256 if decision.task_type == TaskType.QUICK else 768
            kwargs = dict(model=model, messages=messages, timeout=timeout, max_tokens=max_tokens)
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
            total_ms = (time.monotonic() - start) * 1000
            self._record(
                provider.id, model, success=True,
                connection_ms=0.0, total_provider_ms=total_ms,
                output_tokens=result["usage"].get("completion_tokens", 0),
            )
            return result
        except Exception as e:
            total_ms = (time.monotonic() - start) * 1000
            self._record(
                provider.id, model, success=False, error=e,
                total_provider_ms=total_ms,
            )
            logger.error("Provider call failed for %s: %s", provider.id, str(e)[:200])
            raise

    def call_provider_stream(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout_budget: Optional[float] = None) -> Iterator[Dict[str, Any]]:
        model = model_override or decision.model
        try:
            client = self._resolve_llm_client(provider.id, provider)
            first_token_timeout = FIRST_TOKEN_TIMEOUT_LOCAL if provider.is_local else FIRST_TOKEN_TIMEOUT_NONLOCAL
            max_tokens = 256 if decision.task_type == TaskType.QUICK else 768
            kwargs = dict(model=model, messages=messages, stream=True, timeout=CONNECT_TIMEOUT, max_tokens=max_tokens)
            
            # TIMING STAGE 1: Provider Request Started
            provider_request_started_at = time.monotonic()
            logger.info(f"[TIMING] Provider Request Started: {provider.id}/{model}")
            
            stream = client.chat.completions.create(**kwargs)
            
            # TIMING STAGE 2: Connection Established (HTTP response headers received)
            connection_established_at = time.monotonic()
            connection_time_ms = (connection_established_at - provider_request_started_at) * 1000
            logger.info(f"[TIMING] Connection Established: {connection_time_ms:.2f}ms")
            
            yield {"type": "start", "provider": provider.id, "model": model}
            content_accumulated = ""
            last_chunk_time = connection_established_at
            last_progress_emit = connection_established_at
            reasoning_active = False
            first_token = True
            first_visible_content = True
            token_count = 0
            first_token_received_at = None
            for chunk in stream:
                now = time.monotonic()
                if first_token:
                    elapsed = now - provider_request_started_at
                    if elapsed > first_token_timeout:
                        raise TimeoutError(f"First token timeout after {elapsed:.1f}s")
                    first_token = False
                elif now - last_chunk_time > STREAM_IDLE_TIMEOUT:
                    raise TimeoutError("Stream idle timeout")
                last_chunk_time = now
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    if first_visible_content:
                        # TIMING STAGE 3: First Token Received (TTFT)
                        first_token_received_at = now
                        ttft_ms = (first_token_received_at - provider_request_started_at) * 1000
                        logger.info(
                            "First visible token from %s/%s in %.2fs (TTFT: %.2fms)",
                            provider.id,
                            model,
                            now - provider_request_started_at,
                            ttft_ms
                        )
                        first_visible_content = False
                    content_accumulated += delta.content
                    token_count += 1
                    yield {"type": "delta", "content": delta.content}
                elif delta and getattr(delta, "reasoning_content", None):
                    # Reasoning-capable providers can stream internal tokens before
                    # visible text. Keep the bridge alive without exposing them.
                    if not reasoning_active or now - last_progress_emit >= 1.0:
                        yield {"type": "status", "stage": "thinking"}
                        last_progress_emit = now
                        reasoning_active = True
            if not content_accumulated:
                raise RuntimeError("Provider returned no visible content")
            
            # TIMING STAGE 4: Final Token Received
            final_token_received_at = time.monotonic()
            provider_request_completed_at = final_token_received_at
            
            # Calculate corrected timing metrics
            total_provider_duration_ms = (provider_request_completed_at - provider_request_started_at) * 1000
            ttft_ms = (first_token_received_at - provider_request_started_at) * 1000 if first_token_received_at else total_provider_duration_ms
            post_first_token_generation_ms = (final_token_received_at - first_token_received_at) * 1000 if first_token_received_at else 0
            
            # Calculate generation speed correctly (tokens / post-first-token time)
            generation_tokens_per_second = (token_count / post_first_token_generation_ms * 1000) if post_first_token_generation_ms > 0 else 0
            
            logger.info(
                f"[TIMING] Provider Request Complete: {total_provider_duration_ms:.2f}ms, "
                f"TTFT: {ttft_ms:.2f}ms, "
                f"Post-First-Token: {post_first_token_generation_ms:.2f}ms, "
                f"Output Tokens: {token_count}, "
                f"Generation Speed: {generation_tokens_per_second:.1f} tok/s"
            )
            
            self._record(
                provider.id,
                model,
                success=True,
                connection_ms=connection_time_ms,
                ttft_ms=ttft_ms,
                generation_ms=post_first_token_generation_ms,
                total_provider_ms=total_provider_duration_ms,
                output_tokens=token_count,
                generation_tokens_per_second=generation_tokens_per_second,
            )
            yield {
                "type": "done", 
                "content": content_accumulated,
                "timing": {
                    "provider_request_started_at": provider_request_started_at,
                    "connection_established_at": connection_established_at,
                    "first_token_received_at": first_token_received_at,
                    "final_token_received_at": final_token_received_at,
                    "provider_request_completed_at": provider_request_completed_at,
                    "ttft_ms": ttft_ms,
                    "post_first_token_generation_ms": post_first_token_generation_ms,
                    "total_provider_duration_ms": total_provider_duration_ms,
                    "output_tokens": token_count,
                    "generation_tokens_per_second": generation_tokens_per_second
                }
            }
        except TimeoutError as e:
            self._record(
                provider.id, model, success=False, timeout=True, error=e,
                total_provider_ms=(time.monotonic() - provider_request_started_at) * 1000,
            )
            logger.error("Stream error for %s: %s", provider.id, str(e)[:200])
            raise
        except Exception as e:
            self._record(
                provider.id, model, success=False, error=e,
                total_provider_ms=(time.monotonic() - provider_request_started_at) * 1000,
            )
            logger.error("Stream error for %s: %s", provider.id, str(e)[:200])
            raise
