# FASE 2 — Security Boundary Repair

> **Estado: IMPLEMENTADA**. Aprobada por el usuario. ToolExecutionGuard es el chokepoint completo de ejecución.

## Resultado

El `ToolExecutionGuard` ahora es el único punto autorizado de ejecución de herramientas, con **todas** sus dependencias conectadas (auditoría, consentimiento, riesgo, argumentos, rate limit) y la confirmación unificada bajo una sola autoridad.

### Problema crítico resuelto

**Las ejecuciones aprobadas eran denegadas por el guard.** Flujo roto demostrado con test real:

1. `approve_execution()` → `process(skip_simulation=True)` → `context["_orchestrator_approval"]=True`.
2. `DecisionEngine` aprobaba (level=admin) pero `PermissionLevelPolicy` solo reconoce `_confirmation_grant`, no `_orchestrator_approval` → policy devolvía `REQUIRE_CONFIRM`.
3. El guard llamaba `_request_confirmation()` sin consent service (None en prod) → **DENIED**.

Esto era parte de los 18 fallos pre-existentes (`test_simulation_blocking.py::test_approve_execution_runs_and_succeeds`).

| Problema | Fix | Archivo |
|---|---|---|
| Approved executions denegadas por el guard | `_is_already_approved()` honra `_orchestrator_approval`/`_confirmation_grant` (consistente con `tool_gateway.py:294`) | `sentinel/security/tool_guard.py` |
| Guard sin auditoría/consent/riesgo en prod | Wiring completo: `set_consent_service` + `set_risk_classifier` en `main.py`; `set_audit_service` propaga al guard | `sidecar/main.py`, `sentinel/core/execution_pipeline.py` |
| Signature mismatch: `classify(intent, tool_name, args)` vs `classify(intent, plan, context)` | `_classify_risk()` construye Intent/Plan mínimo respetando la firma real | `sentinel/security/tool_guard.py` |
| `user_confirmed` no propagado al resultado | Propagación tras `_execute_via_gateway` | `sentinel/security/tool_guard.py` |
| Grounding con `skip_security=True` incondicional | Fail-closed: solo tools read-only de `READ_ONLY_GROUNDING_TOOLS` lo saltan; el resto pasa por el guard | `sentinel/core/grounding.py` |

## Pendiente FASE 1 resuelto

El pendiente **#2 (clasificación de `skip_security=True`)** quedó resuelto: se definió un whitelist explícito y fail-closed (`READ_ONLY_GROUNDING_TOOLS`) — cualquier tool fuera de él ya no puede saltar seguridad.

## Tests

- Nuevos tests: `TestGuardApprovedExecutionFlow` (orchestrator_approval, confirmation grant match/mismatch, denied sin consent) + verificación de wiring en `test_fase2_security_boundary.py`.
- Suite completa sidecar: **2759 passed / 16 failed / 14 skipped** (antes: 2751/18/14).
  - Se arreglaron 2 fallos pre-existentes (`test_approve_execution_runs_and_succeeds` + otro relacionado).
  - 7 tests nuevos añadidos.
  - Los 16 restantes son pre-existentes (verificado con `git stash` contra el baseline).
- Suites específicas: `test_simulation_blocking.py` (incl. approve flow), `test_fase2_security_boundary.py` (19), `tests/security/test_tool_execution_boundary.py`, `test_unified_confirmation.py`, `test_execution_pipeline_boundaries.py`, `test_skills.py`, `test_e2e_pipeline_phases.py` — todas en verde.

## Score

Security: **7/10 → 9/10**.

---

## Pendientes para FASE 3+

1. **Convertir `runtime.py` en `DeprecatedRuntimeAdapter`** (pendiente #1 FASE 1).
   - `SentinelRuntime` (`sentinel/core/runtime.py:454`) conserva `self._gateway.execute()`. Se mantiene en `AUTHORIZED_MODULES` del test AST solo como legado.
2. **Unificar la doble evaluación de política (guard → gateway)**.
   - El guard evalúa el PolicyEngine y luego el gateway lo re-evalúa (`tool_gateway.py:280-322`) + audit preflight (`log_gateway_authorization`). Es defensa en profundidad válida, pero el resultado de la política debería propagarse para evitar divergencia entre guard y gateway.
3. **Revisar `PermissionLevelPolicy` vs `_orchestrator_approval`.**
   - El policy engine no conoce `_orchestrator_approval`; el guard lo intercepta con `_is_already_approved()`. Evaluar si la política debe reconocerlo explícitamente para eliminar la capa extra.
4. **Mantener el test AST como bloqueo permanente** (pendiente #3 FASE 1).
