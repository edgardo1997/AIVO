# FASE 11 — Go To Market (GTM)

**Estado:** Aprobada (canonical) — cierre verificado (P0, 2026-07-31)
**Fecha:** 2026-07-31
**Objetivo:** Definir cómo Sentinel llegará al mercado, qué usuarios atacar
primero, cómo conseguir los primeros clientes y cómo convertir usuarios
iniciales en una comunidad sostenible.

```
Sentinel = Producto adoptado por usuarios reales
```

---

## 1. Principio fundamental

No vender Sentinel a todos desde el día uno. Estrategia inicial enfocada en
usuarios con un problema fuerte y evidente. Una comunidad técnica vale más que
mil anuncios de "IA revolucionaria".

## 2. Mercado inicial

### Grupo 1 — Developers

- **Usuario ideal:** programadores, ingenieros de software, estudiantes
  avanzados, creadores de herramientas.
- **Problema:** cambiar entre herramientas, configurar entornos, gestionar
  proyectos, buscar información, automatizar tareas repetitivas.
- **Sentinel resuelve:** "Prepara mi entorno de desarrollo" — detecta proyecto →
  identifica herramientas → configura entorno → abre recursos → recuerda
  preferencias.
- **Funciones:** Developer Mode, code assistance, project memory, terminal
  automation, Git integration, environment setup, local model support.
- **Mensaje:** *"Tu compañero inteligente que prepara, entiende y automatiza tu
  entorno de desarrollo."* (no "un chatbot para programadores")

### Grupo 2 — Power Users

- **Usuario ideal:** usuarios avanzados de PC, gamers, creadores de contenido,
  entusiastas tecnológicos.
- **Problema:** PC lenta, demasiadas aplicaciones, configuraciones repetitivas,
  falta de control del sistema, privacidad.
- **Sentinel resuelve:** entender la computadora, optimizar el sistema,
  automatizar tareas, mantener control.
- **Funciones:** Gaming Mode, Performance Mode, System Control, Automation
  Engine, Privacy Mode, resource monitoring.
- **Ejemplo de flujo:** "Voy a jugar" → detecta juego iniciado, RAM disponible,
  procesos activos → recomienda perfil Gaming → ajusta prioridad, cierra
  procesos permitidos, guarda estado → confirma.
- **Mensaje:** *"Tu PC deja de ser una herramienta pasiva y se convierte en un
  sistema que entiende lo que necesitas."*

### Grupo 3 — Small Business

- **Usuario ideal:** empresas pequeñas, equipos sin departamento de IA,
  profesionales independientes.
- **Problema:** trabajo repetitivo, pocos recursos técnicos, datos sensibles,
  dependencia de servicios externos.
- **Sentinel resuelve:** asistente privado, automatización interna, control de
  información, procesos inteligentes.
- **Funciones:** Private AI Assistant, document automation, workflow
  automation, local deployment, access policies, audit logs.
- **Mensaje:** *"La inteligencia artificial de tu empresa sin entregar tus
  datos a terceros."*

## 3. Estrategia de entrada al mercado

| Fase | Objetivo | Canales | Contenido / Demostración |
| ---- | -------- | ------- | ------------------------ |
| 1 — Developer First | Crear usuarios técnicos que entiendan el valor | GitHub, Reddit técnico, Discord, Hacker News, YouTube técnico, blogs de programación | "Construyendo Sentinel", arquitectura del agente, modelos locales, automatización del PC, plugin development |
| 2 — Power Users | Expandir tras validación | YouTube, TikTok técnico, comunidades gaming, foros especializados | Antes/después: 20 min preparando entorno → "Prepara mi modo gaming" → 30 segundos |
| 3 — Empresas pequeñas | Cuando exista seguridad comprobada y casos de uso | LinkedIn, partners tecnológicos, consultores IT, comunidades empresariales | Historias de éxito, despliegue local, compliance |

Los developers primero porque pueden probar, encontrar errores, crear plugins y
hablar del producto.

## 4. Product Led Growth

```
Usuario instala gratis → descubre valor → crea automatizaciones
→ depende de Sentinel → actualiza a Pro
```

### Bloqueos naturales Free → Pro

- Más modelos (cloud model access)
- Automatizaciones avanzadas
- Sincronización entre dispositivos
- Plugins premium
- Funciones inteligentes avanzadas

**No bloquear nunca:** seguridad, control del usuario, datos personales.

## 5. Comunidad Sentinel

Incluye: plugin developers, automation sharing, model configurations, templates,
tutorials.

Los usuarios comparten: "mi setup de desarrollo", "mi perfil gaming", "mi
automatización laboral".

## 6. Métricas GTM

