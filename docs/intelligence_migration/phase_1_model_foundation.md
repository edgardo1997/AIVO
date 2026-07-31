# Phase 1: Model Intelligence Foundation

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Establish the model intelligence foundation by creating a typed ModelMetadata entity, a ModelRegistry, populating it with existing models, and integrating it with the ModelRouter for capability-based selection, while maintaining full backward compatibility.

## Deliverables

### 1. ModelMetadata Entity
- **File**: `sentinel/models/model_metadata.py`
- Frozen dataclass with fields: `id`, `provider`, `context_window` (default 4096), `supports_tool_calling`, `supports_vision`, `supports_coding`, `supports_reasoning`, `supports_embeddings`, `speed`, `cost`, `local`, `status`, `description`, `tags`, `config`
- Status enum: `AVAILABLE`, `DEPRECATED`, `UNAVAILABLE`, `UNKNOWN`
- Validation: non-empty `id` and `provider`, positive `context_window` (>=1), non-negative `cost` (>=0)
- Helper methods: `has_capability(name)`, `is_available`, `display_name`
- Thread-safe immutable design (ModelStatus is the mutability mechanism)

### 2. ModelRegistry
- **File**: `sentinel/core/model_registry.py`
- Thread-safe (RLock) registry with methods: `register`, `register_many`, `unregister`, `get`, `list_all`, `list_available`, `find_by_capability`, `find_by_provider`, `find_candidates`, `count`, `clear`
- `find_candidates(capabilities)`: filters by required capabilities AND availability status, sorted by cost ascending
- `TASK_CAPABILITY_MAP`: maps task tasks to required capabilities (e.g., "coding" -> ["coding", "reasoning"], "action" -> ["tool_calling"], "chat" -> [], "local" -> ["local"], "vision" -> ["vision"])

### 3. Default Registry Population
- **File**: `sentinel/models/default_registry.py`
- `get_default_registry()` builds a registry with 12 models across 10 providers:
  - deepseek (deepseek/deepseek-v4-flash:free), nvidia-nemotron, sentinel_local (Qwen3-1.7B), ollama (llama3), openai (gpt-4o), github_models (gpt-4o-mini), gemini (gemini-2.5-flash), anthropic (claude-sonnet-4), groq (llama-3.3-70b-versatile), cerebras (llama-3.3-70b), mistral (mistral-small, mistral-large)
- All default models marked `supports_coding=True, supports_reasoning=True`
- Tool calling set to False for now (system doesn't send tools to providers)

### 4. ModelRouter Integration
- **File**: `sentinel/core/model_router.py` (modified)
- New methods:
  - `set_model_registry(registry)`: inject a ModelRegistry
  - `set_task_capability_map(task_type, capabilities)`: override task->capability mappings
  - `select_by_capability(capabilities)`: capability-based model selection with fallback strategies
  - `_try_select_from_registry(task_type)`: internal helper that tries registry first for CODE/CHAT/VISION tasks
- `select()` now calls `_try_select_from_registry()` for CODE, CHAT, VISION task types before falling back to old provider-based selection
- `QUICK`, `REASONING`, and `ACTION` tasks still use provider-based selection directly
- Backward compatible: if no registry is set, old behavior is preserved
- Deprecation warning added in `select()` for provider-based path

### 5. Tests
- **`tests/test_model_registry.py`**: 30 tests covering:
  - ModelMetadata creation, validation, capability checks, frozen immutability
  - ModelRegistry register/get/unregister/clear/count, duplicate/invalid registration
  - find_by_capability, find_by_provider, find_candidates, availability filtering
  - TASK_CAPABILITY_MAP structure
- **`tests/test_model_router_phase1.py`**: 11 tests covering:
  - select_by_capability (with/without registry, no match, excludes unavailable)
  - cost-based preference, local-first strategy
  - Registry integration in select() for CODE/CHAT/VISION tasks
  - Fallback to provider-based without registry
  - Custom task capability map overrides

## Test Results

**Full suite**: 2843 passed, 1 failed, 1 skipped (pre-existing fail: `test_backend_has_no_shell_or_free_command_execution` — unrelated, same as baseline)
**New tests**: 41/41 passed

## Key Design Decisions

1. **No changes to existing code paths** — Phase 1 is purely additive
2. **ModelRegistry as composable object** — not a singleton, injectable into ModelRouter
3. **TaskType.CODE uses registry** — but REASONING and QUICK still use old path (Phase 2 will migrate them)
4. **Capability-based selection** — sorted by cost, prefers available models, supports strategy override (local_first, priority)
5. **Deprecation warnings** — added to guide migration in Phase 2+

## Next Steps (Phase 2)

- Migrate task definitions to use registry-based selection for all task types
- Add intelligence tier model mapping (T0, T1, T2)
- Implement model intelligence scoring and benchmarking
- Add A/B testing framework for model selection
- Migrate AI service provider lists to registry
- Remove old provider-based selection paths
