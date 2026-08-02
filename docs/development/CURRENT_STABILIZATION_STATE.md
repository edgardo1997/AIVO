# CURRENT STABILIZATION STATE

Fecha: 2026-08-02
Commit base: `1ee215b` (F7 observabilidad producción)
Objetivo de sesión: migrar approvals legacy al flujo durable (P0-1) y cerrar P0-2 (frontera única).

## Objetivo activo
Continuar Objetivo 4 (baseline amplio) y 6 (siguiente defecto de mayor impacto).
2026-08-sesión-2: cerrar migración de consumidores legacy de `/simulate/approve` y regresión del decision path.

## Tareas cerradas
- O1: 6 tests legacy de `sidecar/tests/test_simulation_blocking.py` migrados al flujo durable. Archivo 16/16 verde.
- P0-1 durable consent: `ConfirmationBroker.request -> gateway.confirm -> ExecutionPipeline -> ToolExecutionGuard -> executor`; `ToolExecutionGuard` valida todos los bindings y consume atómicamente.
- Defecto P0 durable: plan aprobado de alto riesgo volvía a bloquearse por el decision engine al reanudar (`resume_approved_plan`). Fix en `orchestrator.py` `_run_pipeline`: un `approved_plan_grant_id` durable satisface la reconfirmación a nivel de plan (REJECT sigue siendo stop duro; cada paso sigue gobernado por `issue_next_step_grant` -> guard). Test `test_resumed_approved_plan_passes_plan_level_reconfirmation` verde (4/4 e2e durable).
- P0-2 ExecutionPipeline como frontera única: AST estructural `test_execution_bypass_audit.py` 11/11 verde; sin bypass de producción (skill_engine usa pipeline source="skill").
- Sesión-2: `/simulate/approve` ahora devuelve denegación durable estructural (`approved=false`, `requires_reconfirmation=true`, `tool_result=null`, error explícito), no importa `data=None`. Migrados los 4 consumidores legacy de `simulate.approve` al flujo `/v1/execute` gobernado (nada de autoridad por approve):
  - `test_e2e_full_suite.py::TestPermissions::test_admin_executes_command_via_pipeline`
  - `test_e2e_pipeline.py::TestPermissions::test_admin_can_execute_command`
  - `test_integration_pipeline.py::TestPermissionEscalation::test_view_level_blocks_then_admin_allows`
  - `test_orchestrator_intent.py::TestExecutorCommandRouting::test_tool_result_comes_from_executor_not_system`
  Migrados verdes en una sola corrida (4 passed, sin proveedor LLM en el flujo nuevo).

## Pruebas verdes
- `tests/test_simulation_blocking.py` 16 passed (solo lento por timeouts de proveedor LLM externo 49s).
- `tests/test_durable_consent_e2e.py` 3 passed (integration).
- Bloque confirmation/grants: 90 passed (structure, grant repo, grant context, bypass_audit, confirmation_security, confirmation_workflow).
- `tests/test_execution_bypass_audit.py` 11 passed.
- `tests/test_orchestrator_unit.py` 40 passed.
- Consolidado regresión durable (sesión-2): `test_durable_consent_e2e`, `test_durable_consent_structure`, `test_unified_confirmation`, `test_execution_bypass_audit`, `test_orchestrator_unit` -> 64 passed.
- Ruff + py_compile OK. `git diff --check` limpio.

## Fallos pendientes (no investigados / externos)
- (CERRADO en sesión-2) flaky/legacy que esperaban éxito en `/simulate/approve`: migrados al flujo `/v1/execute` durable. `test_approve_reject_cycle` sigue verde (rechazo).
- `test_e2e_full_suite.py` restante (providers web/vault/agentes) y `test_simulation_blocking.py` completo requieren proveedor LLM externo (49s timeout) — presupuesto de red.
- Full Python suite y Rust/Tauri NO ejecutadas en esta sesión (sin presupuesto).

## Símbolo/archivo exacto para reanudar
- Revisar regresión amplia del decision path tras el fix en `sentinel/core/orchestrator.py` (`_run_pipeline`, bloque de decisión para el caso sin grant) y el bridge `sidecar/modules/sentinel_bridge.py` `/simulate/approve`. Ejecutar suites de decisión/simulación amplias (decision_engine, simulate, confirmation) sin LLM.
- Próximo paso: baseline amplio (Objetivo 4) — correr suites de decisión/simulación completas y clasificar el siguiente defecto de mayor impacto (O6).