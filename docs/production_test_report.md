# Production Test Report (FASE 6)

> Auto-generated 2026-08-02 11:25:42 UTC — real components, no stubs/SentinelRuntime.

## Certification gate

| Check | Result |
| --- | --- |
| No failures in gateway/chaos/stress/orchestrator suites | PASS |
| Failed nodes | None |

## Per-level results

| Level | Passed | Failed | Skipped |
| --- | --- | --- | --- |
| 1 - Orchestrator | 14 | 0 | 0 |
| 2 - Gateway security | 8 | 0 | 0 |
| 3 - Real model | 0 | 0 | 1 |
| 4 - Stress | 2 | 0 | 0 |
| 5 - Chaos | 5 | 0 | 0 |
| suite | 32 | 0 | 0 |

## Totals

- Passed: **61**
- Failed: **0**
- Skipped: **1**

## Slowest tests

| Test | Duration |
| --- | --- |
| tests/production/observability/test_architecture_single_implementation.py::test_no_legacy_observability_imports_in_production_code | 41.37s |
| tests/production/orchestrator/test_fastapi_real_stack.py::test_execute_real_tool_via_http | 2.15s |
| tests/production/stress/test_level4_stress.py::test_stress_concurrent_users | 0.64s |
| tests/production/observability/test_dashboard_diagnostics.py::TestDiagnosticsEndpoint::test_diagnostics_reachable | 0.40s |
| tests/production/chaos/test_level5_chaos.py::test_sqlite_locked_retries_and_recovers | 0.39s |
| tests/production/observability/test_dashboard_diagnostics.py::TestDiagnosticsEndpoint::test_engine_check_healthy | 0.31s |
| tests/production/observability/test_dashboard_diagnostics.py::TestDashboardEndpoint::test_endpoint_reachable | 0.29s |
| tests/production/stress/test_level4_stress.py::test_restart_under_load_recovers_state | 0.27s |
| tests/production/observability/test_dashboard_diagnostics.py::TestDashboardEndpoint::test_costs_section_is_real | 0.22s |
| tests/production/observability/test_dashboard_diagnostics.py::TestDashboardEngine::test_dashboard_returns_real_sections | 0.21s |

## Stress (Level 4)

| Users | Tasks/user | OK | Errors | Error rate |
| --- | --- | --- | --- | --- |
| 100 | 10 | 1000 | 0 | 0.00% |

## Recovery & chaos (Level 5)

| Scenario | Result |
| --- | --- |
| model outage -> circuit breaker opens -> fallback to local -> recovery | pass |
| all models down -> controlled RuntimeError (no hang) | pass |
| SQLite locked -> write retried (busy/backoff) -> recovered | pass |
| tool crash -> contained by guard + audited -> system alive | pass |
| network drop -> circuit open -> routed to local model | pass |
| restart under load (execution+performance persisted) | pass |

## Security evidence (Level 2)

| Check | Result |
| --- | --- |
| path traversal blocked (config.write ../) | pass |
| command injection blocked (executor.launch ../..\cmd.exe) | pass |
| invalid parameters rejected without execution | pass |
| rollback restored previous state after failure | pass |
| append-only audit trail with verifiable hash chain | pass |

## Real model (Level 3)

| Model | Latency | Tokens (p/c) | RSS delta | CPU% | Mem% |
| --- | --- | --- | --- | --- | --- |
| _no local model available (skipped)_ | - | - | - | - | - |
