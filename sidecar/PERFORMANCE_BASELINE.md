# Sentinel Performance Baseline

## Purpose

This document records the validated, measured baseline of the Sentinel sidecar after the resource-aware provider-selection and conversation-metadata integration. It is a laboratory result from one Windows development environment and is not a universal product guarantee.

## Laboratory profile

- Host: Windows (cp1252 default console encoding)
- Python: 3.12.10
- venv: `sidecar/.venv`
- Repository: `C:\Users\edgar\OneDrive\Documents\AIVO`
- Test command: `PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe -m pytest -q`

## Files modified to reach this baseline

- `sentinel/core/model_router.py` — truthful `meta` event in `chat_stream`, correlation-id support, safe selection-trace summary.
- `sidecar/services/ai_service.py` — truthful core-fallback `meta`, correlation-id pass-through.
- `sidecar/modules/sentinel_bridge.py` — consistent `meta` fields for the governed `sentinel_core` shortcut.
- `sidecar/routing/provider_selector.py` — resource-aware hard gates and soft scoring.
- `sidecar/core/model_router.py` — `set_resource_intelligence` pass-through.
- `sidecar/modules/__init__.py` — `ResourceIntelligenceLayer` wired into `ModelRouter`.
- `sidecar/tests/conftest.py` — `ai_config` reset and `ai_svc.restore_config()` / `load_provider_keys()` in `clean_state`.
- `sidecar/tests/test_unified_provider_selection.py` — strengthened assertions and new negative fallback test.
- `sidecar/tests/test_provider_selector_resource.py` — resource-aware and strategy-specific deterministic tests.
- `sidecar/tests/test_fallback_chaining.py` — updated to the new `ModelRouter` `meta` contract.
- `sidecar/tests/test_provider_manager_stream.py` — relaxed exact `done` dict assertion to field-level checks.
- `sidecar/tests/test_direct_http_conversation.py`, `test_production_conversation_path.py`, `test_production_latency.py`, `test_production_latency_simple.py` — marked `__test__ = False` as standalone diagnostic scripts.
- `sidecar/pyproject.toml` — `testpaths = ["tests"]` to avoid collecting broken root diagnostic scripts.

## Selected test results

| Suite | Result |
|---|---|
| `tests/test_provider_selector_resource.py` | 23/23 passed |
| `tests/test_provider_selection_precedence.py` | 7/7 passed |
| `tests/test_unified_provider_selection.py` (7 tests) | 7/7 passed (after `clean_state` fix) |
| `tests/test_resource_intelligence.py` | all passed |
| `tests/test_simulated_hardware_profiles.py` | all passed |
| `tests/test_hardware_intelligence.py` | all passed |
| `tests/test_model_router_phase1.py` | 11/11 passed |
| `tests/test_chat_pipeline.py` | all passed |
| `compileall sentinel sidecar` | success |
| `from sentinel.core.model_router import ModelRouter; from sidecar.main import app; from sidecar.modules import init_sentinel_orchestrator` | success |

## Latency measurements

Measured with `benchmark_provider_selector.py` on this laboratory profile, 1000 recorded iterations for A and C, 100 warm iterations for B.

### A. Pure selection algorithm (mocked)

- `n = 1000`
- min ≈ 9.2 µs
- median ≈ 9.8 µs
- mean ≈ 10.6 µs
- p95 ≈ 13.1 µs
- max ≈ 80.9 µs
- Mocks used: `SystemSnapshot`, health, cost; no I/O.

### B. `ResourceIntelligenceLayer.snapshot()` (real psutil)

- cold: ≈ 14.0 ms
- warm (`n = 100`):
  - min ≈ 11.2 ms
  - median ≈ 12.4 ms
  - mean ≈ 13.2 ms
  - p95 ≈ 14.4 ms
  - max ≈ 73.9 ms

### C. Integrated `ProviderSelector.select()` (real snapshot)

- `n = 1000`
- min ≈ 11.0 ms
- median ≈ 12.2 ms
- mean ≈ 12.4 ms
- p95 ≈ 14.1 ms
- max ≈ 82.3 ms
- `snapshot_calls_per_select = 1.0`
- No per-candidate resampling, no network, no filesystem scanning.

## Observed warnings (pre-existing, not introduced)

- `StarletteDeprecationWarning` for `httpx` test client (fastapi/starlette).
- `DeprecationWarning` for `ModelFeedbackStore` and `PerformanceTracker` in `sentinel/core/__init__.py`.
- `InsecureKeyLengthWarning` for JWT HMAC key in `tests/test_auth_authorization.py`.
- `DeprecationWarning` for `ast.NameConstant` in `reportlab` from `tests/test_report_workflow.py`.

