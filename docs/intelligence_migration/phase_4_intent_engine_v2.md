# Phase 4: Intent Engine 2.0

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-29  

## Objective

Evolve the IntentEngine from LLM-dependency to a layered deterministic + LLM hybrid system for reliable, fast, auditable intent classification.

## Architecture Change

### Before
```
User text → LLM → Intent → Pipeline Sentinel
```

### After
```
User text
  ↓
IntentEngineV2
  ├── Layer 1: Fast Rules (deterministic)
  ├── Layer 2: Context (previous intent, active task)
  ├── Layer 3: History (conversation, pronominal references)
  └── Layer 4: LLM Fallback (only when needed)
  ↓
ClassifiedIntent (category, target, confidence, source)
  ↓
CapabilityEngine.resolve()
  ↓
CapabilitySet
  ↓
ModelRouter
  ↓
Execution
```

## New Components

### `sentinel/core/intent_engine_v2.py`

#### IntentCategory Enum
9 official categories:

| Category | Description | Examples |
|---|---|---|
| CHAT | Conversation, greetings | "hola", "hello" |
| ACTION | Execute system actions | "abre chrome", "close notepad" |
| CODING | Code generation, debugging | "crea una función", "fix this bug" |
| SEARCH | Information search | "busca archivos", "search for" |
| DOCUMENT | Document analysis | "lee este archivo", "analiza PDF" |
| SYSTEM_OPERATION | System-level ops | "apaga el equipo", "reboot" |
| AUTOMATION | Automations, tasks | "automatiza", "schedule" |
| MEMORY | Remember/forget | "recuerda esto", "remember" |
| REASONING | Deep analysis | "explícame", "why does" |
| UNKNOWN | Safe fallback | Ambiguous input |

#### ClassifiedIntent Dataclass
Rich output with:

| Field | Type | Description |
|---|---|---|
| `category` | IntentCategory | The classified intent |
| `target` | str | Extracted entity (e.g., "chrome") |
| `confidence` | float | 0.0–1.0 score |
| `source` | str | How it was classified ("rule", "context", "history", "llm") |
| `entities` | dict | Extracted parameters |
| `context_used` | dict | What context influenced the decision |
| `requires_llm` | bool | Whether LLM was needed |
| `explanation` | str | Why this classification |

Methods: `to_intent()` (legacy Intent), `to_capability_set()` (CapabilitySet), `is_actionable` (confidence >= 0.85)

#### Layered Pipeline

**Layer 1: Fast Rules** (17 rules)
Deterministic regex patterns for known cases. Each rule has:
- Pattern (regex)
- IntentCategory
- confidence_bonus (0.25–0.45)
- target_extractor (extracts entity from text)
- Priority (5–12)

Examples of rules:
- `^(?:abre|open|launch|run)\b` → ACTION (bonus 0.40)
- `^(?:ci[eé]rra|close|kill)\b` → ACTION (bonus 0.40)
- `^(?:crea|create|write|generate)\b.*\b(c[oó]digo|function|script)` → CODING (bonus 0.35)
- `\b(?:shutdown|apaga|suspend)\b` → SYSTEM_OPERATION (bonus 0.35)
- `^(?:hola|hello|hi|hey|buenas)$` → CHAT (bonus 0.40)
- `\b(?:expl[ií]came|explain|what is|how does)\b` → REASONING (bonus 0.25)

Scoring: `0.50 + confidence_bonus + (priority * 0.02)`, capped at 0.95

**Layer 2: Context**
Uses `context` dict with:
- `previous_intent` / `intent` — previous intent category + target
- `active_task` — active task context
- `conversation_history` — recent conversation

When previous intent provides category: base confidence 0.65
With target: +0.10
With active_task: +0.10

**Layer 3: History**
Uses `history` list of previous intent dicts:
- Last intent category: base confidence 0.55
- Last target: +0.10
- Pronominal references ("ciérralo", "ábrelo", "hazlo"): +0.25

