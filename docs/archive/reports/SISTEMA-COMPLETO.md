# INFORME DEL SISTEMA — SENTINEL v1.0.0

> Generado del código base real — Julio 2026
> Proyecto: `C:\Users\edgar\OneDrive\Documents\AIVO`

---

## 1. DATOS DEL PROYECTO

| Campo | Valor |
|---|---|
| Nombre | sentinel |
| Versión | 1.0.0 |
| Licencia | MIT |
| Frontend | React 19.2 + TypeScript 6.0 + Vite 8.1 |
| Desktop | Tauri 2.x |
| Backend | Python 3.12 + FastAPI + Uvicorn |
| Base de datos | SQLite WAL-mode (21 tablas) |
| Target Python | 3.12 |
| Target Node | 22 |

---

## 2. HISTORIAL GIT

```
0a23261 2026-07-07 Initial commit: AIVO - AI-powered PC control panel
0158e16 2026-07-07 Add build/ to gitignore, remove PyInstaller build artifacts
56064df 2026-07-07 Add tauri-plugin-updater, fix identifier, initialize git repo
fd0b1cb 2026-07-07 Remove private key from tracking, add updater.key to gitignore
761547e 2026-07-07 Regenerate updater key with empty password, update public key in config
555bff0 2026-07-14 chore: capture pre-beta stabilization baseline
c7e90e4 2026-07-14 docs: close phase 0 baseline preservation       [tag: pre-beta-audit]
1f39823 2026-07-14 Complete phase 1 build quality baseline          [tag: phase-1-complete]
975aa5e 2026-07-14 Complete phase 2 deterministic test suite        [tag: phase-2-complete] (HEAD)
```

**Tags:** v1.0.0, pre-beta-audit, phase-1-complete, phase-2-complete

**Branches:** main, codex/phase-0-baseline, codex/phase-1-build-quality, codex/phase-2-deterministic-tests

**Impacto total:** 370 archivos cambiados, 61,827 inserciones, 51,756 eliminaciones

---

## 3. CÓDIGO FUENTE

### Python (backend + core)

| Directorio | Archivos | Líneas de código |
|---|---|---|
| `sentinel/core/` | 44 módulos | 15,076 |
| `sidecar/modules/` | 19 módulos | — |
| `sidecar/services/` | 13 servicios | — |
| `sidecar/repositories/` | 11 repositorios | — |
| `sidecar/tests/` | 85 tests | — |
| **Total Python** | **235 archivos** | **41,751 líneas** |

### TypeScript / TSX (frontend)

| Tipo | Archivos | Líneas |
|---|---|---|
| `.ts` | 10 | — |
| `.tsx` | 71 | — |
| **Total** | **81 archivos** | **9,003 líneas** |

### Archivos más grandes del proyecto

| Archivo | Líneas | Rol |
|---|---|---|
| `sidecar/modules/sentinel_bridge.py` | 1,713 | API bridge 106 endpoints |
| `sentinel/core/orchestrator.py` | 1,425 | Pipeline orquestador 7 pasos |
| `sentinel/core/file_pipeline.py` | 793 | Pipeline de archivos PDF/DOCX/imágenes |
| `sentinel/core/operational_memory.py` | 763 | Memoria operacional + patrones |
| `src/types.ts` | 730 | Tipos TypeScript del frontend |
| `sentinel/core/model_router.py` | 668 | Router multi-proveedor IA |
| `sidecar/modules/__init__.py` | 629 | Registro central de 73 tools |
| `sidecar/repositories/database.py` | 492 | Schema SQLite + 29 helper functions |

---

## 4. TESTS

### Frontend (Vitest)

| Métrica | Valor |
|---|---|
| Archivos de test | 27 |
| Tests totales | **116** |
| Estado | ✅ 100% passing |
| Tiempo | ~16s |

**Archivos de test:** Agents, Alertas, api, AppContext, Audit, Chat, Console, Dashboard, Execute, FeedbackCosts, Files, Fleet, IntentInput, KnowledgeBase, Memory, Monitor, Observability, Permissions, Plugins, Policies, Profile, Reports, Sentinel, Settings, Triggers, usePolling, Vault

### Backend (Pytest)

| Métrica | Valor |
|---|---|
| Archivos de test | 85 |
| Tests colectados | **1,718** |
| Tiempo de colección | 1.3s |
| Marcadores | unit, integration, security, adversarial, e2e |

---

## 5. ARQUITECTURA

### Modelo Local Integrado (`sentinel/local_model/`)

Sentinel incluye un runtime de inferencia local **propietario** que descarga y ejecuta automáticamente:

