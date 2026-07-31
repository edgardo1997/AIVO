# Observability Decommission — Phase A Dependency Report

Date: 2026-07-31
Scope: eliminate parallel observability implementations; keep the single production
`ObservabilityEngine` (`sentinel/observability/engine.py`).

## Legacy stacks being decommissioned

| Stack | Path | Status today |
|---|---|---|
| ObservabilityService | `sentinel/core/observability.py` | deprecated, replaced by engine |
| ObservabilityCenter | `sentinel/core/observability_center.py` | not wired anywhere |
| OperationalTelemetryHub | `sentinel/operational_telemetry_hub/` | flag-disabled (`OPERATIONAL_TELEMETRY_HUB_ENABLED=False`) |
| V2 Operational Observability | `sentinel/v2_operational_observability/` | flag-disabled (`V2_OPERATIONAL_OBSERVABILITY_ENABLED=False`) |

## Importers by stack

### 1. `sentinel.core.observability` / `sentinel.core.observability_center`

Production (live runtime): **NONE** (wiring migrated to `ObservabilityEngine`).

Test-only:
- `sidecar/tests/test_observability_integral.py` — `ObservabilityService`
- `sidecar/tests/test_observability_v2.py` — `ObservabilityService`, `ObservabilityCenter`

### 2. `sentinel.v2_operational_observability`

Production: **NONE**.

Test-only (19 files — static/audit/boundary tests): `sidecar/tests/test_v2_*.py`,
`test_contract_consumer_migration.py`, `test_global_contract_consolidation.py`.

### 3. `sentinel.operational_telemetry_hub`

Production importers (all flag-disabled v2 parallel modules, **unreachable from the
live runtime** — verified zero imports from `sentinel/core`, `sentinel/observability`,
`sidecar` non-test code):

- `sentinel/authorization_manager/{audit,authorization}.py`
- `sentinel/consent_manager/{audit,consent}.py`
- `sentinel/execution_boundary/{audit,boundary}.py`
- `sentinel/execution_planner/{audit,planner}.py`
- `sentinel/executor_sandbox/{audit,executor}.py`
- `sentinel/final_control_plane_readiness/passive_pipeline.py`
- `sentinel/limited_execution_v2/executor.py`
- `sentinel/policy_engine/engine.py`
- `sentinel/recommendation_engine/engine.py`
- `sentinel/runtime_isolation/{audit,isolation}.py`
- `sentinel/sandbox_engine/{audit,simulation}.py`
- `sentinel/shadow_decision_orchestrator/orchestrator.py`
- `sentinel/shadow_runtime_real/observer.py`
- `sentinel/simulation_engine/simulator.py`
- `sentinel/tool_gateway/{audit,gateway}.py`
- `sentinel/v2_unified_pipeline/pipeline.py`

Test-only: `sidecar/tests/test_*_v2.py` (operational telemetry, authorization_manager_v2,
consent_manager_v2, execution_boundary_v2, execution_planner_v2, executor_sandbox_v2,
limited_execution_v2, runtime_isolation_v2, sandbox_engine_v2, tool_gateway_v2, etc.).

## Classification

- **Live production**: zero remaining imports of any legacy observability stack.
- **Unreachable parallel v2 modules**: the `operational_telemetry_hub` importers above
  form a self-contained, flag-disabled v2 control-plane cluster (shadow runtime,
  sandbox, isolation, v2 unified pipeline) with no path from the production entry point.
- **Test-only**: all remaining importers are tests exercising the deprecated stacks.

## Decision

- Delete `sentinel/core/observability.py` + `sentinel/core/observability_center.py`.
- Delete `sentinel/operational_telemetry_hub/` and `sentinel/v2_operational_observability/`.
- Remove/migrate the test-only importers (obsolete tests deleted or rewritten to
  validate the single `ObservabilityEngine` implementation).
- The v2 parallel control-plane modules that import `operational_telemetry_hub` are
  unreachable dead code; they are removed together with the hub after confirming the
  dependency graph has no live path to them.
