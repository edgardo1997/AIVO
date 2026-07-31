# Phase 8: Cost + Resource Intelligence

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-30  

## Objective

Add a resource intelligence layer to Sentinel's model selection pipeline so that decisions consider hardware availability, network connectivity, budget constraints, and system state — not just capability matching.

## Problem

Before Phase 8, the orchestration pipeline only asked:

> *Which model has the required capabilities?*

It did not ask:

| Question | Source |
|---|---|
| Is there internet? | NetworkMonitor |
| Is there enough RAM? | psutil / hardware |
| Is the budget exceeded? | CostTracker |
| Is the battery low? | psutil sensors |
| Is the GPU powerful enough? | gpu_manager |
| Is power saver active? | power_manager |

## Solution

```
Intent → Capabilities → ModelRegistry → Candidates
                                              ↓
                                    ResourceIntelligenceLayer
                                    ├── snapshot() → SystemSnapshot
                                    ├── evaluate(model, state) → ResourceDecision
                                    │     ├── allowed? (reject if offline, no RAM, no budget)
                                    │     ├── score_modifier (bonus for local, penalty for slow)
                                    │     └── restrictions list
                                    └── filter_candidates() → only compatible models
                                              ↓
                                    Scored + filtered candidates
                                              ↓
                                    Model selected
```

## New Component

### `sentinel/core/resource_intelligence.py`

#### SystemSnapshot (dataclass)

Captures system state at decision time:

| Field | Source | Description |
|---|---|---|
| `online` | NetworkMonitor.is_online | Internet connectivity |
| `ram_available_gb` | psutil.virtual_memory().available | Available RAM |
| `ram_total_gb` | psutil.virtual_memory().total | Total RAM |
| `battery_percent` | psutil.sensors_battery() | Battery level (None if desktop) |
| `on_battery` | psutil.sensors_battery().power_plugged | Running on battery |
| `gpu_available` | gpu_manager.list_gpus() | NVIDIA GPU present |
| `gpu_memory_free_mb` | gpu_manager GPU info | Free VRAM |
| `cpu_load_pct` | psutil.cpu_percent() | Current CPU load |
| `power_saver_active` | power_manager.get_active_plan() | Power saver enabled |
| `budget_remaining_usd` | CostTracker.check_budgets() | Remaining budget |
| `has_budget_constraint` | CostTracker.get_budgets() | Budget configured |

Properties: `ram_available_pct`, `low_resources` (RAM < 15% OR battery < 20% OR power saver)

#### ResourceDecision (dataclass)

| Field | Description |
|---|---|
| `allowed` | True if model can be used |
| `reason` | Human-readable explanation |
| `score_modifier` | Integer adjustment to model score |
| `restrictions` | List of restriction tags (offline, insufficient_ram, budget_exceeded) |

#### ResourceIntelligenceLayer

| Method | Description |
|---|---|
| `snapshot()` | Captures current system state from all monitors |
| `evaluate(model, state)` | Returns ResourceDecision: allowed/rejected, score modifier, reasons |
| `evaluate_all(candidates, state)` | Evaluates all candidates at once |
| `filter_candidates(candidates, state)` | Returns only allowed candidates |
| `find_fallback(candidates, rejected_ids, state)` | Finds next allowed candidate |

#### Evaluation Rules

**Hard Rejections** (score_modifier = -100, cannot be overridden):

| Condition | Reason |
|---|---|
| Cloud model + offline | "requires internet but system is offline" |
| RAM < model requirement | "Insufficient RAM: need XGB, have YGB" |
| VRAM < model requirement | "Insufficient VRAM: need XMB, have YMB" |
| Cost > budget remaining | "Cost $X exceeds remaining budget $Y" |

**Score Modifiers** (positive = bonus, negative = penalty):

| Condition | Modifier |
|---|---|
| Local model when offline | +30 |
| Local model | +10 |
| Local model on battery | +15 |
| Power saver active + local | +10 |
| Cloud model on battery | -20 |
| Free model (cost=0) | +5 |
| RAM < 20% available | -25 |
| CPU load > 80% | -15 |
| Slow model | -10 |

## Integration with IntelligenceOrchestrator

Minimal changes to `intelligence_orchestrator.py`:

- Added `_resource_intelligence` field and `set_resource_intelligence()` method
- Modified `_select_model()` to call `ResourceIntelligenceLayer.evaluate()` on each candidate
- Rejected models are logged and filtered out before scoring
- Modified `_score_model()` accepts optional `ResourceDecision` to include `score_modifier`
- Modified `_build_reasoning()` includes resource decision in explanation
- If all candidates are rejected by resources, returns `status: "no_capable_model"` with descriptive reason

## Integration with ModelCoordinator

For multi-model plans in Phase 7, the ResourceIntelligenceLayer can be used per-task in `select_specialist()`. Each subtask's model is evaluated independently for resource compatibility.

## Hardware Requirement Database

Built-in rules for local model size → hardware requirements:

| Model Size | Min RAM | Min VRAM |
|---|---|---|
| 70B | 64 GB | 48 GB |
| 40B | 32 GB | 24 GB |
| 13B | 16 GB | 8 GB |
| 7B | 8 GB | 4 GB |
| 3B | 4 GB | 2 GB |
| 1B | 2 GB | 1 GB |

Detection is by substring match in model ID (e.g., "llama-70b" → 70B requirements).

## Tests

### `tests/test_resource_intelligence.py` — 36 tests

| Test Class | Tests | What it validates |
|---|---|---|
| SystemSnapshot | 6 | RAM percentage, low resources detection (RAM/battery/power saver), to_dict |
| ResourceDecision | 3 | Defaults, rejection, to_dict |
| ResourceIntelligenceLayer | 18 | Offline rejection, local model acceptance, RAM rejection, VRAM rejection, evaluate_all, filter_candidates, scoring bonuses/penalties (local, battery, slow, CPU, RAM), budget rejection, free model, fallback selection, cloud providers |
| OrchestratorIntegration | 4 | Cloud rejection, full rejection fallback, scoring affected by resource modifiers, reasoning includes resource info |

### Full Suite Results
- **3095 passed**, 1 failed (pre-existing), 1 skipped
- **0 new regressions** from Phase 8
- **293 new tests total** (Phase 1-8): 293/293 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ Sentinel knows hardware state | `SystemSnapshot.ram_available_gb`, `gpu_memory_free_mb`, `cpu_load_pct` |
| ✅ Sentinel knows network availability | `SystemSnapshot.online` from NetworkMonitor |
| ✅ Sentinel considers costs | `SystemSnapshot.budget_remaining_usd` from CostTracker |
| ✅ Can reject incompatible models | `ResourceDecision(allowed=False)` with reason |
| ✅ Can auto-select local models | `score_modifier: +30` when offline, `+10` local bonus |
| ✅ Can do intelligent fallback | `find_fallback()` finds next allowed model |
| ✅ Decisions are explainable | `ResourceDecision.reason` and `restrictions` list |
| ✅ ModelCoordinator can use this layer | Per-task evaluation possible |
| ✅ IntelligenceOrchestrator maintains control | Only scoring/filtering added, no execution paths |
| ✅ All tests pass | 36/36, full suite 0 regressions |
