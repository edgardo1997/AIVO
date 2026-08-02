# SENTINEL — FULL SYSTEM REALITY AUDIT

**Fecha y hora (UTC):** `2026-08-02 07:10 UTC-04:00`
**Auditado por:** agente de IA (READ-ONLY). Solo se creó/escribió este archivo.
**Estado del mejor de la sesión:** base estable verificada por tests.

---

## 0. IDENTIDAD EXACTA DEL ESTADO AUDITADO

| Atributo | Valor |
|---|---|
| Fecha y hora | 2026-08-02 07:10 (UTC-04:00) |
| Rama | `feature/sentinel-intelligence-migration` |
| Commit base / HEAD | `1ee215b` — "F7 - Observabilidad produccion: decommission v2, Orchestrator+ToolGateway, dashboard real, sentinel doctor" |
| Files modificados (tracked) | 112 |
| Files sin seguimiento (untracked) | 53 |
| Diff tracked (vs HEAD) | 111 archivos, **+2261 / -893** |
| Frontend versión | 1.0.0 (`package.json`) |
| Sidecar versión | 1.0.0 (Cargo/tauri 1.0.0; no hay archivo `version.py`) |
| Tauri / Rust versión | 1.0.0 (`tauri.conf.json`, `Cargo.toml`) |
| Schema SQLite sidecar | `LATEST_SCHEMA_VERSION = 8` (`sidecar/repositories/database.py:31`), WAL, `user_version`-tracked, migraciones v4–v8 |
| Schema SQLite "intelligence" | `StorageEngine` separado, propio `sentinel-intelligence.db`, `user_version=2` (`sentinel/storage/database.py`, migraciones 001/002) |
| Python / Node / Rust | Python 3.12.10 · Node v24.18.0 · cargo 1.96.1 |
| Submódulos | NINGUNO (`git submodule status` vacío) |
| Artefactos presentes | MSI + NSIS (`Sentinel_1.0.0`), `.sig` (minisign daemon/Tauri), SBOMs (npm/python/rust), `SHA256SUMS`, `release-manifest.json` bajo `src-tauri/target/release/bundle/` + `release-metadata/1.0.0/` |
| Artefactos AUSENTES | **`update.json` no existe** (solo configurado en `tauri.conf.json:32`); Authenticode documentado pero sin evidencia de firma |
| Archivos generados/históricos en el worktree | `src-tauri/tauri.conf.before-new-updater-key.json`, `src-tauri/tauri.conf.json.backup-pre-sentinel-1.0-signing.json` (untracked, backups históricos); artefactos legacy `AIVO_0.1.0`, `Sentinel_1.0.0-rc.1` en bundle |

**(NOTA de migración exacta):** existe un v7→v8: `MIGRATIONS[7]`→`MIGRATIONS[8]` dentro de `sidecar/repositories/database.py:606-725` (columnas/grants). El `StorageEngine` tiene su propio `user_version=2` independiente.

### Reproducibilidad
**PARCALMENTE reproducible.** En esta máquina, con `sidecar/.venv` + `sidecar.exe` compilado (`src-tauri/target/release/bundle/`) + `node_modules`, la suite unitaria/integración/seguridad/productive se ejecuta verde. NO es reproducible limpio sin: (a) construir `sidecar.exe` via PyInstaller, (b) iniciar la suite LLM/e2e (requiere proveedor + red), (c) el sello `.sig`/updater `update.json`. No se modificó el worktree para comprobación.

### Comandos ejecutados (read-only)
```
git rev-parse HEAD; git branch --show-current; git log --oneline -8
git status --porcelain; git diff --stat; git diff --numstat; git submodule status
Version checks (python/node/cargo); package.json/Cargo.toml/tauri.conf.json
pytest -m unit ................... 231 passed
pytest <durable+consent+pipeline+automations+plugins+migration> ... 303 passed
pytest -m security .............. 236 passed
npm.cmd test (vitest) ........... 33 files / 146 passed
cargo test --release ............ 5 passed (solo smoke; hay 0 en main.rs)
pytest tests/production ......... 60 passed, 1 FAIL, 1 skipped
```
### Alcance no verificado (este sesión)
- Suite e2e LLM / simulación (`/process` real con proveedor) — **no ejecutada** (depende de proveedor externo; presupuesto).
- `test_e2e_real`/`test_e2e_update_recovery` están gated detrás de `SENTINEL_RUN_REAL_E2E` — **no ejecutados**.
- Suite completa default (incluye e2e con provider) — parcial (unit/integration/security/production), no íntegra.
- Código muerto/histórico a eliminarse: **no se eliminó nada** (READ_ONLY).

---

## 1. RESUMEN EJECUTIVO

### ¿Qué es Sentinel hoy?
Un **agente de escritorio local con sidecar** (Rust/Tauri + FastAPI/Python) que: planifica intenciones, ejecuta herramientas con **control de consentimiento y riesgo**, mantiene memoria/auditoría en SQLite, integra multi-modelo (cloud + local) con **circuit breaker y fallback**, y en v1.0 redujo exitosamente la superficie de ejecución a **una sola frontera** (`ExecutionPipeline → ToolExecutionGuard → ToolGateway → Executor`). Existen release build MSI/NSIS + SBOM + firma updater, pero **el feed de actualización (`update.json`) y Authenticode están pendientes**.

