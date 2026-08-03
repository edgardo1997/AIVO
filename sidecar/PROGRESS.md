# Sentinel Performance and Architecture Plan — Progress

## Current phase

Phase 6 — Model tier routing.

## Completed work

### Phase 1 — Clean and lock the current baseline

- Marked standalone diagnostic scripts with `__test__ = False`:
  - `tests/test_direct_http_conversation.py`
  - `tests/test_production_conversation_path.py`
  - `tests/test_production_latency.py`
  - `tests/test_production_latency_simple.py`
- Restricted `pytest` to `tests/` in `pyproject.toml` (`testpaths = ["tests"]`).
- Fixed `tests/test_fallback_chaining.py` and `tests/test_provider_manager_stream.py` for the new `ModelRouter` `meta` contract.
- Fixed `tests/conftest.py` to reset `ai_svc` configuration between tests, eliminating the `test_conversation_normal_routing` state leak.
- Full `PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe -m pytest -q`:
  - **2944 passed**, **14 skipped**, **7 warnings**, **0 failed** in 624.97 s.
- Produced `PERFORMANCE_BASELINE.md` with measured latency numbers.

### Phase 2 — Real authenticated production-path test

**STATUS: PARTIAL — BLOCKED BY UNAVAILABLE AUTHENTICATED TAURI/WEBVIEW RUNTIME**

Completed backend work:

- Added `correlation_id` parameter to `AIService.stream_chat()`; falls back to a fresh UUID.
- `sentinel_bridge.py` `/chat/stream` now reads `X-Correlation-Id` (case-insensitive) and passes it through.
- `pipeline` event now includes `correlation_id`.
- Added `test_correlation_id_propagates_through_stream` to `tests/test_unified_provider_selection.py`.

Deferred until the compiled authenticated Sentinel UI is available:

- UI send timestamp
- real Tauri/WebView transport timing
- frontend stream-receive timing
- frontend render timing
- final user-input-to-pixel duration

### Phase 3 — Performance regression harness

- Created `sidecar/benchmarks/run_performance_harness.py` with:
  - 20 scenario definitions
  - 16 deterministic hardware/resource profiles
  - 5 benchmark modes (deterministic, simulated-latency, local, real, authenticated-UI placeholder)
  - `ModelRouter`/`ProviderSelector` integration with mocked providers
  - JSONL and Markdown output
  - product invariants and pass/fail status per record
  - relative statistics (min, median, mean, p95, max)
- Created `sidecar/tests/test_performance_harness.py` (pytest, `performance` marker) that validates the deterministic CI mode.
- Validated `python benchmarks/run_performance_harness.py --mode deterministic --ci` produces 5 passing records and a summary.
- `pytest -m performance tests/test_performance_harness.py` passes.

### Phase 4 — Fast conversational path

- Removed a redundant inner `stage_3_start` assignment in `sentinel_chat_stream` that was overwriting the outer Stage 3 timer.
- Added `test_fast_conversation_path_is_quick_and_conversation_only` to `tests/test_chat_pipeline.py`:
  - verifies ordinary conversation emits a `delta`;
  - verifies `pipeline` event has `route: conversation`;
  - verifies no `error` events;
  - does not use an absolute latency threshold (profile-specific and evidence-based).
- `tests/test_chat_pipeline.py` passes (23/23).

### Phase 5 — Context budget manager

- Created `sentinel/core/context_budget.py` with:
  - `RequestPurpose` enum (`conversation`, `technical`, `reasoning`, `governed_action`);
  - `ContextBudget` dataclass with explicit reservations (system, history, memory, tools, overhead);
  - `ContextBudgetManager` as the single authoritative owner for context budgets;
  - `budget_for`, `truncate`, and `manage` methods;
  - model-aware budget ratios and token truncation preserving system prompt + most recent messages.
- Created `sidecar/tests/test_context_budget.py` (5/5 passing):
  - conversation budget fits small history;
  - governed-action receives larger ratio than conversation;
  - local model has smaller absolute window;
  - truncation keeps system and recent messages;
  - `manage()` reports `budget`, `messages`, `dropped`, `estimated_tokens`.
- Updated `sidecar/services/ai_service.py` to use `ContextBudgetManager` for `local_prompt_budget` instead of a hardcoded 3072-token Qwen check.
- `tests/test_context_budget.py`, `tests/test_chat_pipeline.py`, and `tests/test_unified_provider_selection.py` pass.

### Warning classification from full pytest run