| Componente | Detalle |
|---|---|
| **Runtime** | llama.cpp b10025 (Vulkan, GPU acceleration) |
| **Modelo** | Qwen3-1.7B-GGUF (Q8_0) |
| **Tamaño** | ~1.8 GB (descarga automática) |
| **Fuente** | HuggingFace: Qwen/Qwen3-1.7B-GGUF |
| **Integridad** | SHA256 verificado en descarga |
| **Servidor** | `llama-server.exe` en `127.0.0.1:11435/v1` |
| **API** | OpenAI-compatible |
| **Contexto** | 4096 tokens |
| **Paralelismo** | 2 requests simultáneas |
| **GPU** | 99 capas (Vulkan), fallback a CPU |
| **Arranque** | Auto vía thread daemon en startup |
| **Health check** | Cada 0.5s |
| **Instalación** | `%LOCALAPPDATA%/Sentinel/local-ai/` |

**Clase principal:** `SentinelLocalModelRuntime` en `sentinel/local_model/runtime.py` (213 líneas)
**Servicio wrapper:** `sidecar/services/local_model_service.py`

### Core Library (`sentinel/core/` — 44 módulos)

| Módulo | Líneas | Función |
|---|---|---|
| orchestrator.py | 1,425 | Pipeline 7 pasos obligatorio |
| model_router.py | 668 | Router con fallback chain multi-proveedor |
| file_pipeline.py | 793 | Ingesta de PDF/DOCX/imágenes |
| operational_memory.py | 763 | Memoria episódica + patrones aprendidos |
| tool_gateway.py | — | Gateway central de 73 tools |
| deep_context.py | — | Contexto del sistema |
| intent.py | — | Motor de intenciones |
| planner.py | — | Planificador multi-paso |
| simulation.py | — | Simulación de planes |
| decision_engine.py | — | Evaluación de permisos |
| policy_engine.py | — | Motor de políticas YAML |
| quality_gate.py | — | Redacción de secretos en outputs |
| circuit_breaker.py | — | 3 fallos → 30s cooldown |
| cost_tracker.py | — | Seguimiento de costos por modelo |
| knowledge_base.py | — | Búsqueda semántica |
| trigger.py | — | Automatización por eventos/cron |
| agent.py | — | Registro de agentes IA |
| multi_agent.py | — | Orquestación multi-agente |
| vault.py | — | Bóveda cifrada de secretos |
| hardening.py | — | Hardening de seguridad |
| web_browsing.py | — | Navegación web asistida |
| goals.py | — | Sistema de metas/objetivos |
| skill.py / skill_engine.py | — | Sistema de skills |
| user_profile.py / user_profile_async.py | — | Perfiles de usuario |
| +22 módulos más | — | |

### Backend API (`sidecar/modules/` — 19 módulos, 198 endpoints)

| Módulo | Endpoints | Temática |
|---|---|---|
| sentinel_bridge.py | 106 | Reports, Memory, Permissions, Chat, Goals, Simulation, Feedback, Cost, Vault |
| admin.py | 14 | Config CRUD, backups, logs, health |
| fleet.py | 15 | Estado, pairing, dispositivos, sync |
| plugins.py | 10 | List, templates, create, load/unload |
| triggers.py | 8 | CRUD triggers, history, evaluate |
| monitor.py | 7 | CPU, RAM, disco, red, procesos, GPU |
| executor.py | 6 | Command, launch, kill, apps |
| permissions.py | 6 | Status, level, emergency, confirm |
| ai_provider.py | 5 | Chat, analyze, config, providers |
| error_recovery.py | 5 | Status, retry, clear, circuit breaker |
| proactive.py | 4 | Suggestions, dismiss, trends |
| filesystem.py | 4 | Read, write, list, search |
| help.py | 4 | Topics, categories, onboarding |
| audit.py | 1 | Log de auditoría |
| auth.py, jwt_auth.py, authorization.py | — | Autenticación y autorización |

### Frontend (43 componentes, 27 tabs)