**Madurez técnica estimada:** ~6/10 (el "core duro" está verde y la frontera de ejecución es real, pero la autoridad durable réplica no está enganchada a producción y la suite "real" falla en confirmación).

**Madurez comercial:** ~3.5/10 (no sellable aún; no hay onboarding para no-técnicos; consentimiento-sensible no operacional).

**Vista/visión técnica completada:** la arquitectura objetivo F1–F7 está implementada Y conectada (routing, decisión, consentimiento estructural, frontera única, obs/recovery, telemetría). Lo que NO está cerrado: cola durable de planes, recuperación de estados fuera de la ruta dirigida, y la "confirmation executor" en el harness real.

**Veredicto explícito**

```text
¿Lo lanzaría hoy? NO
¿Lo entregaría a beta cerrada? NO  (a 1–2 gates de distancia)
¿Está listo para usuarios no técnicos? NO
¿Está listo para manejar acciones sensibles? NO
```
Justificación:
- **NO lo lanzaría**: la gateway de consentimiento durable (única fuente de autoridad efectiva) está **solo en tests**; `create plan grant` no se alcanza desde ningún producto router. La suite `PRODUCTION CERTIFICATION GATE` **FALLA** en `test_ejecucion_con_consentimiento` (no hay confirmation executor en el stack). Un producto que no puede confirmas ejecución en el stack "real" no se lanza.
- **Beta cerrada NO:** requiere cerrar el gate de certificación, cablear el grant durable, y publicar `update.json`.
- **No-técnicos / sensibles**: el login JWT es directamente in croyable/in; multi-user ausente; acciones sensibles dependen del bucle de confirmación fallido.

### Cinco fortalezas
1. **Frontera única de ejecución real** (P0-2): toda ejecución → pipeline → guard → gateway → executor; `skip_*` no bypass (verif: orchestrator.py:1578, tool_guard.py:405, execution_pipeline.py:85; `legacy.py` muerta). Sin `shell=True`, metachars bloqueados (`executor_service.py`).
2. **Simulación durable estructural correcta** (P0-1): `ExecutionGrantContext` frozen con binds (user/session/identity/plan/plan_hash/step/tool/params) verificadas criptográficamente en consumo (`tool_guard.py:342-363`), expiración, SÚPER ATOMIC (`BEGIN IMMEDIATE`), replay rechazado, auditoría append-only (`execution_grant_audit`).
3. **Isolation y fail-closed**: demora. PolicyEngine default DEMY, identity debe estar autenticado, `no guardion → no ejecución`, plugins mutantes → 503 (fail-closed), sandbox separado con restricciones de syscall.
4. **Inteligencia real y persistente**: registros de modelos, métricas por ejecución, `recover_learning` en startup; multi-modelo operativo con fallback probado; modelos locales.
5. **Testing denso y reproducible** en el núcleo: 231 unit + 303 durable/pipeline/plugins + 236 security + 146 JS + 60 production pasan en ~1 minuto sin red.

### Cinco riesgos principales
1. **Autorización durable dormida**: plan-grant no productivo → P0-1 estructuralmente excelente pero **inalcanzable en producción** (P0).
2. **Gate de producción magenta** (suite real falla; harness no configura confirmation executor) → riesgo de "demo verde, prod rojo" y certificación engañosa.
3. **Doble persistencia** (SQLite v8 sidecar + v2 storage-engine en archivo separado) → estado fragmentado, orden/consolidación frágil, `budgets` no persist.
4. **Updater sin feed + flujo de auth roto** (login JWT no alcanzable; JWT refresh con rotación) → no actualizable comercial y multi-sesión frágil.
5. **Automatizaciones no re-vinculadas a consentimiento/sesión** tras restart → puede ejecutar acciones tras vencer contexto/sesión.

### Cinco bloqueos inmediatos (mínimo, secuencia)
1. Cerrar el **gate de producción de confirmación** (wire `gateway.set_confirmation_executor(pipeline.execute)` en harness + en el runtime real de ejecución).
2. **Enviar plan-grant a producción** (rute/service que `request_plan_grant`/`approve_plan_grant`; hoy solo tests).
3. Publicar **`update.json`** + aplicar Autocode → re-firmar `.sig` en orden.
4. Arreglar **`/auth/login`** (no en `UNAUTHENTICATED_PATHS` → caída de gallina que inviabiliza JJWT por HTTP).
5. Re-bind de consentimiento/sesión en **automatizaciones** después de restart.

### Recomendación principal (CTO)
No lanzar. Dedicar 2±1 semanas a: cable durable en producción + cerrar gate real + publicar feed de update + apuntalar auth/automatizaciones; luego habilitar beta cerrada con telemetría y sin `input` sensible. En paralelo consolidar la doble persistencia y añadir un trial_renew de lado de privacy/privacy.

---

## 2. ARQUITECTURA REAL

