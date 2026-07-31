# Persistence Audit — FASE 5.1

**Fecha**: 2026-07-31  
**Alcance**: `sentinel/storage/`, `sentinel/core/`, `sentinel/intelligence/`, `sidecar/repositories/`

---

## Current State

### Bases de datos existentes (4 rutas distintas)

| Base | Ruta | Tablas | Titular |
|---|---|---|---|
| **Operational Memory** (`DatabaseManager`) | `~/.sentinel/sentinel.db` (o `SENTINEL_DB_PATH`) | `execution_history`, `episodic_memory`, `memory_patterns`, `learned_preferences`, `user_preferences`, `session_preferences`, `environment_snapshots`, `environment_changes`, `pending_actions`, `emergency_stop` | Memoria operacional del sidecar (schema v7) |
| **Persistent Intelligence** (`StorageEngine`) | `%LOCALAPPDATA%\Sentinel\sentinel.db` (o `SENTINEL_DATABASE_URL`) | `stored_models`, `feedback_records`, `metric_records`, `conversations`, `decision_history`, `model_performance` | Capa de aprendizaje (esta fase) |
| **Cost Tracker** | `sidecar/cost_tracker.db` | tablas de costos | `CostTracker` |
| **Knowledge Base** | `sidecar/knowledge_base.db` | conocimiento de aplicaciones | `ApplicationKnowledge` |

### Repositorios existentes (`sentinel/storage/repositories/`)

| Repositorio | Tabla | ¿Consumer conectado? |
|---|---|---|
| `ModelRepository` | `stored_models` | ✅ `IntelligenceCoordinator.set_model_repository` + `_init_storage_and_intelligence` |
| `MetricRepository` | `metric_records` | ✅ `_persist_metric()` en `learn()`/`learn_from_model_result()` |
| `FeedbackRepository` | `feedback_records` | ✅ `_persist_feedback()` en `record_feedback()` |
| `ConversationRepository` | `conversations` | ⚠️ creado, sin consumer activo (el sidecar usa `execution_history`) |
| `DecisionRepository` | `decision_history` | ⚠️ creado, sin consumer activo |
| **`ranking_repository`** | — | ❌ **No existe** |

### Componentes en memoria sin respaldo durable

| Componente | Datos | ¿Persistido? | ¿Recuperado al reiniciar? |
|---|---|---|---|
| `PerformanceIntelligence` | métricas de ejecución | ✅ `metric_records` (evento) / `model_performance` | ❌ No se rehidrata |
| `FeedbackEngine` | feedback de usuario | ✅ `feedback_records` | ❌ No se rehidrata |
| `ModelRanking` | scores/rankings | ❌ No hay tabla de rankings | ❌ Vacío tras reinicio |
| `TimePredictor` | predicciones | ❌ | ❌ |
| `LearnedPreference` (SQLiteBackend) | preferencias aprendidas | ✅ `learned_preferences` | ✅ (DB propia del sidecar) |
| `ModelDiscovery` | descubrimientos | ✅ `stored_models` | ✅ `load_registry_from_repository()` |

## Missing Persistence

1. **Execution history** estructurada (FASE 5.4): no existe tabla `executions` con `intent`, `task_type`, `selected_model`, `tools_used`, `duration`, `success`, `failure_reason`, `risk_level`, `cost`, `confidence_score`. Existe `execution_history` en la DB operacional, pero sin esos campos normalizados y en otra base.
2. **Model performance agregada** (FASE 5.5): la tabla `model_performance` existe pero no hay repositorio ni escritura desde la coordinación de inteligencia.
3. **Feedback con execution_id / improvement_signal** (FASE 5.6): el `FeedbackRecord` guarda score en `metadata`; falta `execution_id` y señal de mejora.
4. **User preference memory** (FASE 5.7): no hay `UserPreferenceRepository` en `sentinel.storage`; las preferencias del sidecar viven en otra DB (`user_preferences`/`session_preferences`/`learned_preferences`).
5. **Learning recovery en startup** (FASE 5.8): `_init_storage_and_intelligence` conecta repos y restaura el *registry*, pero **no** rehidrata `PerformanceIntelligence`, `FeedbackEngine` ni `ModelRanking`. Tras reiniciar, rankings/métricas/feedback en memoria están vacíos aunque la DB tenga datos.
6. **Health check de la Learning Database** (FASE 5.8): no existe (¿`sentinel.db` conectada? ¿cuántos registros? ¿última escritura?).
7. **Backups** (FASE 5.9): `StorageEngine._run_migrations` no hace backup ni versiona el esquema (`PRAGMA user_version` sin usar); `DatabaseManager` sí tiene `LATEST_SCHEMA_VERSION`.

