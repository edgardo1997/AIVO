# Current Architecture — Sentinel Streaming, Provider Clients and Cancellation

> This document reflects the architecture as of the Phase 8 checkpoint.

## Ownership

- `ProviderManager` (`sentinel/providers/provider_manager.py`) is the authoritative owner of provider HTTP client lifecycle.
- `ModelRouter` (`sentinel/core/model_router.py`) is the authoritative owner of fallback and circuit-breaker decisions.
- `ProviderSelector` (`sentinel/routing/provider_selector.py`) owns routing/selection scoring.
- `sentinel_bridge` (`sidecar/modules/sentinel_bridge.py`) owns the NDJSON stream contract and persistence timing.
- `AIService` (`sidecar/services/ai_service.py`) owns prompt construction and the top-level streaming entry.

## Backend Stream Path

```
request received
  sentinel_bridge /chat/stream
    auth/session validation
    intent classification
    optional governed pipeline
    prompt construction
    AIService.stream_chat
      ModelRouter.chat_stream
        ProviderSelector.select
        for each fallback candidate:
          emit meta
          ProviderManager.call_provider_stream
            OpenAI client
              provider chunks
          emit delta / status / done
    NDJSON serialization
    persistence (after done or on interruption)
    cleanup
```

## Client Lifecycle

- One `OpenAI` client is cached per `provider_id`, keyed on `(api_key, base_url)`.
- Credential changes close and invalidate the cached client.
- `ProviderManager.close()` and `ModelRouter.close()` close all cached clients.
- Client creation is ~344 ms on the test machine; cache hit is ~1.4 µs.

## Timeout Contract

- `call_provider`: `httpx.Timeout(timeout=call_timeout, connect=CONNECT_TIMEOUT)`.
- `call_provider_stream`: `httpx.Timeout(timeout=read_timeout, connect=CONNECT_TIMEOUT)` where `read_timeout` is the `timeout_budget` supplied by `ModelRouter`.
- No stacked retries inside `ProviderManager`; provider adapter `max_retries=0`.
- `ModelRouter` advances the fallback chain only after the active attempt terminates cleanly or raises a recoverable exception.

## Stream Event Order

- `meta` before provider output.
- Optional `status` / `thinking` events for reasoning models.
- `delta` events for visible content.
- `done` terminal event for successful completion.
- `cancelled` terminal event for request disconnect.
- `error` terminal event for timeout or unrecoverable failure.
- `metrics` after `done`.

## Cancellation

- `request.is_disconnected()` is checked each iteration in `sentinel_bridge`.
- `GeneratorExit` is propagated to `ProviderManager.call_provider_stream`, which records `cancelled=True`.
- `sentinel_bridge` emits a `cancelled` event and persists any partial content.
- Cancellation does not trigger fallback.

## Persistence

- Assistant turn is persisted once after stream completion or on interruption.
- `response_parts` are joined once before persistence to avoid repeated string concatenation.
- `_persist_conversation_turn` runs inside `asyncio.to_thread` to keep SQLite writes off the event loop.
- No persistence write occurs before the first token.
- Persistence failures are logged and, for direct calls, propagate as exceptions.

## Known Limitations

- The authenticated frontend-to-pixel stage cannot be measured until the Tauri/WebView runtime is available.
- `sentinel_bridge` `next(iterator)` runs in a thread; a blocked `read()` cannot be interrupted until it returns.
- `OpenAIProvider` (`sentinel/providers/openai_provider.py`) is unused and duplicates `ProviderManager` client creation.
