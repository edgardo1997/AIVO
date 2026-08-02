# FASE 1 — Architecture Freeze

> **Estado: APROBADA** por el usuario. Orchestrator confirmado como núcleo oficial.

## Resultado

`ExecutionPipeline` es el único punto de ejecución de herramientas. Ningún componente de producción puede llamar a `ToolGateway.execute()` fuera del pipeline o del `ToolExecutionGuard`.

| Problema | Fix | Archivo |
|---|---|---|
| Grounding ejecutaba gateway directo en producción | Pipeline inyectado + fail-closed | `sentinel/core/grounding.py`, `sidecar/modules/__init__.py` |
| SkillEngine tenía ruta directa sin guard | Ruta eliminada (fail-closed) | `sentinel/core/skill_engine.py` |
| Rollback con `skip_security=True` | Rollback por el guard (`source="rollback"`) | `sentinel/core/orchestrator.py` |
| Fallback pipeline sin guard | Nuevo param `tool_execution_guard` | `sentinel/core/orchestrator.py` |
| Pipeline sin métricas/auditoría | `event_bus` + `audit_service` + `PerformanceIntelligence` + `FeedbackEngine` conectados | `sidecar/modules/__init__.py` |
| Test AST con fallbacks | `KNOWN_FALLBACKS` vacío — ruta única enforceable | `sidecar/tests/test_execution_pipeline_boundaries.py` |

## Tests

- Suite sidecar: **2751 passed / 18 failed / 14 skipped** (18 = pre-existentes, no relacionados).
- Suite production (`tests/production/`): **61 passed / 1 skipped** (skip = requiere Ollama real).

## Score

Security: **6/10 → 7/10**.

---

## Pendientes documentados (para FASE 2 y posteriores)

1. **Convertir `runtime.py` en `DeprecatedRuntimeAdapter`** antes de su eliminación final.
   - `SentinelRuntime` (`sentinel/core/runtime.py:454`) todavía contiene una llamada directa a `self._gateway.execute()`.
   - Se mantiene en `AUTHORIZED_MODULES` del test AST solo como legado.
   - Acción futura: renombrar/marcar como adapter deprecated con un solo punto de salida hacia `ExecutionPipeline`, verificar que ningún test de producción lo usa, y luego eliminar.
2. **Revisar la clasificación de `skip_security=True` para tools read-only.**
   - Actualmente Grounding usa `skip_security=True` (tools de solo lectura: `system.cpu`, `system.info`, `system.processes`, `system.network`).
   - Acción futura: auditar que el set de tools de grounding sea estrictamente read-only; evaluar una política explícita `system.read` que permita pasarlas por el guard completo sin requerir confirmación.
3. **Mantener el test AST como bloqueo permanente contra nuevos bypasses.**
   - `sidecar/tests/test_execution_pipeline_boundaries.py` escanea `sentinel/core`, `sentinel/security`, `sidecar/modules`, `sidecar/routers` y falla si aparece cualquier `gateway.execute()`/`get_gateway().execute()` fuera de los módulos autorizados (`execution_pipeline.py`, `tool_guard.py`, `runtime.py` legado).
   - Todo commit nuevo debe pasar este test antes de merge.