## Migration Plan

| Paso | Acción |
|---|---|
| 1 | Migration `002_persistence_intelligence.sql`: tablas `executions`, `user_preferences`; índice `model_performance(model_name, task_type)` |
| 2 | Versionar esquema vía `PRAGMA user_version` + backup automático previo a migraciones nuevas |
| 3 | Repositorios nuevos: `ExecutionRepository`, `ModelPerformanceRepository`, `UserPreferenceRepository` |
| 4 | Coordinador: `set_*_repository`, `record_execution()`, `recover_learning()`, `learning_memory_status()`, preferencias get/set |
| 5 | Wiring en `_init_storage_and_intelligence`: crear repos, conectar, llamar `recover_learning()` al arrancar |
| 6 | Tests: restart recovery, learning loop, DB failure |

## Database Changes

- `executions` (nueva):
  `execution_id TEXT PRIMARY KEY, timestamp, user_request, intent, task_type, selected_model, tools_used TEXT(json), duration REAL, success INTEGER, failure_reason, risk_level, cost REAL, confidence_score REAL, error`
- `user_preferences` (nueva):
  `user_id, key, value TEXT(json), source, evidence_count, confidence, created_at, updated_at, PRIMARY KEY(user_id, key)`
- `model_performance` (existente, sin cambio de esquema): se conecta repositorio + escritura + rehidratación

## Decisión de arquitectura (5.2)

La capa de **aprendizaje** (modelos, métricas, feedback, ejecuciones, preferencias, rendimiento) vive en **una sola base**: la `StorageEngine sentinel.db`. La **memoria operacional** del sidecar (`DatabaseManager`) se mantiene separada por ser un dominio distinto (seguridad operativa: pending actions, emergency stop, episodios). Se documenta para que `SENTINEL_DATABASE_URL` apunte a la misma ruta si se desea consolidación total de archivos. Regla: **una inteligencia, una memoria** — toda la inteligencia de aprendizaje se unifica en `sentinel.db`.

---

## Estado de implementación

| FASE | Entregable | Estado | Verificación |
|---|---|---|---|
| 5.1 | Auditoría | ✅ | `docs/persistence_audit.md` |
| 5.2 | Decisión de arquitectura | ✅ | una base de aprendizaje única |
| 5.4 | `StoredExecution` + `ExecutionRepository` | ✅ | tests `TestNewRepositories::test_execution_repository` |
| 5.5 | `ModelPerformanceEvent` + `ModelPerformanceRepository` | ✅ | tests `test_model_performance_summary` |
| 5.7 | `UserPreference` + `UserPreferenceRepository` | ✅ | tests `test_user_preference_repository` |
| 5.9 | Migraciones versionadas + backup | ✅ | `test_schema_version_tracked` (`user_version >= 2`) |
| 5.3/5.8 | Wiring repos en `_init_storage_and_intelligence` + `recover_learning()` al arrancar | ✅ | smoke test: `exec/perf/pref/model` repos conectados |
| 5.8 | Health check REST + CLI | ✅ | `GET /v1/models/learning-memory`; `sentinel-cli models learning-memory` |
| 5.10 | Tests de reinicio | ✅ | `tests/storage/test_persistence_intelligence.py` |

### Health check

- **REST**: `GET /v1/models/learning-memory` → `{status, records:{metrics, feedback, models, executions, performance, preferences}, last_update}`. `status` es `active`, `degraded` (query falló) o `disabled` (sin repos).
- **CLI**: `sentinel-cli models learning-memory` (misma salida).

### Ejecuciones de referencia

```text
tests/storage/test_persistence_intelligence.py + test_persistent_intelligence.py  → 16 passed
tests/test_model_ecosystem.py                                                     → 49 passed
orchestrator + intelligence + shadow/decision suites                               → 85 passed
```

### Diferidos (no críticos)

- `ConversationRepository` y `DecisionRepository` siguen sin consumer activo (el sidecar usa `execution_history` / `decision_history` de la DB operacional).
- No se creó `ranking_repository`: los rankings se recomputan en `recover_learning()` desde `metric_records` + `feedback_records`, evitando duplicar estado derivado.