- **Activación** (¿valor en los primeros 10 minutos?): primera automatización
  creada, primera acción ejecutada, primer modo activado.
- **Retención:** DAU, MAU, frecuencia de uso.
- **Conversión:** Free→Pro, plugin purchases, enterprise leads.

## 7. Primer objetivo comercial

Buscar **1000 usuarios que amen Sentinel** antes que 100.000 que instalaron y
olvidaron.

---

## 8. Criterio de finalización — verificación

| Criterio | Estado |
| -------- | ------ |
| Usuario objetivo definido | ✅ Sección 2 |
| Mensajes comerciales por segmento | ✅ Sección 2 |
| Canales de adquisición | ✅ Sección 3 |
| Estrategia de lanzamiento | ✅ Sección 3 |
| Comunidad inicial | ✅ Sección 5 |
| Métricas de crecimiento | ✅ Sección 6 |
| Plan Free → Pro → Enterprise | ✅ Secciones 4 y FASE 10 |

## 9. Evaluación de readiness (basada en capacidades reales del código)

| Dimensión | Objetivo | Real | Nota |
| --------- | -------- | ---- | ---- |
| Go To Market Readiness | 9/10 | **6/10** | La estrategia está bien definida, pero la instrumentación de activación está incompleta y la automatización no es persistente ni compartible. |
| Initial Market Fit Potential | 8/10 | **7.5/10** | Los modos Developer/Gaming/Performance existen y funcionan de verdad; el flujo gaming (detectar→recomendar→activar) está implementado en `system_optimizer.py`. Faltan persistencia y pulido de Privacy/Streaming. |
| Community Strategy | 9/10 | **7.5/10** | Existen bases reales (export/import de perfiles y plugins, plugin install desde URL, registry stub de marketplace, SDK de plugins, fleet sync). Falta compartir automatizaciones y el marketplace apunta a una URL local. |

### Gaps detectados contra el código actual

1. **Activación no medible (bloquea GTM).** Solo `mode_used`
   (`product_experience.py:116`) y 3 sitios de `action_completed` emiten métricas
   en producción. `first_action`, `session` y `automation_created` son eventos
   muertos (solo en tests). El onboarding (`src/components/Onboarding/`) es
   informativo y no registra ninguna métrica de activación. Sin esto, el
   "primeros 10 minutos" de la sección 6 no se puede medir.
2. **Automatización no persistente ni compartible.** `AutomationEngine`,
   `TriggerEngine` y `ai_workflows` son in-memory (mueren con el proceso) y no
   tienen export/import. La comunidad no puede compartir automatizaciones y el
   usuario no puede "depender de Sentinel" (requisito del PLG).
3. **Marketplace es un stub.** `MARKETPLACE_REGISTRY_URL` apunta a
   `https://plugins.sentinel.local/registry/v1` (`plugins_service.py:24`); no hay
   registry real ni distribución.
4. **Sin gating de tiers.** Solo hay rate-limit tiers (`free`/`premium` en
   `rate_limiter.py:36-39`); nada está feature-gateado. El plan encajaría en
   `IdentityContext` (auth.py) y se consumiría en `orchestrator.py:562`.
5. **Onboarding sin instrumentación.** No emite `onboarding_completed` ni guía
   hacia modos/automatización.

### Acciones recomendadas para cerrar los gaps

1. Emitir `automation_created` desde `automation_tools.py`/`AutomationEngine.add_rule()`
   y `first_action`/`session` desde el pipeline de ejecución; añadir `user_id`/
   `session_id` al schema de `product_metrics`.
2. Persistir reglas de automatización/triggers en SQLite (p. ej. `product_metrics.db`
   o nueva tabla `automations`) con export/import para compartir.
3. Instrumentar el onboarding para registrar finalización y primera acción
   guiada (primer modo activado).
4. Definir el entitlement Pro (cloud models, sync, premium plugins) como gate
   real sobre `identity["tier"]`.

### Estado de implementación (FASE 11 — ejecución aprobada)

- **Gap 1 (métricas de activación) — implementado.** Nuevo `sidecar/modules/product_metrics_probe.py`
  (wrapper seguro, no bloquea ejecución gobernada). `session` se emite en `initialize_runtime()`,
  `first_action` en `_pipeline_execute()` (primera ejecución gobernada exitosa por proceso,
  con `latency_ms`), y `automation_created` desde los wrappers de triggers (`modules/triggers.py`)
  y automatizaciones (`modules/automations.py`), cubriendo las rutas API y de herramientas.
  `tests/test_automations_persistence.py` valida las tres emisiones; `SENTINEL_PRODUCT_DIR`
  se inyecta en `conftest.py` para mantener los tests herméticos.
