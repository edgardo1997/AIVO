# Phase 7: Multi-Model Execution

**Status**: COMPLETED  
**Branch**: `feature/sentinel-intelligence-migration`  
**Date**: 2026-07-30  

## Objective

Enable Sentinel to coordinate multiple specialized models within a single task. When a user asks to "analyze my project", different specialist models handle architecture review, security analysis, and code review in parallel, then results are fused into a unified response.

## Problem

Before Phase 7, a single model handled the entire response:

```
User: "analyze my project"
  → IntelligenceOrchestrator selects ONE model
  → That model provides a single-angle response
```

A generalist model may lack deep expertise in all areas (security, architecture, code quality).

## Solution

```
User: "analyze my project"
  → IntentEngine → CapabilityEngine → IntelligenceOrchestrator
  → ModelCoordinator
      ├── decompose("analyze my project")
      │     → MultiModelPlan with 3 tasks:
      │        • architecture_review [reasoning]
      │        • security_review     [reasoning]
      │        • code_review         [coding, reasoning]
      ├── assign_models()
      │     → each task gets a specialist from ModelRegistry
      ├── execute_plan(parallel)
      │     → asyncio.gather for independent tasks
      └── results
  → FusionEngine.fuse(results)
      → deduplicated, ordered, conflict-flagged response
```

## New Components

### `sentinel/core/model_coordinator.py`

#### Data Structures

| Class | Description |
|---|---|
| `ModelTask` | Subtask for a specialist model: name, objective, required_capabilities, preferred_model, dependencies |
| `MultiModelPlan` | Collection of tasks + execution strategy (PARALLEL, SEQUENTIAL, MIXED) |
| `ModelTaskResult` | Result of a single subtask: response, success, error, duration_ms |
| `MultiModelResult` | Aggregate result: total/successful/failed, partial_completion, all_failed |
| `ExecutionStrategy` | Enum: PARALLEL, SEQUENTIAL, MIXED |

#### ModelCoordinator

| Method | Description |
|---|---|
| `can_coordinate()` | Returns True for REASONING, CODING, ANALYSIS intents; False for ACTION |
| `decompose()` | Decomposes user message + intent into `MultiModelPlan` using deterministic rules |
| `select_specialist()` | Scores and selects best model from ModelRegistry for a task's required capabilities |
| `assign_models()` | Assigns specialists to all tasks in a plan |
| `execute_task()` | Calls a single model via chat_fn with task-specific prompt |
| `execute_plan()` | Orchestrates execution respecting dependencies and strategy |
| `build_task_prompt()` | Builds specialist prompt from task objective + user message |
| `add_decomposition_rule()` | Extends the rule set |

#### Task Decomposition Rules

Deterministic rules that map message content to task configurations:

| Rule | Trigger Keywords | Tasks |
|---|---|---|
| `project_analysis` | "project", "app", "aplicación" + coding/reasoning cap | architecture_review, security_review, code_review |
| `code_review_deep` | "project", "app" (no coding cap) | code_quality, error_analysis |
| `security_audit` | "security", "seguridad", "vulnerabilidad" | dependency_check, permission_audit, data_safety |
| `research` | "research", "investiga", "analiza" or REASONING intent | fact_checking, deep_analysis |

#### Execution Flow

```
execute_plan(plan, user_message, chat_fn)
  → assign_models() → dict[task_id, ModelMetadata]
  → if PARALLEL and no dependencies:
      → asyncio.gather(all tasks)
  → if SEQUENTIAL or has dependencies:
      → batch processing:
        while remaining:
          batch = [tasks whose deps are all completed]
          asyncio.gather(batch)
  → MultiModelResult(results, total, successful, failed, duration)
```

### `sentinel/core/fusion_engine.py`

#### Data Structures

