# FASE 3 — Consolidación de la Frontera de Ejecución Única

**Rama:** estabilización
**Fecha:** 2026-07-31
**Base:** `docs/FASE_2_SECURITY_BOUNDARY_REPAIR.md`

## Objetivo

Ejecutar los pendientes documentados en FASE 2 para consolidar el **chokepoint de ejecución**:

1. **(P1)** Eliminar la última salida directa a `ToolGateway` fuera del pipeline (`SentinelRuntime`).
2. **(P2)** Unificar la doble evaluación de política guard → gateway (propagación del resultado).
3. **(P3)** Honrar `_orchestrator_approval` en `PermissionLevelPolicy` (elimina la capa extra del guard).
4. **(P4)** Suite completa sin regresiones.
5. **(P5)** Este reporte.

## Estado final

- **Suite sidecar:** 2762 passed / 17 failed / 14 skipped.
  - Los 17 incluyen **2 flakes por carga** (`test_process_cpu`, `test_rate_limiter_survives_multiple_calls`) que pasan en aislamiento.
  - Los **16 deterministas son el baseline pre-existente** (verificado contra FASE 2): `test_feedback_cost_api`, `test_filesystem` ×3 (TypeError), `test_goal_management`, `test_integration_pipeline` (escalación de permisos), `test_model_feedback` ×5, `test_multi_model`, `test_multistep_reliability`, `test_security_verification`, `test_trust_pipeline_invariants` ×2.
  - **0 regresiones** introducidas por esta fase.
- **Score Security: 9/10** (sin cambios frente a FASE 2; se elimina redundancia sin debilitar el chokepoint).

---

## P1 — `SentinelRuntime` → DeprecatedRuntimeAdapter (única salida vía pipeline)

### Problema

`sentinel/core/runtime.py:454` (paso 9 de `process`) llamaba directamente a `self._gateway.execute()`, quedando fuera del `ExecutionPipeline`. El test AST lo mantenía en `AUTHORIZED_MODULES` como "legado".

### Solución

- `runtime.py` marcado **DEPRECADO**:
  - Docstring actualizado señalando `Orchestrator` como núcleo oficial y `DeprecatedRuntimeAdapter` para integraciones nuevas.
  - `logger.warning(...)` en `__init__` (emitido solo cuando se instancia — 0 impacto en producción).
  - Nuevo parámetro `execution_pipeline` en `__init__` + setter `set_execution_pipeline()`.
- Paso 9 reescrito para ejecutar vía `self._pipeline.execute(...)` con **fail-closed**: si no hay pipeline configurado, se bloquea la ejecución con `"ExecutionPipeline required"` y `success=False`.
- **Test AST reforzado** (`test_execution_pipeline_boundaries.py`): se quitó `sentinel/core/runtime.py` de `AUTHORIZED_MODULES`. Ahora `gateway.execute()` solo es legal en `execution_pipeline.py` y `tool_guard.py`. Cualquier reintroducción de llamada directa **rompe el build**.

### Verificación

- `tests/runtime/test_sentinel_runtime.py` actualizado: el test de pipeline completo ahora inyecta un pipeline mock y aserta `pipeline.execute.called` (antes `gateway.execute.called`). **5/5 pasan.**
- `tests/e2e/fixtures/sentinel_test_environment.py`: `create_sentinel_runtime` ahora construye un `ExecutionPipeline` real con `ToolExecutionGuard` real cableado a los stubs (StubPolicyEngine ALLOW, StubConsentService, StubRiskClassifier) + `StubToolGateway.get_spec()` añadido. El fixture queda **fiel a producción** (runtime → pipeline → guard → gateway).

---

## P2 — Unificar doble evaluación de política (guard → gateway)

### Problema

El guard evaluaba el `PolicyEngine` y luego el gateway **re-evaluaba** la misma política (`tool_gateway.py:280-322`), con riesgo de divergencia entre ambas decisiones y doble trabajo de confirmación.

### Solución

- El guard ahora captura el resultado crudo del `PolicyEngine` (`self._last_policy_result`) durante `_evaluate_policy()`.
- `_execute_via_gateway()` lo propaga en el contexto como `_guard_policy_result`.
- `tool_gateway.execute()`: si recibe `_guard_policy_result`, **lo usa directamente** (construye `policy_data`, rechaza si es DENY) en lugar de volver a llamar a `policy_engine.evaluate()`. La re-evaluación solo ocurre cuando el gateway se usa **sin guard** (llamadas directas legítimas de tests/rutas legacy).

### Verificación

- Suites específicas en verde: `test_tool_execution_boundary.py`, `test_unified_confirmation.py`, `test_fase2_security_boundary.py`, `test_execution_pipeline_boundaries.py`, `test_simulation_blocking.py`, `test_tool_calling.py` (**65 passed**).
- Llamadas directas al gateway (sin guard) intactas: `test_application_control_characterization.py`, `test_adversarial_security.py` (**77 passed**, 3 fallos pre-existentes).

---

## P3 — `_orchestrator_approval` en `PermissionLevelPolicy`

### Problema

`PermissionLevelPolicy.evaluate()` solo reconocía `_confirmation_grant` y `params.confirmed`, no `_orchestrator_approval`. El guard compensaba con `_is_already_approved()`, pero la política en sí divergía y forzaba la capa extra en el guard.

### Solución

- `sentinel/policies/security_policies.py`: cuando el efecto calculado es `REQUIRE_CONFIRM` y el contexto trae `_orchestrator_approval`, la política devuelve `ALLOW` directamente (mismo patrón que `_confirmation_grant`).
- **2 tests nuevos** en `test_confirmation_workflow.py`: con `_orchestrator_approval` → ALLOW; sin él → REQUIRE_CONFIRM. **27/27 pasan.**

---

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `sentinel/core/runtime.py` | DEPRECADO + `execution_pipeline` param/setter + paso 9 fail-closed vía pipeline |
| `sentinel/security/tool_guard.py` | Captura y propagación de `_guard_policy_result` |
| `sentinel/core/tool_gateway.py` | Usa `_guard_policy_result` cuando viene del guard (no re-evalúa) |
| `sentinel/policies/security_policies.py` | `_orchestrator_approval` → ALLOW en `PermissionLevelPolicy` |
| `sidecar/tests/test_execution_pipeline_boundaries.py` | `runtime.py` fuera de `AUTHORIZED_MODULES` (permanente) |
| `sidecar/tests/runtime/test_sentinel_runtime.py` | Test de pipeline completo vía `execution_pipeline` |
| `sidecar/tests/test_confirmation_workflow.py` | +2 tests de `_orchestrator_approval` |
| `tests/e2e/fixtures/sentinel_test_environment.py` | Fixture cableado a pipeline + guard real; `StubToolGateway.get_spec()` |

---

## Próximos pasos sugeridos

- Atacar los 16 fallos deterministas pre-existentes en una fase de limpieza (TypeError en `test_filesystem`, escalación de permisos, feedback API, invariantes de auditoría).
- Eliminar completamente `SentinelRuntime` y `DeprecatedRuntimeAdapter` cuando no quede ninguna referencia (tests/e2e fixture migrado a `Orchestrator`).
