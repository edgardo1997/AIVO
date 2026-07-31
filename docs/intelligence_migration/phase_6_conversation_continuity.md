# Phase 6: Conversation Continuity

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Create a conversation continuity layer that allows Sentinel to switch between specialized models (e.g., Nemotron → Qwen Coder) without breaking the user experience. The new model must know what was being discussed, what code was mentioned, and what the user's goal is.

## Problem

In a multi-model architecture, different turns may route to different models:

```
User: "explain python"      → Nemotron (reasoning)
User: "create a file"        → Qwen Coder (coding)
```

Without continuity, Qwen Coder only sees `"create a file"` — it doesn't know Python was being explained, what code was discussed, or the user's learning goal.

## Solution: ConversationManager

```
User
↓
ConversationManager
├── BuildContext → ConversationContext (full state)
├── PrepareForModel → ContextPackage (model-specific)
├── SwitchModelContext → preserves summary, goal, personality
└── UpdateAfterTurn → persists to memory
↓
ContextPackage
├── system_context (personality + model info)
├── conversation_summary (compressed history)
├── recent_messages (last turns)
├── active_goal (what user is trying to do)
├── memory_nuggets (relevant preferences)
└── personality_instruction (Sentinel identity)
↓
Model
↓
ConversationManager.update_after_turn()
```

## Architecture Change

### Before (Phase 5)
```
IntentEngine → CapabilityEngine → IntelligenceOrchestrator → ModelRouter → Model
```

### After (Phase 6)
```
IntentEngine → CapabilityEngine → IntelligenceOrchestrator
                                                      ↓
                                              ConversationManager
                                              ├── build_context()
                                              ├── prepare_for_model()
                                              └── switch_model_context()
                                                      ↓
                                              ContextPackage.to_messages()
                                                      ↓
                                              ModelRouter.chat_with_provider()
                                                      ↓
                                              ConversationManager.update_after_turn()
```

## New Components

### `sentinel/core/conversation_manager.py`

#### ConversationContext (dataclass)

| Field | Type | Description |
|---|---|---|
| `conversation_id` | str | Unique conversation identifier |
| `user_id` | str | User owning this conversation |
| `messages` | List[Dict] | Full message history (role/content pairs) |
| `summary` | str | Auto-generated conversation summary |
| `active_task` | str | Inferred user task (e.g., "learning_python") |
| `current_intent` | str | Last classified intent category |
| `current_capabilities` | List[str] | Capabilities for current intent |
| `previous_models` | List[str] | Models used so far in this conversation |
| `metadata` | Dict | Extensible metadata store |

#### ContextPackage (dataclass)

The prepared context for a specific model. Contains only what the model needs:

| Field | Type | Description |
|---|---|---|
| `system_context` | str | Personality + summary + instructions |
| `conversation_summary` | str | Compressed history |
| `recent_messages` | List[Dict] | Recent turns preserved verbatim |
| `active_goal` | str | User's active task/goal |
| `memory_nuggets` | List[str] | Relevant learned preferences |
| `personality_instruction` | str | Base Sentinel identity prompt |
| `model_id` | str | Target model |
| `trimmed/summarized` | bool | Whether context was compressed |
| `total_tokens` | int | Estimated token count |

Key method: **`to_messages(user_message)`** → ready-to-send `List[Dict[str,str]]`

#### PersonalityLayer

Maintains consistent Sentinel identity across model switches:

- `build_recipe(intent, model_id)` → system prompt string
- Supports mode-specific prompts (CODING → "coding mode", REASONING → "analysis mode")
- Extensible via `add_instruction()` / `remove_instruction()`

#### SummaryEngine

Two summary strategies:
- **`build_summary()`** — full preview of each message (up to max_summary_chars)
- **`build_compact_summary()`** — topic-based summary: what user asked + what Sentinel responded

#### MemoryGate

Determines what information is worth remembering:
- Relevant patterns: preferences, learning requests, named entities
- Irrelevant filters: greetings, acknowledgments ("ok", "thanks", "hello")

#### ConversationManager