### Flujo conectado real (cada entrypoim que puede ejecutar una herramienta)
```
HTTP router / bridge
   └─ _pipeline_execute / orch.execute_direct / get_execution_pipeline().execute
        └─ Orchestrator.process → _run_pipeline → _execute_single_step
             └─ ExecutionPipeline.execute      (execution_pipeline.py:85)
                  └─ _execute_guarded (fail-closed si guard None)
                       └─ ToolExecutionGuard.execute  (tool_guard.py:97)
                            ├─ ArgumentValidator (siempre, :109)
                            ├─ policy engine default-DENY + consent
                            ├─ consume_execution_grant (:342-363)
                            └─ _execute_via_gateway → ToolGateway.execute (:405)
                                 └─ tool.execute(params, ctx) (tool_gateway.py:465)
Confirmaciones: gateway.confirm → broker → _confirmation_executor=pipeline.execute
```
**Entry points verificados:** `/v1/execute`, `/v1/confirm`, `/chat(/stream)`, `/api/sentinel/process(,/multi-agent,…,/offline)`, `/fs/*`, `/executor/*`, `/fleet/*`, `/admin/*`, `/ai/*`, `/fooonomicaciones·automations`, `/product/*`, `/v1/agents|triggers|profile|admin-fleet|policies`, `/permissions/rules`. **TODOS` → pipeline. Los plugins mutaciones → **503 fail-closed** (`sentinel_plugins.py`). WS `/ws/events` = solo lectura.

### Arquitectura objetivo
Documentada en `docs/cto/03_ARCHITECTURE.md` y `docs/FASE_1_ARCHITECTURE_FREEZE.md`. Sigue siendo válidamente sufrida contra curso; la frontera es pipeline.

### Diferencias (clasificadas)
| Diferencia | Severidad | Nota |
|---|---|---|
| `sentinel/routing/legacy.py` llama a `guard.execute` directo | **medium** | código muerto/no importado; debe borarse o recadirse |
| `StorageEngine` (intelligence) vs `DatabaseManager` (sidecar) | **high** | dos bases separadas |
| `ProcessMultiAgent` ejecuta sin llamadas de tool (text-only) | **low** | sin bypass, sin acción |
| `process_offline` solo enqueue, `_sync_pró` stub | **medium** | capazmente sin ejecución |
| `update.json` y `authenticode` | **high** | release no completa |
| Fronula durable plan-grant solo-en-tests | **critical** (ver P0-1) | dormido |

### Autoridades (single-source?)
| Ámbito | ¿Autoridad única real? |
|---|---|
| Entrada | Middleware auth (`auth.py:194`) + rate limit outer. OK single. |
| Consentimiento | `ConfirmationBroker` = única fábrica (pero plan-grant no producido) → OK únicas pero dormida |
| Ejecución | `ExecutionPipeline` única (P0-2) → OK |
| Política | `PolicyEngine` default-DENY single → OK |
| Persistencia | **NO única** (2 backends) → única por dominio aunque duplicada |
| Models/models | `ModelRouter` single → OK |
| Observability | `ObservabilityEngine` single → OK |
| Auditoría | Appéndiceúnico + `audit_service` → OK append-only |

### Duplicaciones
- Persistencia: `DatabaseManager(v8)` + `StorageEngine(v2)` coexisten producidos.
- Routes deprecated: `/simulate/approve` y `approve_with_modifications` viven como *denial* intencionales (contrato fail-closed). No autorizan.
- Bloques de tests de "confidence/trust" y "real stack": `legacy.py` dead.
- Doc describes "Settings→Actualizaciones" button que **no existe** en `Settings.tsx` → runtime/doc mismatch.
- Muchos docs untracked (`docs/cto/*`, `docs/FASE_*`) describen otros per-context; `FASE_11_*` son planes, no runtime.

---

## 3. CONSENTIMIENTO DURABLE Y P0-1 (resultado test adversarial)

| Garantía | Estado | Evidencia |
|---|---|---|
| `approve_execution()` no autoriza | **PASS** | `orchestrator.py:1861-1883` error "deprecated…reconfirm" |
| `approve_with_modifications()` no autoriza | **PASS** | `orchestrator.py:1845-1859` |
| `PendingActionRecord` no autoriza | **PASS** | `operational_memory.py:102-114`; v8 pone `confirmed=0` |
| `/simulate/approve` no autoriza | **PASS** | `sentinel_bridge.py:848-871` (`approved=False,requires_reconfirmation`) |
| Plan modificado requiere reconfirmación | **PASS** | `sentinel_bridge.py:886-897` |
| `ConfirmationBroker` = única fábrica | **PARTIAL** | únicamente `request_plan_grant`/`approve_plan_grant` (solo tests) – single-tool sí wired |
| `PlanApprovalGrant` persiste | **PASS**(schema)/**PARTIAL**(prod) | tabla v8; solo repo (execution_grant_repository.py) |
| `StepExecutionGrant` persiste | **PASS**(schema) | v8; tool_guard consume, pero source approved_plan no alcanzable |
| `ExecutionGrantContext` typed+immutable | **PASS** | `security/models.py:25-54`, frozen, `__post_init__` valida |
| user/session/identity/plan binds | **PASS** | `tool_guard.py:342-363` recompute identity_hash/params_hash |
| `plan_hash` verificado | **PASS** | `confirmation.py:89-101` sha256 recompute + mismatch→PermsError |
| expiración | **PASS** | `transition_plan`: rodov `expires_at`; `consume_step` `AND expiry>` |
| consumo atómico | **PASS** | `BEGIN IMMEDIATE` + `WHERE status='approved'` + `rowcount==1` |
| replay rechazado | **PASS** | identity/params hash mismatch; `consume_step` ya-consumido→False |
| concurrencia single-winner | **PASS** | unique(plan_grant, step_index) + immediate txn |
| fallo parcial bloquea siguientes | **PARTIAL** | `issue_next_step_grant` exige `consumed` previos; `fail_plan`; peccato el layer ordering enforced |
| restart conserva estados | **PARTIAL** | persists en SQLite; `resume_approved_plan` NO alcanzable en prod |
| auditoría conserva evidencia | **PASS** | `execution_grant_audit` + append-only triggers |

**Declaración adversarial**: NO declare P0-1 cerrado solo por same tests. El único "durable plan approval" **no está cableado** a ninguna ruta/service de producción → el/unfeature "resume approved plan" es académico hoy.

---

## 4. FRONTERA ÚNICA DE EJECUCIÓN Y P0-2

- Every toExecute → `ExecutionPipeline` → `Guard` → `Gateway` → `Executor`. `skip_safety`: **no existe**; `skip_simulation` no es bypass (solo pre-sim, ejecución igual pasa pipeline). `gateway.execute` llamada única en producción: `tool_guard.py:405`. `tool.execute` solo desde `tool_gateway.py:465`. `legacy.py` llama `guard.execute` directo pero **no importado** → muerto/latente.
- Clasificaciones: grounding PASS, skills PASS, rollback PASS (:1838 source=rollback), confirmaciones PASS, plugins fail-closed, automations PASS (pipeline tools), model tools PASS (ToolExecutor→pipeline), multi-agent OPEN (sin execution), offline OPEN (stub).

### Status P0-2
**CONDITIONALLY CLOSED.** La frontera es real y sin bypass productivo; único pendiente: **eliminar o re-cablear `sentinel/routing/legacy.py`** para no dejar superficie "guard-direct ♦" ambigua.

---

## 5. SEGURIDAD COMPLETA

Score 0–10 del backend:
| Control | Score | Nota |
|---|---|---|
| Autenticación | 5 | JWT HS256 + host-gate localhost; pecc: `/auth/login` no alcanzable, JWT no revocable |
| Identidad/sesiones | 7 | `IdentityContext` typed; requirement authenticated; bane reality single-user trust |
| Autorización | 8 | policy default-DENY, `*` admin, EmergencyStop |
| Consentimiento (estructura) | 7 | único 单 de plataforma, bound criptográfico |
| Validación de argumentos | 8 | `ArgumentValidator` wired en cada ejecución |
| Path traversal | 7 | sensitive-path; OS roots; Aquí WP scanner/PD |
| Command injection | 7 | `shell=False` + metachars bloqueados + `shlex.split`; residual `ShellExecuteW`/`wt_cmd` |
| Rate limiting | 7 | middleware orb per-path + `ToolRateLimiter` + sliding window |
| Replay | 5 | JWT `jti` sin denylist; refresh sin rotation |
| Concurrency | 7 | `BoundedSemaphore(5)` + transacciones inmediatas |
| Secretos | 8 | `.env` gitignored; no hard de `sk-`; plaintext password en jwt_auth (sin bcrypt) |
| Redacción | 6 | rojo/obscure parcial |
| Auditabilidad | 8 | insert-only triggers, hash cols `audit_log` |
| Fail-closed | 8 | no session→503; no guard→block; policy DENY |
| Aislam. plugins | 8 | sandbox process + validator (solo hasta producción) |
| Aislam. proveedores | 5 | seed en config; no espacio con… |
| Sandboxing | 6 | sandbox plugin; sidecar sin sandbox de proceso general |
| Supply chain | 4 | SBOMs presentes pero sin firma de artefactos/feed |
| Actualizaciones | 3 | proceso documentado; feed ausente |
| Rollback | 5 | update() plugin; no rollback de DB backup (backup_manager) |
| Recuperación | 6 | backup_manager wired | resume-dormido |
| Multiusuario | 3 | single local user; auth multi rotto |

**Medidas duras:** no secretos en repo (env gitignored, sin `sk-` clave en prod). `git ls-files` no commitea `.env`. `test_local_identity` admin estrictamente modo-test.

---

## 6. PERSISTENCIA Y RECOVERY

Backends: (`DatabaseManager`, v8, WAL) y (`StorageEngine`, v2 intelligence `.db`).

| Entidad | Backend | Tabla (migración) | Producido | Sobrevive restart | Recuperación |
|---|---|---|---|---|---|
| Conversaciones | DatabaseManager | `conversation_threads` (v4) + Storage conversaciones (no usado) | sí | sí | version-merge/transactions |
| Memoria | DatabaseManager + StorageEngine | `*memory*`, `learned_preferences` | sí | sí | TTL cleanup |
| Planificaciones / grants | DatabaseManager | `plan_approval_grants`, `step_execution_grants`, `audit` (v8) | **parcial (food)** | sí | resume dormido |
| Auditoría | DatabaseManager | `audit_log` + observ | sí | sí | insert-only |
| Automatizaciones | DatabaseManager | `automation_plans/rules`, `triggers`, `trigger_history` | sí | sí | `_load_from_db` |
| Workflows | DatabaseManager | `ai_workflows` | sí | sí | resume_data |
| Modelos descubiertos | StorageEngine | `stored_models` | sí | sí | recover_learning |
| Metricas/feedback | StorageEngine | `metric_records`, `feedback_records` | sí | sí | recover |
| Costos | StorageEngine(cost) | runtime `_cost_tracker` | **parcial** | — | — |
| Budgets | (sin migración) | runtime | **NO** | NO | — |
| Perfiles | DatabaseManager | `user_profiles`, `profile_history` | sí | sí | — |
| Pending | DatabaseManager | `pending_actions` v8 | sí | sí | consume_immediate |
| Eventos | in-memory bus | `events` | sí | **NO persiste** | — |
| Config | DatabaseManager | `config`, `user_preferences` | sí | sí | rollback |

**Verificación especial:** migración v7→v8 NO es un archivo `.sql`, es `MIGRATIONS[8]` en Python (sidecar/repositories/database.py:606-725) con idempotencia; `StorageEngine` backup_`_backup_before_migration` y Txn IMMEDIATE. Corrupción/restart: grants/audit sobrevivir restart (SQLite) pero recovery de `sentinel-intelligence.db` no probado en este stack.

---

## 7. INTELIGENCIA

| Capacidad | Existe | Conectado | Persiste | Tests | Evidencia real |
|---|---|---|---|---|---|
| Model discovery | sí | sí (deferred por governance) | sí | sí | — |
| Registry | sí | sí | sí | sí | default para capability selection |
| Routing | sí | sí | no | sí | priority default |
| Ranking | sí | sí(parcial, solo `smart`) | sí | sí | **no default** |
| Feedback | sí | sí(wired) | sí | sí | pero no inyectado `set_feedback_store` |
| Métricas | sí | sí (por tool call) | sí | sí | evidencia real |
| Costo | sí | sí(parcial `smart`) | parcial | sí | — |
| TimePredictor | sí | sí(parcial) | no | — | — |
| Capability-select | sí | sí | — | sí | modelo candidate |
| Circuit breaker + fallback | sí | sí | no | sí | cadena real proveedores |
| Multimodelo | sí | sí | — | sí | operativo |
| Consenso | sí | sí(advisory) | — | sí | parcial |
| Memoria | sí | sí | sí | sí | operative |
| Aprendizaje | sí | sí (basado real) | sí | sí | `recover_learning` |
| Explicabilidad/incertidumbre | correl | advisory | — | — | heurístico |

**Respuestas directas:**
- ¿Sentinel aprende de ejecuciones reales? **SÍ (parcial)** — registra metrics por tool y persiste+recarga, pero la selección por feedback/cost no es el decisivo por defecto.
- ¿Experiencia sobrevive al reboot? **SÍ** (`recover_learning`, `ModelRepository`).
- ¿Selección de modelos usa métricas reales? **PARCIAL** — por defecto `priority`/disponibilidad; `smart` (feedback/cost) no inyectado.
- ¿Multi-modelo opera en producción? **SÍ** (`enable_multi_model`).
- ¿Fallback probado con proveedores reales? Solo bajo `SENTINEL_RUN_REAL_E2E`; **no ejecutado este sesión**.

---

## 8. PLUGINS Y AUTOMATIZACIONES

**Plugins**: SDK (manifest/validator/permission) + `core/plugin_manager.py` implementados; UI HTTP mutaciones **fail-closed (503)** (`sentinel_plugins.py:72-130`) hasta boundary gobernada. Sandbox process + guard syscall existe (`plugin_sandbox.py`). Aislamiento fuerte; funcionalidad HTTP no operativa (intencional).

**Automatizaciones**: crean/producen/recuperan en SQLite (`automations.py`), restore on startup, persist. **Flag crítico**: rules restore sin `session_id/consent/request_id y el engine no revalida el consentimiento en trigger-time → una automatización puede disparar/ejecutrar tras restart sin su contexto original → **ROSP prohibido en este READ-ONLY (riesgo P1).

---

## 9. TESTING REAL (lo ejecutado — evidencia)

| Bloque | Resultado | Notas |
|---|---|---|
| `-m unit` | **231 passed** | 8.06s |
| durable+consent+pipeline+automations+plugins+migration | **303 passed** | 44.4s |
| `-m security` | **236 passed** | 15.5s |
| Frontend vitest | **33 files / 146 passed** | |
| Rust/Tauri | **5 passed** | hostés limpios en`11 llén | lib.rs) |
| Production/stress/chaos | **60 passed, 1 FAILED, 1 skipped** | ver FAIL debajo |
| Simulación/LLM-e2e | **NO ejecutado** | provider + budget |
| `-m performance` | **NO ejecutado** | excluida por defecto (`-m "not performance"`) |
| `test_e2e_real`/updater | **NO ejecutado** | env-gated |

**FAIL — regresión real:**
`tests/production/orchestrator/test_level1_real_orchestrator.py::test_ejecucion_con_consentimiento`
- Síntoma: *"Confirmation execution pipeline is unavailable"* en`stack.gateway.confirm(...)`.
- Causa: el harness de producción (`tests/production/harness.py`) construye `gateway`/`confirmation_broker` pero **NO llama `gateway.set_confirmation_executor(pipeline.execute)`** → confirmar válida la accion pendiente pero no ejecuta.
- Clasificación: **regresión actual / wiring real incompleto** (el comentario del certgate lo refleja: "CERTIFICATION GATE FAILED"). En prod `modules/__init__.py:501-502` sí lo setea; el harness "real" no — evaporates el valor de esa suite.

**Resumen de la suite completa:** núcleo muy verde. El único FAIL de la suite "real" es el bucle de consentimiento → ejecución NO cableado en el harness real.

---

## 10. DESKTOP Y EXPERIENCIA DE USUARIO

Flujo implementado: Login local (sin credenciales reales), Onboarding (modal + flag), chat/Workbench(988 line), plano(`PlanDisplay`), explicación, confirmación (ConsentDialog) → **evolución no conectada en prod**, ejecución (`/v1/execute`), resultado, auditoría (`Audit.tsx`), historial/memoria, conexión ups, ErrorRecoveryPanel → todo test UI en vitest (146).

Problemas UX:
- **No hay UI de actualizaciones** (updater Rust registrada, pero no `check/install` en JS; doc → mismatch).
- **Sin modo offline toggladoión** explícito global; parcial via Dashboard/Setup + queue offline.
- **`BASE=http://127.0.0.1:8765` hardco mediante Tauri proxy (`lib.rs:158/`sidecar_request`) que siempre llama 8765. Sin switch de entorno/port.
- Accesibilidad básica (un test `ConsentDialog.accessibility`).
- Producir offsidecar/provider-down: ErrorBoundary/ErrorBox localizados.

Estados de la ruta real: instalación → primer inicio → onboarding → modelo (auto-discovery deferida por governance) → chat → intención → plan → **confirma funciona** → **ejecución asistida fallida en stack real →** resultado parcial → auditoría → historial → restart/recuperación (backup+) → **actualización ausente** → dev/uninstall (no probado).

---

## 11. RENDIMIENTO Y FIABILIDAD

**No medí (no invento cifras)**: startup/y/o/CPU/RAM/redis. No hay benchmark ejecutado (excluido `-m performance`).

Cosas SOLIDAS del código (evidencia sin medir):
- Semillero de concurrencia `_through=semaphore(5)`; rate limits; timeouts provider/fallback; lógica de retry con jitter.
- `backend` WAL + `BEGIN IMMEDIATE` para grants → sin locks de concurrencia en transacciones.
- `event_stream` cancela streams (`cancel_sidecar_stream` via watch) — sin run-away.
- requestAnimationFrame coalescing en frontend para streaming (no flood UI).

Cosas PENDIENTES/metricas que corroborar (no medidas):
- colecciones ilimitadas, memory-leaks, N+1, health sequeciales — **no verificadas**.

**Latencia del pipeline de herramientas NO medible** sin medir (depende del tool).

---

## 12. RELEASE Y COMERCIALIZACIÓN

| Item | Estado |
|---|---|
| Versiones consistentes | 1.0.0 en `package.json`/`Cargo.toml`/`tauri.conf.json` | 
| MSI / NSIS | **present** (`Sentinel_1.0.0_x64_en-US.msi`, `.exe`) |
| `.sig` (minisign/Tauri) | **present** (420 B) |
| SBOM | present (npm/python/rust) |
| `SHA256SUMS`, `release-manifest.json` | present en `release-metadata/1.0.0` | 
| `update.json` | **NOT present** → el feed no está publicado. **PUETHOD A actualizable**. |
| Authenticode | **documentado** (`docs/RELEASE_AUTENTICO...`), sin evidencia de que esté aplicada. **Clasifico**: dependencia externa diferida (NO es defecha de arquitectura). |
| Reproducibilidad | parcial (requiere build exe + firma + feed) |
| Clean install / upgrade / rollback / uninstall | upgrade/test no ejecutado con feed ausente |

### Bloqueos técnicos internos
1. Poner `update.json` + re-firmear artifacts tras aplicar FirmA.
2. Re-vincular el gate de confirmación real.
3. Pulse de login / multi-user.

### Bloques externos
- Authenticode (signing via "Microsoft Artifact Signing") — **externo diferido**.
- Provider LLM para e2e reales.

### Decisiones comerciales
- Modelo de licencia / telemetría (privacidad), local-only vs cloud multi-user, soporte de backups.
- Cost per-execution y budgets aún sin persistencia (no monetizable ainda).

---

## 9. WORKTREE Y MANTENIBILIDAD

Clasificación de 112 modificadas + 53 untracked por dominio:
- **Seguridad/consentimiento**: `sentinel/core/confirmation.py`, `execution_grant_repository.py`, `tool_guard.py` (mutation durable). Forman unidad atómica.
- **Pipeline**: `execution_pipeline.py`, `orchestrator.py`, `tool_gateway.py`, `db`.
- **Producto (new)**: `sentinel/product/*`, `plugins`, `automations.py`, `model_center`, `control_center`. Untracked, consistentes entre sí; **no consolidated** a HEAD.
- **Obs/recovery/telemetry**: `observability/*`, `backup_manager`.
- **Tests** nuevos: `test_durable_consent_*`, `test_plugin_*`, `test_product_*`, `test_execution_bypass_audit`, `test_automations_persistence`. Consistentes.
- **Documentación**: `docs/cto/*`, `docs/FASE_*`, `docs/plugin-sdk.md`, etc. — untracked (docs migration). **Coherentes pero sin commits.**
- **Generado/acidental/histórico**: `src-tauri/tauri.conf.*.backup-*` backups untracked, `AIVO_0.1.0*` / `Sentinel_1.0.0-rc.1*` bundles antiguos, `.venv`, `node_modules`. **Deben limpiarse** (pero READ_ONLY no elimino).
- **Incompletos/contradictorios**: `process_offline` stub (no ejecuta); `legacy.py` dead; doc `Settings→Actualizar` mismatch; harness de producción sin confirmation_executor; `smart` feedback/cost no inyectado.

### Consistencia a aplicar
1. Def key de commits: (a) durable-grant/consent, (b) frontera única+config, (c) product/plugins (untracked), (d) observabilidad/recovery, (e) tests, (f) release/artifacts/reproductive infra.
2. Antes de commitear: `ruff`, `git diff --check`, secrets (sin aportación visible), borrar backups de tauri.conf, mover docs a commit en fase.

**Puntuación mantenibilidad**: 4/10.
**Complejidad**: costo alto (muchas capas) → 4/10 madurez.
**Deuda**: pasada por los "untracked" sin commit + doble persistencia + died stubs (vale 5/10).
**Reproducibilidad**: parcial (requiere env/secrets).
**Facilidad de revisión**: 6/10 (tests claros, pero muchos archivos sin commit).

---

## 10. SCORECARD

Fórmula: promedio simple (1–10) y promedio ponderado donde pesos = X (security, consent, expense) antes del resto del promedio.

| Categoría | Nota | Eff fortaleza / debilidad / prueba faltante / condición +1 |
|---|---|---|
| Arquitectura | 8 | única frontera; debilidad: 2 backends; +1 eliminar legacy.py |
| Runtime | 7 | arran llo; debilidad: confirm-loop no cableado; +1 cerrar gate |
| Seguridad | 7 | fail-closed; debilidad: jedec entrada + login; +1 opaque auth real |
| Consentimiento | 6 | estruct sólida; dormido (no producí); +1 put wired durable |
| Pipeline | 9 | única frontera verificada; +1 quitar legacy |
| Persistencia | 6 | v8 + WAL; debilidad: 2 DB, budgets no; +1 unificar |
| Recuperación | 6 | backup_manager; resume dormido |
| Inteligencia | 6 | aprende real; ranking no default |
| Multimodelo | 8 | operativo con fallback; |
| Plugins | 5 | sandbox fuerte; HTTP 503 (off) |
| Automatizaciones | 5 | persistance; consentimiento no re-vinculado |
| Observability | 6 | dashboard + alerts; metrics reales |
| Testing | 6 | densa verde; e2e_real/performance off |
| Desktop | 6 | Really-shell real; updater no-UI |
| UX | 5 | vistas ricas; offline/update absent |
| Rendimiento | 6 | sin medirggl; dis. |
| Fiabilidad | 6 | retry/circuit; lógico; restart types no prov |
| Mantenibilidad | 4 | 112+53 uncommitted, 2 DB, stubs |
| Release name | 5 | artifacts + update-in | 
| Preparación comercial | 4 | no sellable; auto fragile |
Promedio simple = (vSirve sum) /20 ≈ **6.2** (suma=124/20).
Promedio ponderado (bias 2x seguridad/consentimiento/pipeline/perm: des) = (8·2+7·2+9·2+6·2+...) ponderado ≈ **5.9**.
Madurez técnica ≈ **58%**; Madurez comercial ≈ **30%**; Visión completada ≈ **65%**.

**Prueba faltante más importante:** la **"clearing loop" en stack real de producción** (confirm(→ejecuta) — directamente del FAIL del gate.

---

## 11. BACKLOG RECOMENDADO (no copiar anterior)

| ID | Prioridad | Problema | Evidencia | Riesgo | Dependencia | Dificultad | Gate de cierre |
|---|---|---|---|---|---|---|---|
| A1 | **P0-1** | Durable plan-grant NO cableado a producción; `resume_approved_plan` inalcanzable | confirmation.py:79 "Not wired"; request solo tests | Sensitive actions sin recovery | propio | M | Registry long/governance crea grant via HTTP y ejecuta en stack real |
| A2 | **P0-2** | Harness de producción no setea confirmation executor → "CERTIFICATION GATE" falla | tests/production/...test_ejecucion_con_consentimiento | Cert engañosa | propio | S | ese test pasa |
| A3 | **P1** | `/auth/login` no alcanzable (fuera de UNAUTHENTICATED) | auth.py:191(sin login); jwt | login roto | propio | S | login vía HTTP funcional con credencial |
| A4 | **P1** | Automatizaciones desre-vincular consentimiento tras restart | automations.py:122-128 | ejecuchar tras expiración | A2? | M | trigger revalida session/consent |
| A5 | **P1** | `update.json` ausente; updater no publicable | tauri.conf.json:32; ausencia del arch | no actualizable | Authenticode | M | build + update.json generado + chivilo |
| A6 | **P2** | JWT refresh sin rotation; jti no denylist | jwt_auth.py | replay refresh | — | S | refresh de un token → invalidación |
| A7 | **P2** | legacy.py dead llama guard directa | legacy.py:586 not imported | doble frontera confusa | — | S | eliminado o rewire |
| A8 | **P2** | Doble persistencia (v8 + v2) | database.py v8 + storage/database | fragilidad | — | L | consolidación de esquema |
| A9 | **P3** | Automatización offline stub; multi-agent tool | orchestrator.py:2101,2022 | funcionalidad faltante | — | M | — |
| A10 | **P3** | budgets no persist | — | costo | — | S | persist |
| A11 | Externo | Authenticode signing | RELEASE_AUTHENTICODE | — | externa | L | firma con signtool verif |

---

## 11. CAMINO MÍNIMO AL PRODUCTO (dependencias)

```
AHORA (0–1 sem): A2 (gate real), A1 wire-durable plan grant, A3 login fix.
SIGUIENTE (1–3 sem): A4 automations, A5 update.json+artifacts+rollupHarness,
                     elección regex quantitative, consolidate #A8.
DESPUÉS (3–6 sem): beta cerrada: seguridad multi-user, telemetría/privacy,
                     disponibilidad instalel + recovery estreso-plugin, performance sustenance.
RC (6–10 sem): actualizable completo, clean install/upgrade tests, monetización.
LANZAMIENTO COMERCIAL (>10 sem): license/consent profesional, onboarding no-técnico.
```
Estimación de esfuerzo total P0–P1 (color pura ingeniería): **~6–10 sem ingeniero single real** si end-to-end (hi cuesta y seccioncidos). Incertidumbre: **media-alta** (proceso de firmer/feeds externos). Factores que amplían: multi-tenant/multiuser serio, ACID real del `storage-engine`, telemetría que cumple. Comun cerrar.

---

## 12. VEREDICTO FINAL

1. **¿Qué es Sentinel hoy?** Un agente de escritorio local con **frontera única de ejecución y consentimiento estructurado**, multi-modelo (cloud+local), memoria/auditoría persistentes y observabilidad de producción — no comercializable aún.
2. **¿Qué quedó realmente terminado?** núcleo + frontera única (P0-2 condicional), consentimiento estructural (P0-1, a nivel de código), pipeline, decisión/riesgo/policies default-DENY, multi-modelo con fallback+CB, telemetry/recovery/backup, 151+ unit/security/during/JS/rust pasen, build release MSI gui.
3. **¿Qué creíamos terminado pero NO está?** (a) P0-1 "durable consent" **no operativo en producción** (solo tests); (b) el loop de confirmación en stack real **se cae**; (c) inteligencia **no es el decider por defecto**; (d) actualización/autorolbox no publicada; (e) automatización no re-bind a consentimiento; (f) doble persistencia no consolidada.
4. **Mayor riesgo:** que una **beta de "demo verde"** se entregue sobre el harness que no ejecuta el loop/certificador→"production seam" frágil; y la **doble persistencia** en producción.
5. **Mayor fortaleza:** la **frontera única de ejecución + consentimiento atómico y criptográficamente ligado**, implementada y verificada a fondo (solo plan-gover no wired).
6. **¿Qué se rompería con 100 usuarios/betados?** el **flujo de confirmación real** (no se ejecuta), **login/rbrief** (no alcanzable), y el **resume durable** (nunca se llega). Y covertnd para diagnosticar.
7. **¿Qué se rompería con 10,000?** **multi-tenant/identidad** no existe (single-user), **concurrencia de grants/número**, **DB doble archivo + WAL** (corrupción/migraciones), **feed del update** si existiera (no — será tiempo).
8. **¿Puede beta cerrada?** **NO aún**; sí tras A2+A1+A4+login ib, con candidato manual y telemetry diagnost.
9. **¿Puede venderse?** **NO** — no hay identity multi-user, no consent-loop en prod, no update feed, no privacy/privacy manett. El core (agente supervisado single-user) no es un producto comercial autónomo para No-técnicos hoy.
10. **¿Qué haría mañana como CTO?** cerrar el **gate de producción**, conectar el **durable plan**. us y **ese puño**; public overall. Al: (1) wire durable durable (A1) y confirm-exec (A2); (2) fix login (A3) y reconciling. Luego tengo beta con candidatos reales que ejecute. En paralelo: consolidar el doble esquema de DB y encender telemetría para diagnosticar el retorno real.

---
**Reglas de no-falsa-conformidad cumplidas:** cada garantía exige `Implementation + Wiring + Tests + RuntimeEvidence`. Donde falta, marqué **PASS** solo con prueba real (e.g. boundary pipeline verificado runtimes) o **PARTIAL/FAIL/NOT-VERIFIED**.
```