**Layer 4: LLM Fallback**
Only when:
- No rule matches (or confidence < 0.85)
- No useful context
- No relevant history
- ModelRouter is configured

LLM receives a structured prompt and must return JSON only:
```json
{"category": "ACTION", "target": "chrome", "confidence": 0.7, "entities": {}}
```

The LLM result is used as-is with +0.10 confidence bonus.

#### INTENT_DEFINITIONS
9 categories with descriptions, examples, default confidence, and associated capabilities.

#### INTENT_CATEGORY_CAPABILITY_MAP
Maps each IntentCategory to its required capabilities (compatible with Phase 3 CapabilityEngine).

#### CATEGORY_TO_INTENT_TYPE
Maps IntentCategory to IntentType (from Phase 3) for CapabilityEngine integration.

## Confidence System

| Layer | Base | Bonus | Threshold |
|---|---|---|---|
| Rule match | 0.50 | +0.25 to +0.45 + priority | >= 0.85 |
| Context (prev intent) | 0.65 | +target 0.10 + task 0.10 | >= 0.85 |
| History (last intent) | 0.55 | +target 0.10 + pronoun 0.25 | >= 0.85 |
| LLM | - | +0.10 from LLM confidence | Always accepted |

If confidence >= 0.85 → result used directly (no LLM needed)

## Tests

### `tests/test_intent_engine_v2.py` — 50 tests

| Category | Tests | What it validates |
|---|---|---|
| IntentCategory | 3 | All categories have definitions, capability maps |
| ClassifiedIntent | 6 | Actionable flag, Intent conversion, CapabilitySet, dict |
| Rules: ACTION | 6 | abre, open, launch, cierra, close, reinicia |
| Rules: CHAT | 3 | hola, hello, gracias |
| Rules: CODING | 3 | crea función, write script, corrige error |
| Rules: SEARCH | 2 | busca, search for |
| Rules: DOCUMENT | 2 | lee archivo, analiza PDF |
| Rules: REASONING | 2 | explícame, qué es |
| Rules: SYSTEM_OP | 2 | apaga equipo, reinicia sistema |
| Rules: MEMORY | 1 | recuerda |
| Rules: AUTOMATION | 1 | automatiza |
| Context | 2 | previous_intent, active_task |
| History | 2 | pronominal reference, last intent |
| LLM Fallback | 4 | no router, with router, invalid JSON, no key |
| Unknown | 3 | no crash, empty, whitespace |
| Safety | 3 | never executes tools, CapabilityEngine compat, backward compat |
| Edge Cases | 4 | mixed language, case insensitivity, install, long sentence |

### Full Suite Results
- **2953 passed**, 1 failed (pre-existing), 1 skipped
- **0 new regressions** from Phase 4
- **151 new tests total** (Phase 1+2+3+4): 151/151 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ Intent Engine 2.0 exists | `sentinel/core/intent_engine_v2.py` |
| ✅ Simple intents don't need LLM | 17 rules handle common cases at >= 0.85 confidence |
| ✅ Smart fallback exists | LLM only when rules + context + history insufficient (< 0.85) |
| ✅ Critical decisions have deterministic classification | 0.50 base + rule bonus ensures high confidence |
| ✅ Confidence system exists | 4-layer scoring with threshold gating |
| ✅ Uses context and history | Context (Layer 2) + History (Layer 3) layers |
| ✅ Output compatible with CapabilityEngine | `to_capability_set()` and `CATEGORY_TO_INTENT_TYPE` |
| ✅ No intent executes tools directly | Pure classification only |
| ✅ All tests pass | 50/50, full suite 0 regressions |

## Next Steps (Phase 5)

- Wire IntentEngineV2 into AIService.chat() as primary intent classifier
- Replace old IntentEngine.parse() with IntentEngineV2.classify()
- Add real-time LLM fallback with streaming
- Fine-tune rule patterns based on usage data
- Add user-definable custom rules
