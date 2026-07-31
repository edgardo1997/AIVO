# FASE 7 — Observability en Producción

**Estado:** COMPLETADA
**Resultado esperado:** Observability 9/10
**Resultado:** 9/10 (única implementación, dashboard real, `sentinel doctor`, persistencia vía repos oficiales, 61+98 tests)

---

## 1. Objetivo

Una sola implementación de observabilidad en producción, integrada en el
Orchestrator y el ToolGateway, sin implementaciones paralelas, con dashboard
que refleja estado real, `sentinel doctor`, y métricas persistidas a través de
los repositorios oficiales.

## 2. Implementación única

| Stacks | Estado |
|--------|--------|
| `sentinel/observability/` (ObservabilityEngine) | **Única implementación viva** |
| `sentinel/core/observability.py` (legacy) | **Eliminado** |
| `sentinel/core/observability_center.py` (legacy) | **Eliminado** |
| `sentinel/operational_telemetry_hub/` (legacy) | **Eliminado** |
| `sentinel/v2_operational_observability/` (legacy) | **Eliminado** |
| Clúster v2 de control-plane conectado a obs | **Eliminado (46 paquetes)** |

Ver `docs/observability_decommission/01_dependency_report.md` y
`02_deletion_manifest.md` para el reporte de dependencias y el manifest.

## 3. Integración

- **Orchestrator** (`sentinel/core/orchestrator.py`): parámetro
  `observability_engine`, `_wire_observability()` (registra components
  orchestrator/execution_pipeline/tool_gateway/tool_execution_guard),
  `_run_with_observability()` (fail-safe wrapper: traza request + telemetría),
  `_maybe_persist_observability()` (flush cada 25 requests), property
  `observability`.
- **ToolGateway** (`sentinel/core/tool_gateway.py`): `set_observability`,
  helpers `_obs_start`/`_obs_finish` con fallback al contrato legacy
  (`start_tool_span`/`finish_tool_span`, y `start`/`finish` como último
  recurso). Los 6 call sites migrados (start, circuit_open, quality,
  success/error, transient, fatal).
- **Sidecar**: `sidecar/modules/__init__.py` crea
  `ObservabilityEngine(ObservabilityConfig(backup_dir="./data/observability",
  version="sentinel-1.0.0"))`, lo wirea al gateway y al Orchestrator.
  `sidecar/main.py` lo expone en `app.state.observability_engine`.

## 4. Dashboard real

`GET /api/observability/dashboard` (`sentinel/observability/endpoints.py`):

| Sección | Fuente |
|---------|--------|
| `health` | HealthChecker (9 components registrados) |
| `metrics` | MetricsCollector + MetricRegistry |
| `models` | model_metrics (requests, avg_latency, success_rate) |
| `costs` | CostTracker real del Orchestrator (total USD, tokens, calls, by_model) |
| `network` | MonitorService (psutil) + NetworkMonitor (online) |
| `running_tasks` | Event loop asyncio real |
| `plugins` | PluginsService (active plugins) |
| `recovery` | RecoveryManager |
| `alerts` | AlertEngine (8 reglas por defecto) |
| `traces` | TraceManager |
| `system` | estado, versión, uptime |

## 5. `sentinel doctor`

`sidecar/cli/doctor.py` + `GET /api/observability/diagnostics`
(`sentinel/observability/diagnostics.py`):

Checks reales: `observability_engine`, `python`, `resources` (RAM/CPU),
`disk`, `database`, `orchestrator`, `cost_tracker`, `network_monitor`,
`plugins`, `event_loop`.

```bash
python -m cli.doctor          # humano, exit 0/1/2
python -m cli.doctor --json   # máquina
```

## 6. Persistencia

- **Manual**: `IntelligenceCoordinator.persist_observability_metrics(engine)`
  → `engine.to_metric_records()` → `MetricRepository.save_batch()`.
- **Por requests**: Orchestrator `_maybe_persist_observability()` (cada 25).
- **Por tiempo**: task de background en `sidecar/main.py` (`_start_observability_flush`,
  cada 60 s) que persiste incluso con tráfico bajo.

Verificado end-to-end: 8 registros persistidos en `metric_records` y
consultables vía `MetricRepository.get_component_metrics("observability")`.

## 7. Tests

| Suite | Resultado |
|-------|-----------|
| `tests/production/observability/` (FASE 7, 37 tests: dashboard, diagnostics, alert engine, metrics collector, trace manager, recovery, logging, persistencia, integración orchestrator, arquitectura) | **37 passed** |
| `sidecar/tests/observability/` (unit, 61 tests) | **61 passed** |
| `tests/production/` total | **61 passed, 1 skipped** (Level 3 sin Ollama) |

- **Arquitectura**: `test_architecture_single_implementation.py` valida cero
  imports de los stacks legacy en código de producción, directorios eliminados,
  wiring moderno en Orchestrator/ToolGateway/Sidecar, y ausencia de paquetes
  paralelos.

## 8. Puntuación

| Criterio | Cumplido |
|----------|----------|
| Única implementación en producción | ✅ |
| Integrado en Orchestrator y ToolGateway | ✅ |
| Sin implementaciones paralelas | ✅ |
| Dashboard con estado real | ✅ |
| `sentinel doctor` | ✅ |
| Métricas persistidas vía repos oficiales | ✅ |
| Tests contra el stack real (no stubs) | ✅ |
| Sin módulos huérfanos / refs colgantes | ✅ |
| Suite sidecar colecta limpia (2629 tests) | ✅ |
| **Resultado** | **9/10** |