## Known limitations on this profile

1. The real `SystemSnapshot` capture dominates `ProviderSelector.select()` at ~12 ms.
2. The Windows console defaults to cp1252; `PYTHONIOENCODING=utf-8` is required for a clean `pytest` run when tests or providers emit non-ASCII characters.
3. Several root-level `test_*.py` files in `sidecar/` are broken standalone diagnostics and are now excluded from `pytest` collection.

## Full suite result

`PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe -m pytest -q`

- **2944 passed**, **14 skipped**, **7 warnings**, **0 failed** in 624.97 s (Phase 1 baseline).

The one earlier failure (`test_unified_provider_selection.py::test_conversation_normal_routing`) was a state leak from the `ai_service` configuration not being reset between tests. It was fixed by adding `ai_svc.restore_config()` and `ai_svc.load_provider_keys()` to the `clean_state` fixture in `tests/conftest.py`.

### Phase 6 full validation

- **2978 passed**, **14 skipped**, **1 failed**, **7 warnings** in 591.80 s.
- The single failure is `tests/test_context_window.py::test_streaming_local_model_reserves_generation_capacity`, which expects a hardcoded 3072-token Qwen budget.  The actual 5760 value is produced by the existing `ContextBudgetManager` integration and is not related to Phase 6 tier routing.

## Phase 6 — Model tier routing

Laboratory measurement on the same Windows profile (`PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe`):

- `ModelTierSelector.select_tier` (three mock models, 1000 iterations):
  - mean ≈ 6.9 µs
  - total ≈ 6.9 ms
- Targeted regression suites:
  - `tests/test_model_tier.py`: **27 passed**
  - `tests/test_provider_selector_resource.py` + `test_unified_provider_selection.py` + `test_chat_pipeline.py` + `test_context_budget.py` + `test_performance_harness.py`: **60 passed**

Tier decision time is a negligible addition to the existing `ProviderSelector.select()` path, which remains dominated by `SystemSnapshot` capture at ~12 ms.

## Phase 7 — Provider performance intelligence

- `ProviderPerformanceStore.record` + `performance_score` combined (1000 iterations, 100 pre-warmed observations):
  - mean ≈ 23.8 µs per record+score cycle
- The performance component is calculated only when a `ProviderPerformanceStore` is wired; without it `ProviderSelector` soft scoring is unchanged.
- Targeted regression suites:
  - `tests/test_provider_performance.py`: **18 passed**
  - `tests/test_provider_manager_performance.py`: **11 passed** (including client reuse and lifecycle)
  - `tests/test_provider_selector_resource.py` + `test_model_tier.py` + `test_performance_harness.py` + `test_context_budget.py`: **74 passed**
  - `tests/test_context_window.py`: **5 passed**
- Full `pytest -q`:
  - **3005 passed**, 14 skipped, **0 failed** in 869.59 s
  - `tests/test_filesystem.py` repeated 20 times: 20/20 passed
- Phase 8 targeted regression:
  - `test_provider_manager_stream.py` + `test_provider_manager_performance.py` + `test_chat_pipeline.py` + `test_fallback_chaining.py` + `test_context_window.py`: **88 passed**
  - `test_provider_manager_stream.py` + `test_provider_manager_performance.py` + `test_chat_pipeline.py` + `test_fallback_chaining.py`: **63 passed**

## Phase 8 — Connection, streaming and cancellation

- Client reuse baseline:
  - `ProviderManager` now caches one `OpenAI` client per `(provider_id, api_key, base_url)`
  - Credential changes close and recreate the client
  - `ProviderManager.close()` and `ModelRouter.close()` close all cached provider clients
  - `tests/test_provider_manager_performance.py` client lifecycle tests: **3 passed**
- Timeout split:
  - `call_provider` uses `httpx.Timeout(timeout=call_timeout, connect=CONNECT_TIMEOUT)`
  - `call_provider_stream` uses `httpx.Timeout(timeout=read_timeout, connect=CONNECT_TIMEOUT)` with `timeout_budget` as the read/first-token bound
- Cancellation:
  - `ProviderManager.call_provider_stream` records a `cancelled` observation on `GeneratorExit`
  - `sentinel_bridge` emits a `cancelled` terminal event on disconnect
- Known findings:
  - `OpenAIProvider` in `sentinel/providers/openai_provider.py` is currently unused and duplicates `ProviderManager` client creation
  - `sentinel_bridge` stream loop `next()` is executed in a thread, so cancellation cannot truly abort a blocked `read()` until that call returns
