# FASE 11 — Auditoría Estructural de Bypasses (P1)

**Fecha:** 2026-07-31
**Alcance:** Inventario automatizado (AST) de toda llamada a `ToolGateway.execute`,
ejecución directa de herramientas y `ExecutionPipeline.execute`. Clasificar cada
llamada como **entrada gobernada** / **consulta no gobernada** / **bypass**.
Eliminar o encapsular bypasses confirmados y probar que una herramienta sin
`required_permissions` no puede evadir política, guardia ni auditoría.

---

## 1. Inventario automatizado

Inventario generado con grep + análisis AST (`tests/test_execution_bypass_audit.py`).

### 1.1 Llamadas a `ToolGateway.execute()`

| Ubicación | Línea | Clasificación |
|---|---|---|
| `sentinel/security/tool_guard.py` | `_execute_via_gateway` (~351) | **Gobernada** — ruta del guard de ejecución |
| `sentinel/core/execution_pipeline.py` | ramo `skip_security` (~144) | **Gobernada** — sólo para whitelist de grounding read-only |

**Total: 2 sitios en producción.** No existe ningún otro llamador directo del gateway.

### 1.2 Ejecución directa de herramientas (`.execute` fuera del dispatch del gateway)

| Ubicación | Clasificación |
|---|---|
| `sentinel/core/tool_gateway.py` dispatch (`_dispatch`) | **Gobernada** — único sitio que invoca `.execute` de herramientas |
| `sidecar/modules/tool_calling.py` / `tool_calling_helpers.py` | **Gobernada** — construye `ToolRequest` y delega en el guard |

No hay `tool.execute(...)` directo en producción fuera del dispatch del gateway
y de los helpers que delegan en el guard.

### 1.3 Llamadas a `ExecutionPipeline.execute()`

| Ubicación | Línea | `source` | Clasificación |
|---|---|---|---|
| `sentinel/core/grounding.py` | ~316 | `grounding` (skip_security para whitelist) | **Gobernada** |
| `sentinel/core/orchestrator.py` | ~1493 (paso de plan), ~1758 (rollback) | `sentinel` / `rollback` | **Gobernada** |
| `sentinel/core/runtime.py` | ~477 | `sentinel_runtime` | **Gobernada** (runtime en desuso) |
| `sentinel/core/skill_engine.py` | ~120 (vía `orchestrator.execute_direct` → `process()`) | `skill` | **Gobernada** |
| `sidecar/modules/admin.py` | `_pipeline_execute` | `api` | **Gobernada** |
| `sidecar/modules/fleet.py` | `_pipeline_execute` | `api` | **Gobernada** |
| `sidecar/modules/automations.py` | ~361 | `api` | **Gobernada** |
| `sidecar/modules/sentinel_bridge_helpers.py` | `_pipeline_execute` (~148) | `api` | **Gobernada** |

**Total: 9 sitios, todos con `source` explícito y a través de `process()`.**

### 1.4 Rutas de llamadas de modelo (LLM)

| Ubicación | Línea | Clasificación |
|---|---|---|
| `sentinel/routing/legacy.py` | ~586 | **Gobernada** — `ToolRequest` → guard |
| `sentinel/execution/tool_executor.py` | ~58 | **Gobernada** — `ToolRequest` → guard |

Las llamadas originadas por el modelo también pasan por `ToolExecutionGuard`.

### 1.5 Consultas no gobernadas (intencionales)

Endpoints read-only que consultan herramientas/estado directamente sin ejecutar
nada (`/tools`, `/catalog`, `/status`, healthchecks). No constituyen bypass
porque no ejecutan herramientas ni mutan estado.

---

## 2. Bypasses confirmados y eliminados

### 2.1 (FIX) Auditoría rota en ejecuciones del pipeline

`ExecutionPipeline._record_metrics` llamaba `AuditService.log_action` con kwargs
`resource=`/`user_id=` que la firma `log_action(action, details, status, user)`
no acepta → `TypeError` silenciado → **las ejecuciones (incluidas las denegadas
por API) no generaban entrada de auditoría**.

**Fix** (`sentinel/core/execution_pipeline.py`):
```python
audit.log_action(action="tool_execution",
                 details={tool_id, source, duration_ms, success, policy_decision, error},
                 status="completed" | "failed", user=user_id)
```
Cada ejecución del pipeline (éxito, fallo, denegación) queda auditada.

### 2.2 (FIX) Herramientas activas sin permisos