| Method | Description |
|---|---|
| `build_context()` | Creates/updates ConversationContext from intent + messages |
| `prepare_for_model()` | Builds ContextPackage for a specific model (token-aware) |
| `switch_model_context()` | Handles model transition: saves state, creates summary, adapts context |
| `update_after_turn()` | Appends user/assistant messages, stores relevant memory |
| `clear_context()` | Removes active context |
| `get_context()` / `get_active_contexts()` | Access active contexts |

## ModelRouter Integration

New method: **`chat_with_conversation()`**

```
ModelRouter.chat_with_conversation(
    user_message,
    conversation_context,
    decision,        # IntelligenceDecision
)
  → Uses ConversationManager.prepare_for_model()
  → Calls chat_with_provider()
  → Calls ConversationManager.update_after_turn()
  → Returns result with context_package metadata
```

## Memory Integration

The ConversationManager integrates with existing OperationalMemory:

| Operation | Method | What's Stored |
|---|---|---|
| Load preferences | `_load_memory_nuggets()` | `get_learned_preferences()` → top 5 nuggets |
| Store relevance | `_store_memory_nugget()` | `learn_preference()` for relevant topics |

No new database tables or storage backends were created. All persistence uses the existing `MemoryBackend` protocol.

## Context Window Management Integration

Uses existing `ContextWindowManager`:
- `prepare_for_model()` calls `context_window_manager.manage()` to trim/summarize
- Small context windows (< 16384 tokens) force summarization
- Token counting uses existing `count_messages_tokens()` / `count_tokens()`
- Model window lookup uses existing `get_window()`

## Model Switch Flow

```
switch_model_context(context, old_model, new_model, new_model_window)
  1. Append old_model to context.previous_models
  2. Build compact summary from context.messages
  3. Create system_context = personality + model change info + summary
  4. Run context_window_manager.manage() for new model's window
  5. Load memory nuggets for user
  6. Return ContextPackage with adapted context
```

## Personality Consistency

The `PersonalityLayer` ensures:
- Same base system prompt across all models
- Same custom instructions apply to every model
- Mode hints (coding, reasoning) adapt tone without changing identity
- Model identity is always "Sentinel" regardless of underlying model

## Tests

### `tests/test_conversation_manager.py` — 40 tests

| Test Class | Tests | What it validates |
|---|---|---|
| ConversationContext | 2 | Defaults, to_dict serialization |
| ContextPackage | 3 | Defaults, to_messages with goal injection, to_dict |
| PersonalityLayer | 8 | Default prompt, custom, add/remove instructions, coding/reasoning modes, cross-model consistency, to_dict |
| SummaryEngine | 4 | Empty, single message, compact summary, truncation |
| MemoryGate | 5 | Relevance detection: preferences, learning, greetings |
| ConversationManager | 18 | Build context, intent integration, prepare for model, continuity basics, model switch, update after turn, personality across models, clear context, small window, operational memory, active contexts, serialization |

### Full Suite Results
- **3017 passed**, 1 failed (pre-existing), 1 skipped
- **0 new regressions** from Phase 6
- **215 new tests total** (Phase 1-6): 215/215 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ ConversationManager exists | `sentinel/core/conversation_manager.py` |
| ✅ Models can switch without losing context | `switch_model_context()` preserves summary, goal, history |
| ✅ Automatic summarization exists | `SummaryEngine.build_compact_summary()` |
| ✅ Sentinel personality maintained | `PersonalityLayer` consistent across all models |
| ✅ Context adapts to model size | `ContextWindowManager.manage()` + forced summary for small windows |
| ✅ Uses existing memory | `OperationalMemory.get_learned_preferences()` / `learn_preference()` |
| ✅ No duplicated storage systems | No new tables, backends, or databases |
| ✅ Tests pass | 40/40, full suite 0 regressions |

## Next Steps (Phase 7)

- Wire ConversationManager into AIService.chat() as the primary context provider
- Replace raw history/context building with ConversationManager.build_context()
- Add automatic conversation persistence to database via ConversationManager
- Add summary persistence across sessions
- Add context package caching for repeated model queries
