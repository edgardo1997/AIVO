# FASE 4 — MODEL ECOSYSTEM · COMPLETION REPORT

**Área**: Plataforma multimodelo real (registry, descubrimiento, capability intelligence, ranking, coordinación, estrategia, failover) + gestión expuesta vía REST y CLI.

---

## Resumen

Se completó el ecosistema de modelos de Sentinel: un `ModelRegistry` persistente, descubrimiento automático, análisis de capacidades, ranking por feedback/rendimiento, coordinación multi-modelo, estrategia de ejecución, failover con circuit breaker, y dos superficies de gestión: **REST** (`/api/v1/models/*`) y **CLI** (`python -m cli.models`).

Además se cerró la cascada de fallos `403` en la suite de tests (rate limiter interno del framework).

---

## Archivos creados

| Archivo | Propósito |
|---|---|
| `sentinel/core/model_registry.py` | `ModelRegistry` con alta/baja/upsert, filtros por capability/provider/tag, métricas, persistencia a `ModelRepository` |
| `sentinel/core/model_discovery.py` | `ModelDiscovery`: descubrimiento de modelos por proveedor + health check |
| `sentinel/core/model_ranking.py` | `ModelRanking`: scoring por feedback/rendimiento |
| `sentinel/core/circuit_breaker.py` | `CircuitBreaker` por provider (éxito/fallo, degradación) |
| `sentinel/core/model_coordinator.py` | `ModelCoordinator`: descomposición y ejecución multi-modelo |
| `sentinel/core/model_router.py` | `ModelRouter`: selección, fallback, tool calling, multi-modelo, health, streaming |
| `sentinel/intelligence/model_strategy.py` | `ModelStrategyEngine`: decisión de estrategia (single/multi/offline/privacy) |
| `sentinel/intelligence/model_capability.py` | `ModelCapabilityAnalyzer`: análisis de capacidades |
| `sentinel/core/intelligence_coordinator.py` | Fachada única (strategy, capability, ranking, coordinator, failover, CB sync) |
| `sidecar/routers/v1/models.py` | Endpoints REST de gestión del ecosistema |
| `sidecar/cli/models.py` | CLI de gestión del ecosistema |
| `sidecar/tests/test_model_ecosystem.py` | 49 tests (registry, discovery, ranking, router, strategy, coordinador, API) |

## Archivos modificados

| Archivo | Cambios |
|---|---|
| `sidecar/main.py` | Registro de `v1_models_router` (prefijo `/v1`) |
| `sidecar/modules/__init__.py` | Singletons `_model_registry`, `_capability_engine`, `_model_coordinator`, `_model_strategy_engine`; wiring del `CircuitBreaker` al router e intelligence; consumo de strategy/recommend en el orchestrator |
| `sentinel/core/orchestrator.py` | `ExecutionPlan.model_strategy` + `capability_recommendation`; `_process_impl` llama a `decide_strategy`/`recommend_model` y lo expone en el contexto |
| `sidecar/tests/conftest.py` | Fix de la cascada 403: `_reset_tool_rate_limiter()` resetea el `ToolRateLimiter` interno en `clean_state` |

---

## Superficie REST (`/api/v1/models`)

| Endpoint | Método | Descripción |
|---|---|---|
| `/v1/models` | GET | Listar modelos (filtros `provider`, `capability`, `status`) |
| `/v1/models/{model_id}` | GET | Detalle de un modelo |
| `/v1/models` | POST | Registrar modelo (409 si ya existe) |
| `/v1/models/{model_id}` | DELETE | Eliminar modelo (404 si no existe) |
| `/v1/models/strategy` | GET | Decidir estrategia para una tarea |
| `/v1/models/recommend` | GET | Recomendar modelo para una tarea |
| `/v1/models/rankings` | GET | Rankings por task_type |
| `/v1/models/health` | GET | Health check de proveedores |
| `/v1/models/discover` | POST | Disparar descubrimiento de modelos |

## Superficie CLI

```bash
cd sidecar
$env:PYTHONPATH="<repo_root>"
python -m cli.models list [--provider p] [--capability c] [--status s]
python -m cli.models get <model_id>
python -m cli.models register <model_id> --provider p [--coding] [--reasoning] [--tags a b]
python -m cli.models unregister <model_id>
python -m cli.models recommend "<task>"
python -m cli.models strategy "<task>"
python -m cli.models rankings [--task-type t] [--top-k n]
python -m cli.models discover
python -m cli.models health
```

`register`/`unregister`/`discover` persisten en el `ModelRepository` (SQLite vía `StorageEngine`), de modo que las altas sobreviven reinicios; `list`/`get` cargan el repositorio al arrancar.

---

## Fix: cascada de 403 en la suite de tests

**Root cause**: `test_benchmarks.py` agotaba el límite `process.*` de 20/60s del `ToolRateLimiter` interno, y todos los tests posteriores que usaban `/api/sentinel/process` fallaban con `{"error":"Rate limit exceeded for 'process.execute': 20/20 per 60s"}`.

**Solución**: en `sidecar/tests/conftest.py`, `clean_state` ahora llama a `_reset_tool_rate_limiter(orch)` que resetea `guard._rate_limiter` del `ToolRateLimiter` del `_execution_pipeline` y del `_model_router`.

**Resultado**: la suite completa pasó de 107 fallos a **25 fallos** (los 25 restantes son pre-existentes y se reproducen en solitario, sin relación con esta fase: timing, módulo `limited_execution_v2` inexistente, auth 403-vs-404, validación de argumentos, y dependencia de proveedores en vivo).

---

## ¿Todos los tests pasan?

**Suite `test_model_ecosystem.py`: 49/49 pasan**

| Clase | Tests | Qué valida |
|---|---|---|
| Registry | 8 | alta/upsert/filtros/métricas/clear |
| Discovery | 5 | add_default_discoverers, health, run_discovery |
| Ranking | 6 | scoring por feedback, persistencia |
| Router/CircuitBreaker | 10 | selección, fallback, apertura/cierre de CB |
| Strategy/Capability | 8 | estrategia single/multi/offline, análisis de capacidades |
| IntelligenceCoordinator | 3 | fachada integrada |
| OrchestratorStrategyIntegration | 2 | `exec_plan.model_strategy` + `capability_recommendation` |
| ModelEcosystemAPI | 7 | list/recommend/strategy/rankings/register-get-delete/409/404 |

**Suite completa**: `25 failed, 3399 passed, 14 skipped` — **0 regresiones** introducidas por la FASE 4 (los 25 fallos restantes se reproducen en aislamiento y son pre-existentes).

---

## Arquitectura de seguridad

La FASE 4 **NO** modifica `ToolGateway`, `Executor`, `PolicyEngine`, `RiskClassifier` ni `ConsentManager`. Los endpoints REST requieren autenticación (`request_identity`). El registro de modelos es un registro declarativo de metadatos; la ejecución sigue pasando por el pipeline de seguridad existente.