| Class | Description |
|---|---|
| `FusionFinding` | A discrete finding from a specialist model: source, category, summary, detail, severity |
| `FusionConflict` | A detected discrepancy between two specialist findings |
| `FusionResult` | Consolidated output: summary, findings, conflicts, categories |

#### FusionEngine

| Method | Description |
|---|---|
| `fuse(results)` | Main pipeline: extract findings → classify → deduplicate → detect conflicts → order → build summary |
| `_classify(text)` | Keyword-based category detection (architecture, security, code_quality, performance, testing, docs) |
| `_assess_severity()` | Keyword-based severity (critical, warning, info) |
| `_detect_conflicts()` | Finds contradictory findings across different specialist sources using negation/positive keyword heuristics |
| `_order_findings()` | Orders by severity (critical first), then category |
| `_build_summary()` | Generates human-readable summary of analysis |
| `find_by_category()` | Filters findings by category |

#### Fusion Pipeline

```
fuse([task_result_1, task_result_2, task_result_3])
  → For each successful result:
      → Split response into paragraphs
      → Classify each paragraph (architecture, security, code_quality, etc.)
      → Deduplicate by content hash
      → Assess severity
      → Create FusionFinding
  → For each failed result:
      → Create error FusionFinding
  → Detect conflicts across specialists
  → Order findings (critical → warning → info)
  → Build summary
  → FusionResult
```

## Architecture Compliance

- **IntelligenceOrchestrator** unchanged: still controls strategy + initial model decision
- **ModelRouter** unchanged: still handles provider communication. Only `chat_with_conversation()` was added in Phase 6
- **ConversationManager** referenced: results can be stored for continuity
- **ToolGateway** untouched: no tool execution paths added
- **ModelRegistry** unchanged: used read-only for specialist selection

## Error Handling

| Scenario | Behavior |
|---|---|
| No model for capability | Task result with `success=False`, error message. Partial completion. |
| API call fails | Individual task fails, other tasks continue. `partial_completion=True` |
| All tasks fail | `all_failed=True`, no fabricated response |
| Circular dependency | Detected and logged; remaining tasks skipped |
| No registry configured | Returns None for specialist selection |

## Tests

### `tests/test_model_coordinator.py` — 42 tests

| Test Class | Tests | What it validates |
|---|---|---|
| ModelTask | 2 | Defaults, to_dict |
| MultiModelPlan | 5 | Empty, add_task, dependencies, independent_tasks, to_dict |
| ModelTaskResult | 2 | Defaults, to_dict |
| MultiModelResult | 3 | all_successful, partial_completion, all_failed properties |
| ModelCoordinator | 22 | can_coordinate, decompose (project/security/research), specialist selection, assign_models, task prompts, execute_task success/failure, execute_plan parallel/sequential/partial/all-fail, dependencies, custom rules |
| FusionEngine | 8 | Empty results, single/multiple results, failed task inclusion, classification, severity, conflict detection, deduplication, to_dict |

### Full Suite Results
- **3059 passed**, 1 failed (pre-existing), 1 skipped
- **0 new regressions** from Phase 7
- **257 new tests total** (Phase 1-7): 257/257 pass

## Acceptance Criteria

| Criterion | Status |
|---|---|
| ✅ ModelCoordinator exists | `sentinel/core/model_coordinator.py` |
| ✅ Sentinel can use multiple models in one task | `execute_plan()` with multiple tasks |
| ✅ Subtasks can execute in parallel | `asyncio.gather()` for independent tasks |
| ✅ Models selected by capabilities | `select_specialist()` uses `ModelRegistry.find_candidates()` |
| ✅ FusionEngine exists | `sentinel/core/fusion_engine.py` |
| ✅ Partial failures are controlled | Remaining tasks continue; `partial_completion=True` |
| ✅ ConversationManager can store results | Results available via `MultiModelResult.results` |
| ✅ ToolGateway remains sole execution gate | No new execution paths |
| ✅ All tests pass | 42/42, full suite 0 regressions |