`ToolGateway.register` ya rechazaba herramientas ACTIVE sin `required_permissions`
(`ValueError`), pero `execute()` no tenía defensa en profundidad.

**Fix** (`sentinel/core/tool_gateway.py`): fail-closed en `execute()` — si
`spec.required_permissions` está vacío, devuelve `ToolResult.fail` con
`policy_decision="_missing_permissions"` y `policy_result={effect: "deny",
policy_id: "_missing_permissions"}`. **Nunca ejecuta la herramienta.**

### 2.3 (FIX) Whitelist de grounding con herramienta inexistente

`READ_ONLY_GROUNDING_TOOLS` incluía `"system.health"` (alias de `system.info`,
no un tool registrado con permisos) → habría permitido `skip_security` hacia un
ID no registrado.

**Fix** (`sentinel/core/grounding.py`): el whitelist ahora sólo contiene IDs
reales de herramientas registradas que declaran permisos. Los tests verifican
esa propiedad estructuralmente.

### 2.4 (FIX) Pérdida de `policy_result` / `quality_result` en la cadena

El guard envolviendo el resultado del gateway y el pipeline envolviendo el
resultado del guard descartaban `policy_result` y `quality_result` → la auditoría
del orchestrator persistía `policy: null` (causa del fallo pre-existente
`test_trust_pipeline_invariants.py::test_pipeline_audit_persists_actual_policy_and_quality_results`).

**Fix**:
- `sentinel/security/models.py`: `ExecutionResult` gana campos
  `policy_result` / `quality_result` (serializados en `to_dict`).
- `sentinel/security/tool_guard.py::_execute_via_gateway`: los propaga.
- `sentinel/core/execution_pipeline.py::_execute_via_guard`: los propaga al
  `ToolResult`.

El test pre-existente **ahora pasa**; la auditoría persiste la decisión de
política y la calidad reales.

---

## 3. Garantías verificadas

1. La única puerta de ejecución de herramientas es `ToolGateway` + `ToolExecutionGuard`.
2. `skip_security` se usa **exclusivamente** para la whitelist de grounding read-only
   (`test_skip_security_only_used_by_grounding_whitelist`).
3. Una herramienta sin `required_permissions` es bloqueada en 3 capas:
   - `register` → rechazo al registro;
   - `gateway.execute` → fail-closed sin ejecutar;
   - guard → `ExecutionResult(decision=DENIED)` sin invocar el gateway.
4. Toda ejecución del pipeline queda auditada con `status`/`user_id` correctos.
5. La whitelist de grounding sólo contiene herramientas reales con permisos.
6. `PolicyEngine` es fail-closed (`default_effect=DENY`) con `IdentityPermissionPolicy`,
   `CapabilityMatrixPolicy`, `PermissionLevelPolicy`, `GranularPermissionPolicy` y
   `EmergencyStopPolicy` registradas.

---

## 4. Tests (`sidecar/tests/test_execution_bypass_audit.py`)

- `test_inventory_gateway_execute_only_in_authorized_files` — AST: sólo 2 llamadores.
- `test_inventory_tool_execute_only_in_gateway_dispatch` — sin ejecución directa de tools.
- `test_inventory_pipeline_is_single_governed_entry` — pipeline viaja por `process()` con `source`.
- `test_register_rejects_active_tool_without_required_permissions`
- `test_gateway_fails_closed_on_tool_without_permissions`
- `test_pipeline_execution_always_audited`
- `test_no_perm_tool_blocked_by_policy_before_execution`
- `test_guard_rejects_no_perm_tool_without_calling_gateway`
- `test_grounding_whitelist_tools_all_declare_permissions`
- `test_skip_security_only_used_by_grounding_whitelist`
- `test_runtime_pipeline_execution_writes_audit_via_api` (integración: `/v1/execute` real audita)

**Resultado: 11 passed.**

---

## 5. Resultados

- Suite completa: **2788 passed / 17 failed / 14 skipped** (baseline anterior: 2775/19/14).
- **0 regresiones.**
- **1 fallo pre-existente eliminado:** `test_pipeline_audit_persists_actual_policy_and_quality_results`.
- Los 17 fallos restantes = 15 deterministas pre-existentes + 2 flakes de carga
  (pasando en aislamiento: `test_triggers_list`, `test_simulation_blocking`).
- Conclusión: no quedan rutas de ejecución no gobernadas; el modelo de autoridad
  (política → guard → gateway → pipeline → auditoría) se mantiene estructuralmente.