| Warning | Classification |
|---|---|
| `StarletteDeprecationWarning` for `httpx` in `fastapi/testclient.py` | test-environment artifact; tied to dev-only `TestClient` |
| `DeprecationWarning` for `ModelFeedbackStore` in `sentinel/core/__init__.py` | dependency/lifecycle warning; already documented migration to `IntelligenceCoordinator` |
| `DeprecationWarning` for `PerformanceTracker` in `sentinel/core/__init__.py` | dependency/lifecycle warning; already documented migration to `IntelligenceCoordinator` |
| `InsecureKeyLengthWarning` in `tests/test_auth_authorization.py` | test-environment artifact; test-only JWT secret |
| `DeprecationWarning` for `ast.NameConstant` from `reportlab` | dependency deprecation in third-party library; unrelated to Sentinel logic |

None are resource leaks, incorrect async behavior, or imminent dependency breakages, so no fixes were applied.

## Files added or modified in this session

- `sentinel/core/context_budget.py`
- `sentinel/core/model_router.py`
- `sidecar/services/ai_service.py`
- `sidecar/modules/sentinel_bridge.py`
- `sidecar/tests/conftest.py`
- `sidecar/tests/test_unified_provider_selection.py`
- `sidecar/tests/test_fallback_chaining.py`
- `sidecar/tests/test_provider_manager_stream.py`
- `sidecar/tests/test_direct_http_conversation.py`
- `sidecar/tests/test_production_conversation_path.py`
- `sidecar/tests/test_production_latency.py`
- `sidecar/tests/test_production_latency_simple.py`
- `sidecar/tests/test_performance_harness.py`
- `sidecar/tests/test_chat_pipeline.py`
- `sidecar/tests/test_context_budget.py`
- `sidecar/benchmarks/run_performance_harness.py`
- `sidecar/benchmarks/results/*.jsonl`
- `sidecar/benchmarks/results/*.md`
- `sidecar/pyproject.toml`
- `sidecar/PERFORMANCE_BASELINE.md`
- `sidecar/PROGRESS.md`

### Phase 6 — Model tier routing

- Created `sentinel/core/model_tier.py` with:
  - `ModelTier` (T0–T4), `ExecutionMode`, `RiskLevel`, `LatencyClass`, `CostClass`
  - `RequestProfile` and `ModelTierDecision` dataclasses with a documented owner/producer/consumer contract
  - `RequestClassifier` keyword/purpose/risk heuristics
  - `ModelTierSelector` that derives model tiers from existing `ModelMetadata` capability flags (reasoning, coding, tool_calling, context_window, cost, local) without hardcoding provider names
  - Deterministic T0 path that returns `execution_mode == "deterministic"` and does not invoke an LLM
  - Escalation and downgrade recording when constraints (budget, privacy, user preference) force a lower tier than the request requires
- Integrated tier gating into `sentinel/routing/provider_selector.py`:
  - `ProviderSelector` accepts an optional `ModelTierSelector`
  - When `context["tier_decision"]` is supplied, the selector filters providers below the minimum tier
  - Explicit selections are respected when they satisfy the minimum; otherwise they are blocked with `tier_below_minimum`
  - A deterministic `RouterDecision` is returned for T0 requests
  - Tier metadata is included in `selection_trace` without exposing sensitive internal details
- Added `sidecar/tests/test_model_tier.py` (27/27 passing):
  - Greeting → Tier 1
  - Rewriting → Tier 1
  - Technical debugging → Tier 2
  - Architecture review → Tier 3
  - Known application launch → deterministic T0
  - Destructive/governed actions do not bypass governance
  - High-risk ambiguity escalates
  - Tier 4 is not selected for ordinary chat
  - Long context excludes small-window models
  - Explicit user selection respected / undersized rejected
  - Privacy-forbids-cloud selects local
  - Degraded capability reported when no candidate meets the minimum
  - Provider metadata matches actual execution
  - Model tiers do not use hardware class letters
- Targeted regression validation:
  - `tests/test_model_tier.py`: 27 passed
  - `tests/test_provider_selector_resource.py` + `test_unified_provider_selection.py` + `test_chat_pipeline.py` + `test_context_budget.py` + `test_performance_harness.py`: 60 passed

## Next step

Phase 7 — Continue from the logical checkpoint created by Phase 6.  Before promoting Phase 6 to fully complete, run the full pytest suite and, if practical, add opt-in real-provider tier tests and harness-based tier-decision latency measurements.
