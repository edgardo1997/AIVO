# Model Execution Legacy Migration

## Inventory

| Method | File | Status | New path | Notes |
|--------|------|--------|----------|-------|
| `chat` | `sentinel/core/model_router.py` | canonical behind `SENTINEL_CANONICAL_CHAT` | `_chat_canonical` | can switch default after tests |
| `chat_with_provider` | `sentinel/core/model_router.py` | uses `_call_provider` | `_call_provider` → `execute_inference` | non-stream |
| `chat_with_tools` | `sentinel/core/model_router.py` | uses `_call_provider` | `_call_provider` → `execute_inference` | passes `tools` |
| `chat_multi_model` | `sentinel/core/model_router.py` | uses `_call_provider` | `_call_provider` → `execute_inference` | async |
| `_call_provider` | `sentinel/core/model_router.py` | deprecated wrapper | `execute_inference` | warning emitted |
| `call_provider` | `sentinel/providers/provider_manager.py` | deprecated wrapper | `execute_inference` | warning emitted |

## Removal criteria

- `chat` default can be switched to canonical when legacy tests no longer need `_call_provider` mock.
- `_call_provider` can be removed after `chat_with_*` methods migrate to `execute`.
- `call_provider` can be removed after no production caller remains.
