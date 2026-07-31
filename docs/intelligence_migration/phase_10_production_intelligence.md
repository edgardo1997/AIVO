# Phase 10 — Production Intelligence

## Objective

Convert Sentinel into a system capable of learning from operational behavior and progressively improving its routing, model selection, and execution decisions without modifying model internals.

## Architecture

```
User
  ↓
Sentinel Intelligence Pipeline
  ↓
Decision (IntelligenceOrchestrator)
  ↓
Execution
  ↓
Metrics Collection (PerformanceIntelligence)
  ↓
Performance Learning (ModelRanking)
  ↓
Feedback Integration (FeedbackEngine)
  ↓
Time Prediction (TimePredictor)
  ↓
Future Decisions Improved
```

### Before Phase 10
- Static model selection based on declared capabilities
- No learning from past executions
- No user feedback integration
- No time estimation

### After Phase 10
- Dynamic scoring based on real success rates and latency
- Observed vs declared capability tracking
- User feedback adjusts model scores in real time
- Time prediction using historical data
- Audit log for all decisions
- Event-driven integration via EventBus

## Metrics

### ExecutionMetrics
| Field | Type | Description |
|---|---|---|
| model_id | str | Model identifier |
| task_type | str | Type of task performed |
| intent | str | Original user intent |
| latency | float | Response time in seconds |
| tokens_used | int | Total tokens consumed |
| cost | float | Cost in USD |
| success | bool | Whether execution succeeded |
| error | Optional[str] | Error message on failure |
| hardware_state | Optional[Dict] | Hardware context at execution time |
| prompt_tokens | int | Prompt tokens |
| completion_tokens | int | Completion tokens |

### ModelPerformanceSummary
| Field | Type | Description |
|---|---|---|
| total_executions | int | Total recorded runs |
| success_rate | float | Ratio of successful executions |
| avg_latency | float | Average response time |
| reliability_score | float | success_rate * 100 |
| recent_errors | List[str] | Last 10 error messages |

## Feedback

### FeedbackScore
- `POSITIVE` — user approved the response
- `NEGATIVE` — user rejected or corrected
- `NEUTRAL` — no strong opinion

### FeedbackEngine
- Records feedback per model_id + task_type
- Summarizes positive ratio and net score
- Emits `USER_FEEDBACK_RECEIVED` event
- Feedback feeds into ModelRanking scores

## Ranking

### ModelRanking
Computes composite score from:
| Factor | Weight | Source |
|---|---|---|
| Reliability | 35% | PerformanceIntelligence success rate |
| Latency | 20% | Average response time |
| Cost | 15% | Cost per execution |
| User Feedback | 20% | FeedbackEngine positive ratio |
| Experience | 10% | Total execution count |

### Observed vs Declared Capabilities
- **Declared**: What the model metadata says (supports_coding=True)
- **Observed**: What real usage shows (supports_coding_score=92%)

Discrepancies are flagged when a declared capability has <50% observed success rate.

## Prediction

### TimePredictor
- Estimates task duration from historical execution data
- Considers: model_id, task_type, complexity hint, estimated tokens
- Uses statistical confidence intervals (95% CI)
- Complexity factors: simple (0.5x), moderate (1.0x), complex (2.0x), very complex (4.0x)

## Optimization

### IntelligenceOrchestrator Integration
- `_score_model` now adds performance bonuses and penalties
- `_select_model` uses ranking data for tie-breaking
- `_build_reasoning` includes success rates, latency, cost, time estimates
- Decision includes explainable reasoning with all factors

### Example Decision Reasoning
```
Intent: CODING | Model: qwen-coder (provider=ollama) | Capabilities: ['coding', 'reasoning'] | Strategy: coding | Tool calling: enabled | Performance: 85/100 (high) | Success rate: 100% | Avg latency: 2.3s | Cost: free | Estimated time: 2.5 minutes (confidence: 92%)
```

## Safety

Phase 10 follows strict safety rules:
- **No model weight modification** — learning is metric/history/feedback based only
- **No automatic model deletion** — underperforming models are marked, not removed
- **No authorization rule changes** — security layers remain untouched
- **Recommend only** — ranking suggests, orchestrator decides
- **Full audit trail** — all ranking updates and decisions logged

## Events

New EventBus events added:
| Event | When |
|---|---|
| `model.execution.started` | Model invocation begins |
| `model.execution.completed` | Model returns successfully |
| `model.execution.failed` | Model execution errors |
| `user.feedback.received` | User provides feedback |
| `model.ranking.updated` | Ranking recomputed |

## Tests

### Test Structure
68 tests across 10 test classes:

| Test | Description |
|---|---|
| TestPerformanceIntelligence | 10 tests — metric recording, summaries, filtering |
| TestPerformanceIntelligenceTest1 | Success metric stored correctly |
| TestPerformanceIntelligenceTest2 | Failure recorded, model loses ranking |
| TestFeedbackEngine | 12 tests — positive/negative/neutral, summaries |
| TestFeedbackEngineTest3 | Positive feedback increases score |
| TestFeedbackEngineTest4 | Negative feedback decreases score |
| TestModelRanking | 10 tests — scoring, ranking, audit, observed capabilities |
| TestModelRankingTest5 | Faster model outranks slower |
| TestTimePredictor | 11 tests — prediction, complexity, display |
| TestTimePredictorTest6 | Estimate generated with confidence |
| TestIntelligenceOrchestratorIntegration | 5 tests — setters, audit log, orchestration |
| TestIntelligenceOrchestratorTest7 | Explainable decision with all factors |
| TestEventTypes | 2 tests — new events registered |
| TestObservedCapabilities | 1 test — defaults |
| TestExecutionMetrics | 1 test — timestamp |
| Event subscription | 2 tests — event names, subscription |

## Acceptance Criteria

- [x] Sentinel records real performance metrics
- [x] Sentinel learns from historical results
- [x] User feedback system exists and works
- [x] Dynamic model ranking in place
- [x] Time prediction generates estimates
- [x] Model selection improves with performance data
- [x] All decisions remain explainable
- [x] Audit log maintained
- [x] No internal model modifications
- [x] Security layers unchanged
- [x] All tests pass (131 existing + 68 new)

## Files Created

| File | Purpose |
|---|---|
| `sentinel/core/performance_intelligence.py` | Metrics collection and analysis |
| `sentinel/core/feedback_engine.py` | User feedback recording |
| `sentinel/core/model_ranking.py` | Dynamic model scoring and ranking |
| `sentinel/core/time_predictor.py` | Task time estimation |
| `sidecar/tests/test_production_intelligence.py` | 68 tests covering all components |
| `docs/intelligence_migration/phase_10_production_intelligence.md` | This document |

## Files Modified

| File | Change |
|---|---|
| `sentinel/core/event_types.py` | Added 5 new event types |
| `sentinel/core/intelligence_orchestrator.py` | Performance-aware routing, setters, audit log, enhanced reasoning |
| `sentinel/core/__init__.py` | Exported all new classes |
