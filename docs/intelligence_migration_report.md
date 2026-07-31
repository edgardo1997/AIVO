# Intelligence Migration Report

## Current State: Two Parallel Systems

### OLD SYSTEM (wired into Orchestrator)
| Class | File | Purpose | Storage | Status |
|-------|------|---------|---------|--------|
| `ModelFeedbackStore` | `sentinel/core/model_feedback.py` | Record feedback per (provider, model, task_type) | SQLite (file) + RAM | REMOVE |
| `PerformanceTracker` | `sentinel/core/performance_tracker.py` | Track duration, detect regressions | RAM only (dict) | REMOVE |
| `CostTracker` | `sentinel/core/cost_tracker.py` | Estimate/record costs, budgets | SQLite (file) + RAM | KEEP (migrate interface) |

### NEW SYSTEM (NOT wired into Orchestrator)
| Class | File | Purpose | Storage | Status |
|-------|------|---------|---------|--------|
| `PerformanceIntelligence` | `sentinel/core/performance_intelligence.py` | Execution metrics (latency, success, tokens, cost) | RAM (list) | MIGRATE |
| `FeedbackEngine` | `sentinel/core/feedback_engine.py` | User feedback, positive/negative scoring | RAM (list) | MIGRATE |
| `ModelRanking` | `sentinel/core/model_ranking.py` | Weighted scoring (perf + feedback) | RAM (dict) | MIGRATE |
| `TimePredictor` | `sentinel/core/time_predictor.py` | Estimate execution time + confidence | RAM (via PerformanceIntelligence) | MIGRATE |
| `IntelligenceOrchestrator` | `sentinel/core/intelligence_orchestrator.py` | Model selection orchestration | RAM | KEEP (rename to Coordinator) |
| `ModelDiscovery` | `sentinel/core/model_discovery.py` | Discover models from providers | RAM | KEEP |

### DUPLICATE SYSTEM (sentinel/intelligence/)
| Class | File | Relationship | Status |
|-------|------|-------------|--------|
| `FeedbackCycle` | `sentinel/intelligence/feedback.py` | Parallel to `FeedbackEngine` | REMOVE |
| `RankingEngine` | `sentinel/intelligence/ranking.py` | Parallel to `ModelRanking` | REMOVE |
| `TaskTimePredictor` | `sentinel/intelligence/time_predictor.py` | Parallel to `TimePredictor` | REMOVE |
| `ModelDiscovery` | `sentinel/intelligence/model_discovery.py` | Simpler version of core's `ModelDiscovery` | REMOVE |
| `IntelligenceEngine` | `sentinel/intelligence/engine.py` | Coordinator (not wired) | REMOVE |
| `IntelligenceStorage` | `sentinel/intelligence/storage.py` | Parallel to `sentinel/storage/` | REMOVE |

### STORAGE LAYER (ready to use)
| Class | File | Purpose | Status |
|-------|------|---------|--------|
| `MetricRepository` | `sentinel/storage/repositories/metric_repository.py` | Persist ExecutionMetrics | KEEP |
| `FeedbackRepository` | `sentinel/storage/repositories/feedback_repository.py` | Persist UserFeedback | KEEP |
| `ModelRepository` | `sentinel/storage/repositories/model_repository.py` | Persist model registry | KEEP |
| `StorageEngine` | `sentinel/storage/database.py` | SQLite/async connection | KEEP |
| `StoredModel` | `sentinel/storage/models.py` | Model registry dataclass | KEEP |
| `FeedbackRecord` | `sentinel/storage/models.py` | Feedback dataclass | KEEP |
| `MetricRecord` | `sentinel/storage/models.py` | Metrics dataclass | KEEP |

## Migration Plan

### What We Keep
- `sentinel/core/performance_intelligence.py` → wire via Coordinator
- `sentinel/core/feedback_engine.py` → wire via Coordinator
- `sentinel/core/model_ranking.py` → wire via Coordinator
- `sentinel/core/time_predictor.py` → wire via Coordinator
- `sentinel/core/model_discovery.py` → wire via Coordinator
- `sentinel/core/intelligence_orchestrator.py` → source of model selection logic (absorb into Coordinator)
- `sentinel/storage/` → persistence backend for all intelligence data
- `sentinel/core/cost_tracker.py` → too widely used to move; wrap via Coordinator

### What We Eliminate
- `sentinel/core/model_feedback.py` (ModelFeedbackStore) → replaced by FeedbackEngine
- `sentinel/core/performance_tracker.py` (PerformanceTracker) → replaced by PerformanceIntelligence
- `sentinel/intelligence/feedback.py` (FeedbackCycle) → duplicate
- `sentinel/intelligence/ranking.py` (RankingEngine) → duplicate
- `sentinel/intelligence/time_predictor.py` (TaskTimePredictor) → duplicate
- `sentinel/intelligence/model_discovery.py` → duplicate of core version
- `sentinel/intelligence/engine.py` (IntelligenceEngine) → duplicate coordinator
- `sentinel/intelligence/storage.py` (IntelligenceStorage) → duplicate of sentinel/storage/

### What We Create
- `sentinel/core/intelligence_coordinator.py` → single interface for Orchestrator

### What We Rename
- `ModelFeedbackStore.record()` → `FeedbackEngine.record_feedback()`
- `PerformanceTracker.record()` → `PerformanceIntelligence.record_metric()`
- `CostTracker` → no rename, but accessed via `Coordinator.calculate_cost()`

## Consumers to Update

### Modules directly referencing old OLD classes
1. `sentinel/core/orchestrator.py` — imports `ModelFeedbackStore`, `PerformanceTracker`, `CostTracker`
2. `sentinel/core/model_router.py` — uses `set_feedback_store()`, `set_cost_tracker()`
3. `sentinel/core/alerting.py` — uses `CostTracker`, `PerformanceTracker`
4. `sentinel/core/resource_intelligence.py` — uses `CostTracker`, `PerformanceTracker`
5. `sentinel/routing/provider_selector.py` — uses `CostTracker`
6. `sentinel/routing/legacy.py` — uses `CostTracker`
7. `sentinel/core/file_pipeline.py` — uses `CostTracker`
8. `sidecar/modules/__init__.py` — creates `CostTracker`, `PerformanceTracker`
9. `sidecar/modules/sentinel_bridge.py` — API endpoints for baselines, alerts, cost

### API endpoints to update
- `sentinel_bridge.py` `/performance/baselines` → read from `PerformanceIntelligence`
- `sentinel_bridge.py` `/performance/alerts` → remove (regression detection is legacy)
- `sentinel_bridge.py` `/cost/summary`, `/cost/total`, `/cost/budgets`, `/cost/alerts` → keep via Coordinator

## Dependency Graph (Target)

```
Orchestrator
  └── IntelligenceCoordinator
        ├── PerformanceIntelligence → MetricRepository (SQLite)
        ├── FeedbackEngine → FeedbackRepository (SQLite)
        ├── ModelRanking
        ├── TimePredictor
        ├── ModelDiscovery → ModelRepository (SQLite)
        └── CostTracker
```

## Phases

1. **3.1** — This audit (done)
2. **3.2** — Create `IntelligenceCoordinator`
3. **3.3** — Migrate modern components into Coordinator
4. **3.4** — Migrate Orchestrator to use Coordinator
5. **3.5** — Wire persistence via sentinel/storage/
6. **3.6** — Delete old code
7. **3.7** — Tests