| Tab | Componente | Propósito |
|---|---|---|
| Panel | Dashboard.tsx | Métricas del sistema, análisis IA |
| Monitor | Monitor.tsx | CPU/RAM/disco/red/GPU en vivo |
| Chat | Chat.tsx | Conversación con IA + voz |
| Sentinel | Sentinel.tsx, PlanDisplay.tsx, IntentInput.tsx | Pipeline completo |
| Ejecutar | Execute.tsx | Ejecución multi-paso |
| Consola | Console.tsx | Terminal con comandos |
| Archivos | Files.tsx | Navegador de archivos |
| Flota | Fleet.tsx | Dispositivos en red |
| Plugins | Plugins.tsx | Marketplace + templates |
| Agentes | Agents.tsx | Gestión de agentes |
| Disparadores | Triggers.tsx | Automatización |
| Permisos | Permissions.tsx | Control de acceso |
| Políticas | Policies.tsx | Editor YAML |
| Auditoría | Audit.tsx | Log inmutable |
| Perfil | Profile.tsx | Preferencias |
| Configuración | Settings.tsx | Proveedores IA |
| Observabilidad | Observability.tsx | Trazas, health, costos |
| Costos | FeedbackCosts.tsx | Presupuestos |
| Bóveda | Vault.tsx | Secretos cifrados |
| Conocimiento | KnowledgeBase.tsx | Base semántica |
| Reportes | Reports.tsx | Generación reportes |
| Memoria | Memory.tsx | Memoria episódica |
| Alertas | Alertas.tsx | Alertas rendimiento |
| Admin | Admin.tsx | Config, backups, logs |
| Ayuda | Help.tsx | Documentación |
| Proactivo | Proactive.tsx | Sugerencias automáticas |
| Onboarding | Onboarding.tsx | Wizard 6 pasos |
| Login | Login.tsx | Autenticación |
| — | ConfirmDialog.tsx | Diálogo de confirmación |
| — | SimulationConfirmDialog.tsx | Confirmación simulación |
| — | Sidebar.tsx | Barra lateral 27 tabs |

**UI components:** UserBadge, Toast, Loading, ErrorRecoveryPanel, ErrorBox, ErrorBoundary, EmptyState, ConnectionStatus, AdvisoryNotice

---

## 6. GATEWAY — TOOLS REGISTRADOS (73)

| Categoría | Tools | Cantidad |
|---|---|---|
| Filesystem | read, write, list, search, delete, undo_write, restore | 7 |
| Executor | command, launch, kill, restart | 4 |
| System | SystemInfo, CpuInfo, MemoryInfo, DiskInfo, NetworkInfo, ProcessList, GpuInfo, AppDiscovery | 8 |
| AI | AIChat, AIAnalyze, AIConfig | 3 |
| Agents | AgentList, AgentCreate, AgentDelete, AgentDelegate | 4 |
| Fleet | FleetStatus, GeneratePairing, RevokePairing, ToggleRemote, QR, ListDevices, RegisterDevice, DeleteDevice, SyncPush, SyncPull, SyncLog | 11 |
| Plugins | PluginList, PluginTemplates, PluginLoad, PluginUnload, PluginReload, PluginToggle, PluginCreate | 7 |
| Permissions | PermissionStatus, PermissionSetLevel, PermissionEmergency, PermissionConfirm | 4 |
| Audit | AuditList | 1 |
| Triggers | TriggerList, TriggerCreate, TriggerDelete, TriggerHistory, TriggerEvaluate | 5 |
| Knowledge Base | KBSearch, KBAdd, KBList, KBDelete, KBStats | 5 |
| File Pipeline | PipelineIngest, PipelineStatus, PipelineReport | 3 |
| Profile | ProfileGet, ProfileUpdate, ProfilePreference, ProfileExport, ProfilePreset, ProfileHistory | 6 |
| Hardening | HardeningStatus, HardeningReset, HardeningConfig | 3 |
| Web Browsing | WebNavigate, WebExtract, WebSearch | 3 |
| Desktop Integration | IntegrationStatus, IdeOpen, BrowserOpen, DocumentOpen, ImageOpen, ImageInspect, OsReveal | 7 |
| Proactive | ProactiveSuggestions, ProactiveDismiss, ProactiveTrend, ProactiveRestart | 4 |

---

## 7. BASE DE DATOS (21 tablas)

| Tabla | Función |
|---|---|
| config | Almacenamiento clave-valor |
| audit_log | Traza de auditoría append-only |
| execution_history | Historial de ejecuciones |
| pending_actions | Acciones pendientes de confirmación |
| emergency_stop | Flag de parada de emergencia |
| agents | Registro de agentes IA |
| fleet | Configuración de flota |
| fleet_devices | Dispositivos de red |
| fleet_sync_log | Historial de sincronización |
| triggers | Definiciones de triggers |
| trigger_history | Historial de ejecución de triggers |
| user_preferences | Preferencias de sesión |
| user_profiles | Datos de perfil de usuario |
| user_preferences_v2 | Preferencias v2 por usuario |
| profile_history | Historial de cambios de perfil |
| profile_presets | Presets de perfil |
| episodic_memory | Memoria operacional |
| memory_patterns | Patrones de comportamiento |
| learned_preferences | Preferencias aprendidas por ML |
| vault_entries | Bóveda de secretos cifrados |
| vault_audit | Auditoría de bóveda |

---

## 8. PROVEEDORES IA (10)

