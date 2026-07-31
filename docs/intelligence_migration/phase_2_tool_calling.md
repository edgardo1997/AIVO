# Phase 2: Tool Calling Real

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Evolve Sentinel from text-only model interaction to structured tool calling. Models with `supports_tool_calling=True` now receive available tool schemas and can generate structured tool calls that pass through the full ToolGateway security pipeline.

## Architecture Changes

### Before (Phase 1)
```
Model
  ↓
Text generation only
  ↓
Sentinel interprets intent from text
  ↓
ToolGateway (manual intent → tool mapping)
```

### After (Phase 2)
```
Model (supports_tool_calling=True)
  ↓
Structured Tool Call (JSON)
  ↓
ModelRouter._handle_tool_calls()
  ├── Validate model compatibility
  ├── ToolGateway.execute()
  │   ├── Identity Gate
  │   ├── Authorization Gate
  │   ├── Consent Gate
  │   ├── Policy Engine
  │   ├── Risk Assessment
  │   └── Executor
  ├── Result → append to messages
  └── LLM receives tool result → final response
```

## New Files

### `sentinel/core/tool_schema_adapter.py`
Converts internal `ToolSpec` objects to OpenAI-compatible tool schemas.

| Function | Purpose |
|---|---|
| `to_openai_tool(tool_spec)` | Single ToolSpec → `{"type":"function","function":{...}}` |
| `to_openai_tools(specs)` | Batch convert, filters DISABLED tools |
| `parse_tool_call(response_message)` | Parse OpenAI response for tool_calls |
| `build_assistant_tool_message(tool_calls)` | Build assistant message with tool_calls |
| `build_tool_result_message(id, name, result)` | Build tool result message |
| `build_tool_error_message(id, name, error)` | Build tool error message |

Key behavior:
- DISABLED tools are filtered out (never sent to the model)
- Empty parameters default to `{"type":"object","properties":{}}`
- Invalid JSON in tool call arguments defaults to `{}`
- NEVER executes tools — only transforms data

## Modified Files

### `sentinel/core/model_router.py`

**New attributes:**
- `_tool_gateway: Optional[ToolGateway]` — injected via `set_tool_gateway()`
- `_tool_calling_max_recursion: int` — max tool call rounds (default 5)

**New methods:**

| Method | Purpose |
|---|---|
| `set_tool_gateway(gateway)` | Inject a ToolGateway reference |
| `_validate_tool_call_compatibility(model_id, provider_id)` | Check `supports_tool_calling` in ModelRegistry — **rejects if False** |
| `_execute_tool_call(tool_call, context)` | Execute a single tool call via ToolGateway (async bridge) |
| `_handle_tool_calls(tool_calls, provider_id, model_id, context)` | Validate model + execute all tool calls |
| `chat_with_tools(messages, tools, task_type, ...)` | Full tool-calling orchestration loop |

**Modified method:**

`_call_provider()` — now accepts optional `tools` parameter. When provided:
- Adds `tools` and `tool_choice="auto"` to the API request
- Parses `tool_calls` from the response
- Returns `tool_calls` in the response dict alongside `response`

**Tool calling flow (`chat_with_tools`):**

1. Convert ToolSpecs to OpenAI schema via `to_openai_tools()`
2. Check if registry has tool-capable models
3. Select model via `select()` (or provided override)
4. Call LLM with tools
5. If response has `tool_calls`:
   a. Validate model supports tool calling (`_validate_tool_call_compatibility`)
   b. For each tool call: execute via `ToolGateway.execute()`
   c. Append assistant message + tool results to conversation
   d. Loop back to step 4 (up to `max_tool_rounds`)
6. Return final text response

### Protection: Incompatible Model Rejection

When `_handle_tool_calls()` detects a tool_call from a model with `supports_tool_calling=False`:

```python
RuntimeError: Tool calling rejected: model 'nemotron' (provider=nvidia-nemotron)
does not support tool calling
```

This is checked via `_validate_tool_call_compatibility()`:
- If no ModelRegistry set → allow (backward compat)
- If model not found in registry → allow (backward compat)
- If model found and `supports_tool_calling=True` → allow
- If model found and `supports_tool_calling=False` → **reject with error**

## Models and Tool Calling

Models are registered in `sentinel/models/default_registry.py`. For Phase 2, all default models have `supports_tool_calling=False`. Models must be explicitly registered with `supports_tool_calling=True` to enable tool calling.

When `chat_with_tools()` is called:
1. It checks `self._model_registry.find_candidates(["tool_calling"])`
2. If no tool-capable models exist → falls back to normal chat
3. The model selected must have `supports_tool_calling=True` for tools to be sent

## Security

All tool executions pass through the **existing** ToolGateway pipeline:
- Identity Gate (authentication check)
- Authorization Gate (permissions check)
- Consent Gate (user consent)
- Policy Engine (policy evaluation)
- Risk Assessment (risk classification)
- Executor (actual execution with timeout)
- Quality Gate (output scanning)
- Audit logging (all decisions logged)

No new execution path bypasses security. The `_execute_tool_call` method calls `ToolGateway.execute()` which enforces the complete security pipeline.

## Tests

### `tests/test_tool_calling.py` — 27 tests

| Category | Tests | What it validates |
|---|---|---|
| ToolSchemaAdapter | 13 | Schema conversion, disabled filtering, parse_tool_call, message builders |
| ModelRouter Tool Calling | 11 | `set_tool_gateway`, validation, rejection, execution, fallback |
| Model Selection | 2 | Capability-based selection for tool calling |
| Protection | 1 | Rejection of incompatible model tool calls |

### Full Suite Results
- **2869 passed**, 2 failed, 1 skipped
- 2 failures are pre-existing (unrelated: `test_backend_has_no_shell_or_free_command_execution`, `test_similar_texts_have_higher_sim`)
- **0 new regressions** from Phase 2 changes
- **68 new tests total** (Phase 1 + Phase 2): 68/68 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ModelRouter sends tools only to compatible models (supports_tool_calling=True) | ✅ |
| Tool-capable models can generate structured tool calls | ✅ |
| Tool calls pass through ToolGateway (full security pipeline) | ✅ |
| No model can execute tools directly (bypassing ToolGateway) | ✅ |
| Models without tool calling continue working as chat | ✅ |
| Automated tests exist and pass | ✅ |
| Sentinel maintains existing security | ✅ |
| Incompatible model tool calls are rejected with controlled error | ✅ |
| DISABLED tools are never sent to models | ✅ |
| Max recursion prevents infinite tool calling loops | ✅ |

## Next Steps (Phase 3)

- Update `sentinel/models/default_registry.py` to mark specific models with `supports_tool_calling=True`
- Wire `chat_with_tools()` into `AIService.chat()` as the primary path
- Add `tool_choice` override support (force specific tool)
- Streaming support for tool calls in `chat_stream()`
- Tool call analytics and monitoring
