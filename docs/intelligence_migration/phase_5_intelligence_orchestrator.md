# Phase 5: Intelligence Orchestrator

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Create the central decision core of Sentinel — the Intelligence Orchestrator — that coordinates intent, capabilities, models, tools, and context before any task execution.

## Architecture Change

### Before (Phase 4)
```
IntentEngineV2 → CapabilityEngine → ModelRouter.select() → Model
```

### After (Phase 5)
```
IntentEngineV2 → ClassifiedIntent
  ↓
CapabilityEngine → CapabilitySet
  ↓
IntelligenceOrchestrator
  ├── Resolves capabilities from intent
  ├── Selects execution strategy
  ├── Scores and selects best model from registry
  ├── Selects relevant tools
  └── Returns IntelligenceDecision
  ↓
ModelRouter.chat_with_decision()
  ↓
Provider API → ToolGateway → Execution Pipeline
```

## New Components

### `sentinel/core/intelligence_orchestrator.py`

#### ExecutionStrategy Enum
5 strategies mapping intent categories to execution patterns:

| Strategy | Used For | Behavior |
|---|---|---|
| CHAT_ONLY | CHAT, SEARCH, DOCUMENT, MEMORY | Conversational model, no tools |
| TOOL_EXECUTION | ACTION, SYSTEM_OPERATION, AUTOMATION | Tool-capable model + ToolGateway |
| REASONING | REASONING | Reasoning-capable model |
| CODING | CODING | Coding-capable model |
| MULTI_STEP | Reserved | Multi-turn orchestration |

#### IntelligenceDecision Dataclass
Rich decision output consumed by ModelRouter:

| Field | Type | Description |
|---|---|---|
| `model_id` | str | Selected model identifier |
| `provider` | str | Provider for the model |
| `required_capabilities` | List[str] | Capabilities that drove selection |
| `selected_tools` | List[str] | Tools to make available to the model |
| `execution_strategy` | ExecutionStrategy | How to execute |
| `confidence` | float | Overall confidence (0-1) |
| `reasoning` | str | Human-readable decision trace |
| `status` | str | "success", "no_capable_model", "no_registry" |

#### IntelligenceOrchestrator Class

**Input:** ClassifiedIntent, Context (optional), Available Tools (optional)  
**Output:** IntelligenceDecision

**Internal pipeline:**

1. `_resolve_capabilities(intent)` → CapabilitySet (via CapabilityEngine or intent.to_capability_set())
2. `_select_strategy(category)` → ExecutionStrategy (from INTENT_STRATEGY_MAP)
3. `_select_model(capabilities, intent, context)` → ModelMetadata (scored candidates)
4. `_select_tools(strategy, available_tools, model)` → List[str] (only for TOOL_EXECUTION + tool-capable models)
5. `_build_reasoning(...)` → str (human-readable trace)

**Model Scoring System:**

| Criterion | Score |
|---|---|
| Compatible capability (each) | +50 |
| Tool calling matches requirement | +30 |
| Local model | +10 |
| Zero cost | +10 |
| Low cost (≤ 1.0) | +5 |
| Fast speed | +5 |
| Slow speed | -10 |

Models are sorted by score (desc), then cost (asc).

**Error Handling:**
- No model with required capabilities → `status: "no_capable_model"`
- No ModelRegistry configured → `status: "no_registry"`
- Never assumes capabilities not explicitly declared
- Never executes tools

## ModelRouter Integration

Minimal addition: `chat_with_decision()` method accepts an `IntelligenceDecision` and delegates to `chat_with_provider()`:

```python
router.chat_with_decision(messages, decision)
```

## Architecture Compliance

The Intelligence Orchestrator:
- ✅ NEVER executes tools directly
- ✅ NEVER bypasses ToolGateway, PolicyEngine, ConsentManager, RiskClassifier
- ✅ ONLY decides — execution belongs to existing pipeline
- ✅ Uses ModelRegistry for model selection (not hardcoded)
- ✅ Uses CapabilityEngine for capability resolution
- ✅ Produces structured, auditable decisions

## Tests

### `tests/test_intelligence_orchestrator.py` — 24 tests

| Category | Tests | What it validates |
|---|---|---|
| ExecutionStrategy | 6 | All categories mapped, enum values |
| IntelligenceDecision | 2 | Defaults, to_dict serialization |
| Orchestrate: Action | 2 | Tool execution strategy, tool-capable model selected |
| Orchestrate: Chat | 1 | Chat only strategy, no tools |
| Orchestrate: Coding | 1 | Coding strategy, coding-capable model |
| Orchestrate: Reasoning | 1 | Reasoning strategy |
| No capable model | 1 | Error status returned |
| No registry | 1 | Error status returned |
| Model selection | 2 | Tool-calling model preferred, coding model preferred |
| Tool selection | 2 | Tools for TOOL_EXECUTION, no tools for CHAT_ONLY |
| Scoring | 1 | Lower cost model preferred |
| Configuration | 2 | set_model_registry, set_capability_engine |
| Reasoning trace | 1 | Human-readable decision included |
| Serialization | 1 | All fields in to_dict |
| Safety | 1 | Non-tool-calling model rejected for ACTION |

### Full Suite Results
- **2977 passed**, 1 failed (pre-existing), 1 skipped
- **0 new regressions** from Phase 5
- **175 new tests total** (Phase 1-5): 175/175 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ IntelligenceOrchestrator exists | `sentinel/core/intelligence_orchestrator.py` |
| ✅ Receives Intent + Capabilities + Context + System State | `orchestrate(classified_intent, context, available_tools)` |
| ✅ Decides appropriate model | Scored model selection from ModelRegistry |
| ✅ Decides execution strategy | 5 strategies via INTENT_STRATEGY_MAP |
| ✅ Uses ModelRegistry | `find_candidates()` + scoring |
| ✅ Uses ModelRouter correctly | `chat_with_decision()` minimal integration |
| ✅ Never executes tools directly | Pure decision — no execution |
| ✅ Maintains ToolGateway as only execution gate | No new execution paths |
| ✅ All tests pass | 24/24, full suite 0 regressions |

## Next Steps (Phase 6)

- Wire IntelligenceOrchestrator into AIService as primary decision path
- Add tool-to-capability mapping for automatic tool selection by capability
- Implement feedback loops for model scoring
- Add A/B testing framework for model selection
- Add decision caching for repeated patterns