- **Gap 2 (persistencia + export/import) — implementado.** Nuevas tablas `automation_rules` y
  `ai_workflows` en `repositories/database.py`. Nuevo `sidecar/modules/automations.py` envuelve
  los singletons de `AutomationEngine` y `AIWorkflows` (persistencia en `add_rule`/`remove_rule`/
  `trigger_rule`/`create`) y expone en `/api/sentinel`: `GET/POST /automations`,
  `DELETE /automations/{rule_id}`, `POST /workflows`, `DELETE /workflows/{workflow_id}`,
  `GET /automations/export` y `POST /automations/import` (formato `sentinel-automations` v1).
  Los triggers ya persistían (`modules/triggers.py`); la cobertura nueva asegura reload,
  roundtrip export/import y rechazo de payloads inválidos.
- **Gap 3, 4 y 5 (marketplace, tiers, onboarding) — pendientes.** Sin cambios.
- **Nota (corregida):** el bug pre-existente por el que `automation_engine.py` y `ai_workflows.py`
  llamaban a `EventBus.emit` (async) sin `await` quedó corregido: ambos engines ahora construyen
  `SentinelEvent` (con `component="automation_engine"` / `"ai_workflows"`) y despachan siguiendo el
  patrón de `trigger.py` (`asyncio.get_running_loop()` → `create_task`, o `asyncio.run` si no hay
  loop en ejecución). `tests/test_engine_event_emission.py` (13 tests) valida el contenido de los
  eventos, la entrega a subscribers y la ausencia del `RuntimeWarning` "coroutine was never awaited".
  Suite completa: 2751 passed / 18 failed (los 18 son pre-existentes y no tocan el código corregido).

---

## Cierre P0 de FASE 11 (2026-07-31) — verificación

Requisitos duros verificados antes de dar la fase por cerrada (reporte completo en
`docs/FASE_11_GTM_CLOSURE.md`):

1. **`first_action` centralizado en el éxito del `ExecutionPipeline` y deduplicado por
   `session_id`.** `sentinel/core/execution_pipeline.py` recibe un recorder vía
   `set_first_action_recorder` y lo invoca una única vez en el éxito de `execute()` con la
   `session_id` extraída de `ctx["identity"]` (`_extract_session_id`). `product_metrics_probe.py`
   deduplica por `session_id` (`_first_action_sessions`) y conserva el flag global para llamadas
   sin sesión. El hook duplicado en `_pipeline_execute` (`sentinel_bridge_helpers.py`) fue
   eliminado. `tests/test_fase11_closure.py` valida dedup por sesión, emisión vía API y vía
   `/v1/execute`.
2. **Todas las transiciones de workflows se persisten.** `automations.py` amplía `_save_workflow`
   con `status`/`current_step`, añade `_save_workflow_state` y envuelve
   `start/execute_step/complete/fail` (`_wrap_workflow_transitions`); `create` persiste al crear y
   `delete` borra de SQLite. Tras simular reinicio (`_load_from_db`), los estados
   created/running/completed/failed y el step sobreviven.
3. **Los endpoints mutantes pasan por herramientas → pipeline → auditoría.** Los endpoints de
   `POST/DELETE /automations`, `POST/DELETE /workflows`, `POST /automations/import` usan
   `_pipeline_tool(...)` → `get_execution_pipeline().execute(..., source="api")`. No queda ninguna
   mutación directa de `AutomationEngine`/`AIWorkflows` desde la capa API (barrido AST en
   `test_fase11_closure.py::test_no_direct_engine_mutation_outside_persistence_module`). Las
   mutaciones generan entradas de auditoría `tool_execution` verificadas en tests.
4. **Rutas admin `/v1/admin/fleet`.** Nuevo `sidecar/routers/v1/admin_fleet.py` registrado en
   `/v1`: status, devices CRUD, pairing generate/revoke, remote toggle y sync log — todas
   `require_admin_identity` + pipeline. Tests cubren existencia de rutas, CRUD, gate admin
   (rechazo de identidad no-admin vía `require_admin_identity` y monkeypatch del gate en la ruta).
5. **Sin rutas alternativas sin cobertura.** `routers/v1/triggers.py`, `agents.py`, `profile.py`,
   `policies.py` y `admin_fleet.py` ya ejecutan vía pipeline con `request_identity`; el barrido AST
   impide reintroducir mutaciones directas fuera de `automations.py`.

**Suite completa (2026-07-31):** `2775 passed / 19 failed / 14 skipped`. Los 19 fallos = 16
deterministas pre-existentes (mismo conjunto que el baseline de FASE 3) + 3 flakes de benchmarks por
carga (`test_process_cpu`, `test_dry_run_skip_simulation`, `test_triggers_list`) que pasan en
aislamiento. **0 regresiones.**