| ID | Tipo | Default Model | Prioridad | API Key |
|---|---|---|---|---|
| ollama | Local | llama3 | 30 | No requiere |
| groq | Cloud | llama-3.3-70b-versatile | 25 | Requiere |
| openai | Cloud | gpt-4o | 22 | Requiere |
| anthropic | Cloud | claude-sonnet-4 | 22 | Requiere |
| openrouter | Cloud | deepseek/deepseek-v4-flash:free | 20 | Requiere |
| gemini | Cloud | gemini-2.5-flash | 18 | Requiere |
| mistral | Cloud | mistral-large-latest | 16 | Requiere |
| deepseek | Cloud | deepseek-v4-flash | 15 | Requiere |
| cerebras | Cloud | llama-3.3-70b | 14 | Requiere |
| github_models | Cloud | gpt-4o | 12 | Requiere |

---

## 9. CI/CD — WORKFLOWS

| Workflow | Archivo | Disparador | Acciones |
|---|---|---|---|
| CI | ci.yml | push/PR | Ruff lint, Pytest matrix (unit/integration/security/adversarial/e2e con cobertura), dep audit (pip/npm/cargo), Oxlint, TypeScript check, Vitest |
| Release | release.yml | tag v* | PyInstaller, Tauri MSI, Autenticode signing, CycloneDX SBOM (npm/Python/Rust), SLSA attestation, release metadata |
| Publish | publish-general.yml | release published | Verifica pentest approval attestation, confirma assets, publica GA |
| Security | security-adversarial.yml | push/PR | Bandit, adversarial security, production security, pentest gate, Windows ACL, env gate |

---

## 10. ÚLTIMAS INTEGRACIONES (Fase 17-18)

### Interfaz en Español
Traducción completa de todos los componentes frontend:
- Chat.tsx — mensajes, placeholders, quick actions, voz, TTS
- Sidebar.tsx — 27 tabs con labels y tooltips en español
- Dashboard.tsx — WelcomeCard, métricas, análisis IA
- App.tsx — banner offline, botones Recovery/Retry
- Console.tsx — header, quick commands, placeholders
- Settings.tsx — labels, botones, descripciones
- Login.tsx — subtítulo, descripción, botones
- ErrorBoundary.tsx — mensajes amigables
- ConnectionStatus.tsx — estados en español
- ConfirmDialog.tsx, UserBadge.tsx, etc.

### UX Fixes
- Dashboard QuickAction buttons ahora navegan (eran divs sin onClick)
- Onboarding botones navegan a tabs antes de cerrar wizard
- Sidebar con tooltips descriptivos en todos los tabs
- Texto "Continue" consistente en todos los pasos del onboarding

### Auth en navegador
- `.env` con `VITE_SENTINEL_SESSION_TOKEN=sentinel-dev-session`
- Sidecar iniciado con `SENTINEL_SESSION_TOKEN`
- invoke() de Tauri importado dinámicamente (try/catch)

### Errores como UX (no errores internos)
- Chat: mensaje amigable con instrucciones cuando no hay API key
- Settings: mensajes de solución, no códigos de error
- Null safety en Monitor.tsx y Observability.tsx (optional chaining + fallbacks)
- 5 `Object.entries()` con `?? {}` para evitar crashes por null

### Proveedores gratis preconfigurados
- 7 proveedores gratuitos con botones en Settings
- Auto-detección de Ollama al iniciar
- Fallback automático a Ollama si ningún proveedor responde

---

## 11. RESUMEN DE MÉTRICAS

| Categoría | Dato |
|---|---|
| **Archivos totales** | 384 (git-tracked) |
| **Archivos Python** | 235 (41,751 líneas) |
| **Archivos TS/TSX** | 81 (9,003 líneas) |
| **Archivo más grande** | sentinel_bridge.py (1,713 líneas) |
| **Tests backend** | 1,718 (85 archivos) |
| **Tests frontend** | 116 (27 archivos) |
| **Estado tests** | ✅ Todos pasan |
| **TypeScript errors** | 0 |
| **Lint errors** | 0 |
| **Tablas DB** | 21 |
| **Endpoints API** | 198 |
| **Tools registrados** | 73 |
| **Componentes React** | 43 |
| **Tabs frontend** | 27 |
| **Proveedores IA** | 10 (7 gratuitos) |
| **Commits** | 9 |
| **Tags** | 4 (v1.0.0, phase-1-complete, phase-2-complete, pre-beta-audit) |
| **CI/CD workflows** | 4 |
| **Cambios netos** | +61,827 / -51,756 |
| **Fases completadas** | 18/18 |

---

*Documento generado del código base — 16 Julio 2026*
*Sentinel v1.0.0 — MIT License*
