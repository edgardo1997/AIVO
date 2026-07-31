# Phase 3: Capability Engine

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Create a new intelligence layer that translates user intents into required capabilities, decoupling "what the user wants" from "what capabilities Sentinel needs" and ultimately "which model has those capabilities".

## Architecture Change

### Before (Phase 2)
```
Intent
  ↓
ModelRouter.select(task_type)
  ↓
Model selected
```

### After (Phase 3)
```
Intent
  ↓
CapabilityEngine.resolve(intent)
  ↓
CapabilitySet (required capabilities)
  ↓
ModelRegistry.find_candidates(capabilities)
  ↓
ModelRouter.select(capabilities=...)
  ↓
Model with matching capabilities
```

## New Files

### `sentinel/core/capability_engine.py`

Three components:

#### 1. `IntentType` Enum
```python
class IntentType(Enum):
    CHAT = "CHAT"        # conversation, personality
    ACTION = "ACTION"    # tool_calling, system_access, risk_analysis
    CODING = "CODING"    # coding, reasoning
    DOCUMENT = "DOCUMENT"# vision, long_context
    SEARCH = "SEARCH"    # internet, grounding
    UNKNOWN = "UNKNOWN"  # safe fallback → conversation
```

#### 2. `CapabilitySet`
Wrapper around `Set[str]` with rich query methods:

| Method | Purpose |
|---|---|
| `has(capability)` | Check single capability |
| `has_all(list)` | Check all required capabilities exist |
| `has_any(list)` | Check any of the candidates exist |
| `add(capability)` | Add single capability |
| `merge(other)` | Combine two CapabilitySets |
| `to_list()` | Sorted list of capabilities |
| `to_dict()` | `{"capability": True, ...}` |

#### 3. `CapabilityEngine`
Main resolver with methods:

| Method | Purpose |
|---|---|
| `resolve(intent)` | Intent → CapabilitySet |
| `get_capabilities_for(intent_type)` | Get capabilities for a type |
| `register_intent_mapping(type, caps)` | Add/override mapping |
| `list_registered_intents()` | List all registered mappings |

### Initial Intent → Capability Map (INTENT_CAPABILITY_MAP)

| Intent | Required Capabilities |
|---|---|
| CHAT | conversation, personality |
| ACTION | tool_calling, system_access, risk_analysis |
| CODING | coding, reasoning |
| DOCUMENT | vision, long_context |
| SEARCH | internet, grounding |
| UNKNOWN | conversation (safe fallback) |

## Integration with Existing Intent

The CapabilityEngine accepts three input types:
1. **`IntentType` enum** — direct type specification
2. **`Intent` dataclass** (from `sentinel/core/intent.py`) — maps `action` field:
   - `"execute"`, `"launch"` → ACTION
   - `"analyze"`, `"diagnose"` → CODING
   - `"query"`, `"search"` → SEARCH
   - `"configure"`, `"chat"`, `"talk"` → CHAT
   - `"read"`, `"document"`, `"vision"` → DOCUMENT
   - Anything else → CHAT (safe fallback)
3. **`str`** — by name ("CHAT", "ACTION") or by action ("execute", "analyze")

## Unknown Intent Handling

All unknown/unrecognized intents resolve to `["conversation"]` — a safe fallback that guarantees the system never breaks on new intent types.

## Tests

### `tests/test_capability_engine.py` — 33 tests

| Category | Tests | What it validates |
|---|---|---|
| IntentType | 2 | Enum values, map coverage |
| CapabilitySet | 11 | Creation, has/has_all/has_any, add/remove/merge, dict/iter/repr |
| CapabilityEngine | 20 | All 5 intent types, UNKNOWN fallback, Intent object resolution, string resolution, custom maps, registration, listing |

### Full Suite Results
- **2903 passed**, 1 failed (pre-existing, unrelated), 1 skipped
- **0 new regressions** from Phase 3
- **101 new tests total** (Phase 1+2+3): 101/101 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ CapabilityEngine exists | `sentinel/core/capability_engine.py` |
| ✅ CapabilitySet exists | Rich query methods on capability collections |
| ✅ Intents can be converted to capabilities | `resolve(intent)` → CapabilitySet |
| ✅ System does NOT select models yet | CapabilityEngine is pure translation |
| ✅ Does NOT execute tools | No tool execution capability |
| ✅ Maintains backward compatibility | No changes to existing code paths |
| ✅ Automated tests exist | 33 tests, all passing |
| ✅ Unknown intents handled safely | Fallback to `["conversation"]` |

## Next Steps (Phase 4)

- Integrate CapabilityEngine with ModelRouter (use capabilities for model selection)
- Connect IntentEngine → CapabilityEngine → ModelRouter in AIService
- Add capability scoring to rank models by capability match
- Extend INTENT_CAPABILITY_MAP with additional intent types
- Add dynamic capability inference for custom intents
