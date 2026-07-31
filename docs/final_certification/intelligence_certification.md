# Intelligence Certification

## ModelDiscovery

### Evidence: Unit tests pass (36/36)
- `OllamaDiscovery.discover_models()` — tested with mock HTTP responses
- `LMStudioDiscovery.discover_models()` — tested
- `CloudProviderDiscovery.discover_models()` — tested for OpenAI, Anthropic, Google

### But: NOT WIRED INTO PRODUCTION
- `init_sentinel_orchestrator()` in `sidecar/modules/__init__.py` does NOT create `ModelDiscovery`
- `ModelRouter` does NOT use `ModelDiscovery` — models are hardcoded from `BUILTIN_PROVIDERS`
- `SentinelRuntime` does NOT accept `ModelDiscovery`
- **Verdict:** Model discovery runs only in tests. Real models cannot be auto-detected in production.

## ModelRanking

### Evidence: Unit tests pass (13/13)
- `compute_scores()` correctly weights latency (0.20), cost (0.15), reliability (0.35), feedback (0.20), execution count (0.10)
- `update_score()` delegates to `PerformanceIntelligence.record_metric()`
- `get_declared_vs_observed()` correctly flags discrepancies

### But: NOT WIRED INTO PRODUCTION ORCHESTRATOR
- Only connected in `SentinelRuntime.set_router()` — which never runs in production
- `Orchestrator` has no `model_ranking` parameter
- **Verdict:** ModelRanking exists only for tests. Production cannot rank models.

## FeedbackEngine

### Evidence: Unit tests pass
- `record_feedback()` stores feedback with model_id, task_type, score
- `get_summary()` returns aggregated feedback

### But: NOT WIRED INTO PRODUCTION
- Orchestrator uses older `ModelFeedbackStore` (different class)
- `initialize_intelligence()` added but only works in SentinelRuntime
- **Verdict:** Feedback has no path to affect production behavior.

## TimePredictor

### Evidence: Unit tests pass
- `predict()` returns estimated_seconds and confidence
- `predict_by_complexity()` adjusts by complexity level

### But: NEVER USED IN PRODUCTION PIPELINE
- Now wired into `SentinelRuntime._process_impl()` but that's dead code
- Orchestrator never calls `TimePredictor`
- **Verdict:** TimePredictor produces estimates that nobody reads.

## Actual Production Intelligence

The production Orchestrator has:
- `ModelFeedbackStore` (old API, different from FeedbackEngine)
- `PerformanceTracker` (different from PerformanceIntelligence)
- `CostTracker` (separate from model ranking)

**These are NOT connected to the `sentinel/core/` intelligence components.**

## Verdict: **FAIL** (4/10)

All intelligence components pass unit tests but are NOT connected to the production pipeline. The production Orchestrator uses different, older classes. No feedback loop exists in production.
