# FASE 11 — GTM Closure (P0)

**Fecha:** 2026-07-31
**Alcance:** Verificación de cierre de FASE 11. Cierra los requisitos duros P0:
`first_action` centralizado y deduplicado por `session_id`, persistencia de
transiciones de workflows, obligación de que las mutaciones pasen por
herramientas → pipeline → auditoría, y rutas admin `/v1/admin/fleet` probadas.
No se acepta la fase si queda una ruta alternativa sin cobertura.

---

## 1. `first_action` centralizado en el éxito del pipeline

- `sentinel/core/execution_pipeline.py`: campo `_first_action_recorder` +
  `set_first_action_recorder(...)`. En `execute()`, cuando `result.success`, se
  invoca el recorder con `tool_id` y la `session_id` extraída de
  `ctx["identity"]` (helper `_extract_session_id`), protegido contra
  excepciones.
- `sidecar/modules/product_metrics_probe.py`: deduplicación por `session_id`
  (`_first_action_sessions`), conservando `_first_action_recorded` como flag
  global para llamadas sin sesión. `reset_probe()` resetea ambos.
- `sidecar/modules/sentinel_bridge_helpers.py`: se **eliminó** el hook
  duplicado de first_action en `_pipeline_execute`.
- `sidecar/modules/__init__.py` (`_init_execution_pipeline`): registra
  `record_first_action` como recorder del pipeline compartido.

Tests (`tests/test_fase11_closure.py`):
- `test_first_action_deduplicated_per_session` — dos sesiones distintas → 2
  eventos; misma sesión → 1.
- `test_first_action_recorded_once_via_pipeline` — endpoint `POST
  /api/sentinel/cache/clear` vía pipeline emite exactamente una vez.
- `test_first_action_recorded_from_v1_execute` — `/v1/execute` emite una vez.

## 2. Persistencia de todas las transiciones de workflows

`sidecar/modules/automations.py`:
- `_save_workflow(workflow_id, name, steps, status, current_step)` persiste
  estado y step en la tabla `ai_workflows`.
- `_save_workflow_state(workflow_id)` persiste `status`/`current_step` del
  workflow en memoria.
- `_wrap_workflow_transitions()` envuelve `start`, `execute_step`, `complete` y
  `fail` del engine para persistir tras cada transición.
- El wrapper de `create` persiste al crear y registra `automation_created`.
- El wrapper de `delete` borra la fila de SQLite.
- `_load_from_db()` recarga reglas y workflows (incluidos `status` y
  `current_step`) al arrancar/reiniciar.

Tests:
- `test_workflow_transitions_persist_start_step_complete` — tras start/step/
  complete y recarga, el workflow queda `completed` con `current_step` correcto.
- `test_workflow_fail_and_cancel_persist` — `failed` sobrevive a la recarga.
- `test_workflow_delete_persists` — el borrado quita la fila de SQLite.
- `test_workflow_execute_through_tool_persists` — ejecución vía `workflow.execute`
  por pipeline persiste y sobrevive a la recarga.

## 3. Mutaciones obligadas a herramientas → pipeline → auditoría

- Endpoints mutantes de `sidecar/modules/automations.py` pasan por
  `_pipeline_tool(...)` → `get_execution_pipeline().execute(..., source="api")`:
  - `POST /automations` → `automation.rules.add`
  - `DELETE /automations/{rule_id}` → `automation.rules.remove`
  - `POST /workflows` → `workflow.create`
  - `DELETE /workflows/{workflow_id}` → `workflow.delete`
  - `POST /automations/import` → `automation.import`
- Herramientas nuevas: `WorkflowDeleteTool` (`workflow.delete`, `system.write`),
  `AutomationImportTool` (`automation.import`, `system.write`).
- `routers/v1/triggers.py` ya ejecutaba create/update/delete/list vía pipeline;
  verificado (sin mutación directa).
- Barrido AST (`test_no_direct_engine_mutation_outside_persistence_module`):
  ningún `.py` fuera de `automations.py` contiene mutaciones directas de
  `_rules`/`_workflows` ni llamadas a `get_engine().add_rule/remove_rule/
  trigger_rule` o `get_workflows().*` mutantes.

Tests de auditoría:
- `test_automation_creation_produces_audit_entry` — `POST /automations` genera
  entrada `tool_execution` con `automation.rules.add`.
- `test_workflow_creation_produces_audit_entry` — `POST /workflows` genera
  entrada `tool_execution` con `workflow.create`.

## 4. Rutas admin `/v1/admin/fleet`

Nuevo `sidecar/routers/v1/admin_fleet.py`, registrado en `main.py` bajo `/v1`
con tags `["v1","admin"]`. Todas las rutas pasan por `require_admin_identity` +
pipeline (`fleet.*`):

- `GET /v1/admin/fleet/status`
- `GET /v1/admin/fleet/devices` y `GET /v1/admin/fleet/devices/{device_id}`
- `POST /v1/admin/fleet/devices` (registro), `PUT` y `DELETE`
- `POST /v1/admin/fleet/pairing/generate` y `/pairing/revoke`
- `POST /v1/admin/fleet/remote/toggle`
- `GET /v1/admin/fleet/sync/log`

Tests:
- `test_admin_fleet_routes_exist` — recorre `app.routes` (incl. los
  `_IncludedRouter` de FastAPI 1.x) y verifica las 7 rutas.
- `test_admin_fleet_status_and_devices` — GET status/devices con identidad
  admin.
- `test_admin_fleet_device_crud` — registro, consulta, actualización, borrado y
  404 tras borrar.
- `test_admin_fleet_requires_admin` — `require_admin_identity` rechaza
  identidad no-admin (403).
- `test_admin_fleet_route_invokes_admin_gate` — monkeypatch del gate en la ruta
  demuestra que la ruta lo invoca (403).

## 5. Sin rutas alternativas sin cobertura

Revisados `routers/v1/triggers.py`, `agents.py`, `profile.py`, `policies.py`,
`admin_fleet.py`: todos usan `get_execution_pipeline().execute(...)` con
`request_identity` para create/update/delete/list. El barrido AST evita que se
reintroduzcan mutaciones directas fuera de `automations.py`.

## 6. Resultados

| Suite | Resultado |
| ----- | --------- |
| `tests/test_fase11_closure.py` (nuevo, 15 tests) | 15 passed |
| `test_automations_persistence.py` + boundaries + event emission + runtime shadow + plugins fleet | 54 passed |
| Suite completa `sidecar` | **2775 passed / 19 failed / 14 skipped** |

Desglose de los 19 fallos de la suite completa:
- 16 deterministas **pre-existentes** (mismo conjunto que el baseline de FASE 3):
  `test_feedback_cost_api`, `test_filesystem`×3, `test_goal_management`,
  `test_integration_pipeline`, `test_model_feedback`×5, `test_multi_model`,
  `test_multistep_reliability`, `test_security_verification`,
  `test_trust_pipeline_invariants`×2.
- 3 flakes de benchmarks por carga que pasan en aislamiento:
  `test_process_cpu`, `test_dry_run_skip_simulation`, `test_triggers_list`.

**Regresiones: 0.**

## 7. Notas

- `reset_probe()` se expone y `tests/test_fase11_closure.py` lo usa en un
  fixture autouse para aislar métricas entre tests.
- El `_import_payload(payload)` devuelve `{imported_rules, skipped_rules,
  imported_workflows, skipped_workflows}`; la firma coincide con la llamada de
  `AutomationImportTool` (`self._import_fn(params.get("payload") or {})`).
- No se ejecutó commit; los cambios quedan en el working tree para revisión.
