# INFORME EJECUTIVO — SENTINEL v1.0.0

> Trust Layer para orquestación de IA en el sistema operativo
> Fecha: Julio 2026 | Versión: 1.0.0 | Release: Production-ready

---

## 1. VISIÓN DEL PRODUCTO

### Misión
Ser la capa de confianza que permite a cualquier agente de IA interactuar con el sistema operativo de forma **segura, auditable y controlable**, eliminando el riesgo de ejecución no supervisada.

### Visión
Un mundo donde cualquier persona pueda delegar tareas a la IA con total confianza, sabiendo que cada acción está protegida por políticas, auditorías y controles de seguridad — sin sacrificar la libertad de ejecución.

### Propósito
Sentinel resuelve el problema fundamental de la interacción IA-SO: **¿cómo le das a un modelo de lenguaje la capacidad de ejecutar comandos, leer archivos y modificar configuración sin que sea un riesgo de seguridad?**

La respuesta es un pipeline de 7 pasos obligatorio, políticas en YAML con recarga en caliente, circuit breakers, y un gateway central que intercepta, evalúa y audita cada operación.

### Valor Diferencial

| Dimensión | Sentinel | Alternativas (Ejecución directa) |
|---|---|---|
| Seguridad | Pipeline obligatorio, políticas YAML, redacción de secretos | Sin control, acceso total a sistema |
| Auditoría | Append-only, inmutable, trazabilidad completa | Sin registro |
| Extremo a extremo | Frontend + Backend + Tauri + Instalador MSI | APIs sueltas, sin UI |
| Multi-proveedor | OpenRouter, OpenAI, Anthropic, Ollama, Groq, Gemini y más | Proveedor único |
| Local/Cloud | Híbrido: Ollama local + Cloud providers | Sólo cloud o sólo local |
| Costo | Modelos gratuitos preconfigurados (7 proveedores free) | Sin opciones free |
| Despliegue | Docker, MSI Windows, PyInstaller | Sólo código fuente |

---

## 2. ARQUITECTURA DEL PRODUCTO

### 2.1 Diagrama de Alto Nivel

```
┌──────────────────────────────────────────────────────────┐
│                     FRONTEND (Tauri + React 19)           │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬────┐ │
│  │Dashboard│Monitor│ Chat │Execute│Console│Files │Admin│...│ │ 27 tabs
│  └──────┴──────┴──────┴──────┴──────┴──────┴──────┴────┘ │
│                     ↓ HTTP REST (port 8765)               │
├──────────────────────────────────────────────────────────┤
│                  BACKEND (FastAPI + Python 3.12)           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │            PIPELINE OBLIGATORIO (7 pasos)            │ │
│  │  DeepContext → Intent → Planner → Simulation →      │ │
│  │  Decision → Policy → ToolGateway → Audit            │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌──────┬──────┬──────┬──────┬──────┬──────┬───────────┐ │
│  │Fleet │Plugins│Trigger│ Proact. │Admin │ErroRecov│Vault │ │
│  └──────┴──────┴──────┴──────┴──────┴──────┴───────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │          SQLite WAL-mode (21 tablas)                 │ │
│  └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│           CAPA IA (ModelRouter + Smart Strategy)          │
│  Ollama(30) ← Groq(25) ← OpenAI(22) ← Anthropic(22)     │
│  ← OpenRouter(20) ← Gemini(18) ← Mistral(16) ...         │
├──────────────────────────────────────────────────────────┤
│                 CI/CD + RELEASE ENGINE                    │
│  GitHub Actions → Ruff/Oxlint → PyTest/Vitest →          │
│  PyInstaller → Tauri → Autenticode → SBOM → SLSA        │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Pipeline de Ejecución (7 pasos obligatorios)

Cada tool execution pasa por este pipeline sin excepción:

| Paso | Componente | Función |
|---|---|---|
| 1 | **DeepContextEngine** | Recolecta contexto del sistema: CPU, RAM, batería, procesos, apps abiertas, dispositivos fleet |
| 2 | **IntentEngine** | Analiza la intención del usuario, extrae objetivos y parámetros |
| 3 | **Planner** | Genera un plan multi-paso con capacidades registradas |
| 4 | **SimulationEngine** | Simula el plan contra el contexto actual, detecta conflictos y bloqueos |
| 5 | **DecisionEngine** | Evalúa nivel de permiso requerido, solicita confirmación si es necesario |
| 6 | **PolicyEngine** | Aplica políticas YAML: patrones destructivos, niveles de acceso, emergency stop |
| 7 | **ToolGateway** | Ejecuta el tool, redacta secretos del output, registra en auditoría |

**Rollback automático**: Si cualquier paso falla, `RollbackManager` revierte los pasos anteriores.

### 2.3 Stack Tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| **Frontend** | React + TypeScript + Vite | React 19.2 / TS 6.0 / Vite 8.1 |
| **Desktop Shell** | Tauri | 2.x |
| **Backend** | Python + FastAPI + Uvicorn | Python 3.12 / FastAPI |
| **Base de datos** | SQLite con WAL-mode, aiosqlite async | — |
| **IA Router** | OpenAI-compatible (multi-provider) | — |
| **Testing Frontend** | Vitest + Testing Library + jsdom | Vitest 4.1 |
| **Testing Backend** | Pytest (5 categorías) | — |
| **Linting** | Ruff (Python) + Oxlint (JS/TS) | — |
| **Empaquetado** | PyInstaller (backend) + Tauri (frontend) | — |
| **CI/CD** | GitHub Actions (4 workflows) | — |
| **SBOM** | CycloneDX (npm + Python + Cargo) | — |
| **Firmado** | Autenticode + SLSA attestations | — |

---

## 3. INVENTARIO DE FUNCIONALIDADES

### 3.1 Proveedores de IA Soportados

| Proveedor | Tipo | Modelo Default | Prioridad | API Key |
|---|---|---|---|---|
| Ollama | Local (gratis) | llama3 | 30 (máx) | No necesita |
| Groq | Cloud (gratis) | llama-3.3-70b-versatile | 25 | Requiere |
| OpenAI | Cloud (pago) | gpt-4o | 22 | Requiere |
| Anthropic | Cloud (pago) | claude-sonnet-4 | 22 | Requiere |
| OpenRouter | Cloud (gratis) | deepseek/deepseek-v4-flash:free | 20 | Requiere |
| Gemini | Cloud (gratis) | gemini-2.5-flash | 18 | Requiere |
| Mistral | Cloud (gratis) | mistral-large-latest | 16 | Requiere |
| DeepSeek | Cloud (gratis) | deepseek-v4-flash | 15 | Requiere |
| Cerebras | Cloud (gratis) | llama-3.3-70b | 14 | Requiere |
| GitHub Models | Cloud (gratis) | gpt-4o | 12 | Requiere |

### 3.2 Tools del Gateway (73 tools registrados)

| Categoría | Tools | Propósito |
|---|---|---|
| **Filesystem** | 7 | Leer, escribir, listar, buscar, eliminar, restaurar archivos |
| **Executor** | 4 | Ejecutar comandos, lanzar/kill/reiniciar procesos |
| **System** | 8 | CPU, RAM, disco, red, procesos, GPU, apps, info sistema |
| **AI** | 3 | Chat, analizar, configurar proveedores IA |
| **Agents** | 4 | Listar, crear, eliminar, delegar agentes |
| **Fleet** | 11 | Estado, pairing, QR, dispositivos, sync push/pull/log |
| **Plugins** | 7 | Listar templates, cargar/descargar, toggle, crear plugins |
| **Permissions** | 4 | Estado, nivel, emergency stop, confirmar acción |
| **Audit** | 1 | Log de auditoría |
| **Triggers** | 5 | CRUD triggers, historial, evaluar |
| **Knowledge Base** | 5 | Buscar, agregar, listar, eliminar conocimiento, estadísticas |
| **File Pipeline** | 3 | Ingestar PDF/DOCX/imágenes, estado, reporte |
| **Profile** | 6 | Obtener/actualizar perfil, preferencias, exportar, presets |
| **Hardening** | 3 | Estado, reset, configurar hardening |
| **Web Browsing** | 3 | Navegar, extraer contenido, buscar en web |
| **Desktop Integration** | 7 | Estado integración, abrir IDE/edge/documento/imagen |
| **Proactive** | 4 | Sugerencias, descartar, tendencias, reiniciar engine |

### 3.3 Base de Datos (21 tablas)

| Grupo | Tablas | Propósito |
|---|---|---|
| **Config** | config | Almacenamiento clave-valor |
| **Audit** | audit_log | Traza de auditoría append-only |
| **Ejecución** | execution_history, pending_actions | Historial y acciones pendientes |
| **Seguridad** | emergency_stop, vault_entries, vault_audit | Emergency stop y bóveda cifrada |
| **Agentes** | agents | Registro de agentes |
| **Fleet** | fleet_devices, fleet_sync_log | Dispositivos en red |
| **Triggers** | triggers, trigger_history | Automatización programada |
| **Perfil** | user_profiles, user_preferences, profile_history, profile_presets | Perfiles de usuario |
| **Memoria** | episodic_memory, memory_patterns, learned_preferences | Memoria operacional |
| **Feedback** | (vía api) | Costos, feedback, rendimiento |

### 3.4 API REST (195 endpoints)

| Módulo | Endpoints | Prefijo |
|---|---|---|
| sentinel_bridge | 106 | /api/* |
| fleet | 15 | /api/fleet/* |
| admin | 14 | /api/admin/* |
| plugins | 10 | /api/plugins/* |
| triggers | 8 | /api/triggers/* |
| monitor | 7 | /api/monitor/* |
| permissions | 6 | /api/permissions/* |
| executor | 6 | /api/executor/* |
| error_recovery | 5 | /api/recovery/* |
| ai_provider | 5 | /api/ai/* |
| proactive | 4 | /api/proactive/* |
| filesystem | 4 | /api/filesystem/* |
| help | 4 | /api/help/* |
| audit | 1 | /api/audit/* |
| **Total** | **195** | |

### 3.5 Frontend (27 tabs + 42 componentes)

| Tab | Ruta | Propósito |
|---|---|---|
| Panel | / | Dashboard, métricas, análisis IA |
| Monitor | /monitor | CPU, RAM, disco, red, GPU en tiempo real |
| Chat | /chat | Conversación con IA, quick actions, voz, TTS |
| Sentinel | /sentinel | Pipeline completo: intent, plan, simulación, decisión |
| Ejecutar | /execute | Ejecución directa con plan multi-paso |
| Consola | /console | Terminal con comandos rápidos |
| Archivos | /files | Navegador de archivos |
| Flota | /fleet | Dispositivos en red, pairing, sync |
| Plugins | /plugins | Marketplace, templates, carga de plugins |
| Agentes | /agents | Gestión de agentes IA |
| Disparadores | /triggers | Automatización por tiempo/eventos/webhook |
| Permisos | /permissions | Niveles, reglas, emergency stop |
| Políticas | /policies | Editor de políticas YAML |
| Auditoría | /audit | Log de auditoría |
| Perfil | /profile | Preferencias y perfil de usuario |
| Configuración | /settings | Proveedor IA, API keys, actualizaciones |
| Observabilidad | /observability | Trazas, health, costos, feedback |
| Costos | /feedback-costs | Presupuestos, límites, análisis costos |
| Bóveda | /vault | Secretos cifrados |
| Conocimiento | /knowledge | Base de conocimiento semántico |
| Reportes | /reports | Generación de reportes |
| Memoria | /memory | Memoria episódica y patrones |
| Alertas | /alertas | Alertas de rendimiento, costos, dispositivos |
| Admin | /admin | Config, backups, logs, health |
| Ayuda | /help | 14 tópicos de documentación |
| Proactivo | /proactive | Sugerencias automáticas del sistema |
| Onboarding | (modal) | Wizard de 6 pasos para nuevos usuarios |

---

## 4. MÉTRICAS DEL PROYECTO

### 4.1 Tamaño del Código Base

| Métrica | Valor |
|---|---|
| Archivos Python (sidecar/) | 147 |
| Archivos TypeScript/TSX (src/) | 78 |
| Componentes React | 42 |
| Archivo más grande (Python) | sentinel_bridge.py — 1,630 líneas |
| Archivo más grande (TS) | types.ts — 729 líneas |
| Líneas de especificación PyInstaller | 229 líneas |
| Archivo de rutas API | api.ts — 412 líneas |

### 4.2 Tests

| Categoría | Tests | Estado |
|---|---|---|
| Frontend (Vitest) | 116 tests en 27 archivos | ✅ 100% passing |
| Backend (Pytest) | 1,693+ tests en 83 archivos | ✅ 100% passing |
| TypeScript | Compilación —noEmit | ✅ 0 errores |
| Lint Python (Ruff) | E, F, W, S | ✅ 0 errores |
| Lint JS/TS (Oxlint) | — | ✅ 0 errores, 8 warnings |

**Categorías de tests backend:**
- Unitarios
- Integración
- Seguridad
- Adversarial
- End-to-End (pipeline completo)
- Benchmarks
- Release contract (9 gates)

### 4.3 Renderizado del Pipeline

```
DeepContext → Intent → Planner → Simulation → Decision → Policy → Gateway → Audit
     ↓           ↓         ↓           ↓           ↓         ↓         ↓       ↓
  Sistema    Intención  Plan multi- Simulación  Nivel     YAML     Tool +    Log
  + apps     del user   paso        virtual     permiso   Policies  Quality   inmutable
```

### 4.4 Cobertura de Funcionalidades por Fase

| Fase | Funcionalidad | Estado |
|---|---|---|
| 1 | Pipeline Obligatorio (7 pasos) | ✅ |
| 2 | Quality Gate (redacción de secretos) | ✅ |
| 3 | YAML Policies con Hot Reload | ✅ |
| 4 | SQLite Unificación (WAL-mode) | ✅ |
| 5 | API v1 con OpenAPI | ✅ |
| 6 | Security Hardening | ✅ |
| 7 | Fleet Multi-Device | ✅ |
| 8 | Plugin System | ✅ |
| 9 | Triggers & Automation | ✅ |
| 10 | Observabilidad & Monitoreo | ✅ |
| 11 | Knowledge & Memory | ✅ |
| 12 | Admin UI | ✅ |
| 13 | Documentación y Onboarding | ✅ |
| 14 | Error Recovery UX | ✅ |
| 15 | Proactive Engine (pasivo) | ✅ |
| 16 | CI/CD & Release Pipeline | ✅ |
| 17 | Frontend UX, Traducción Español | ✅ |
| 18 | Release v1.0.0 | ✅ |

---

## 5. SEGURIDAD Y CUMPLIMIENTO

### 5.1 Capas de Seguridad

| Capa | Mecanismo |
|---|---|
| **Autenticación** | SENTINEL_SESSION_TOKEN + JWT bearer |
| **Autorización** | Policy Engine con YAML policies |
| **Rate Limiting** | RateLimiter por tool + global |
| **Circuit Breaker** | 3 fallos consecutivos → 30s cooldown |
| **Emergency Stop** | Kill switch global desde UI o API |
| **Redacción** | Quality Gate: API keys, tokens, secrets en outputs |
| **Input Validation** | PathGuardian, prevención path traversal |
| **Windows ACL** | Control de acceso a nivel OS |
| **Pentest Gate** | Suite de pruebas adversariales |
| **Vault** | Bóveda cifrada para secretos |
| **Offline Queue** | Cola de operaciones en modo offline |
| **Contenido** | ContentSecurityPolicy headers |

### 5.2 Políticas YAML (Cargadas en caliente)

Las políticas se definen en YAML y se recargan sin reiniciar:

```yaml
security:
  identity_permissions:     # Permisos por identidad
  permission_level:         # Nivel de permiso (allow/confirm/deny)
  granular_permissions:     # Permisos por tool específico
  emergency_stop:           # Parada de emergencia
destructive_patterns:       # Patrones destructivos bloqueados
```

### 5.3 Auditoría

- Append-only: los registros de auditoría no se pueden modificar ni eliminar
- Traza completa: cada ejecución registra usuario, tool, input, output, timestamp
- Consultable vía API y UI de Auditoría

---

## 6. DESPLIEGUE Y DISTRIBUCIÓN

### 6.1 Canales de Distribución

| Canal | Formato | Plataforma |
|---|---|---|
| **Docker** | ghcr.io/anomalyco/sentinel:latest | Linux/Windows/Mac |
| **Windows Installer** | MSI firmado Authenticode | Windows 10/11 |
| **Código fuente** | GitHub Releases | Multi-plataforma |

### 6.2 CI/CD Pipeline

```
                    ┌──────────────┐
                    │   git push   │
                    └──────┬───────┘
                           ↓
              ┌────────────────────────┐
              │    CI (ci.yml)         │
              │  • Ruff lint           │
              │  • Pytest matrix       │
              │  • Oxlint              │
              │  • TypeScript check    │
              │  • Vitest              │
              │  • Dep audit           │
              └───────────┬────────────┘
                          ↓ (tag v*)
              ┌────────────────────────┐
              │  Release (release.yml) │
              │  • PyInstaller bundle  │
              │  • Tauri MSI build     │
              │  • Autenticode signing │
              │  • SBOM (npm/Python)   │
              │  • SLSA attestations   │
              │  • Release contract    │
              │    tests (9 gates)     │
              │  • GitHub Release      │
              └───────────┬────────────┘
                          ↓ (draft)
              ┌────────────────────────┐
              │ Publish (publish.yml)  │
              │  • Verify pentest      │
              │  • Verify attestation  │
              │  • Publish GA release  │
              └────────────────────────┘
```

### 6.3 Release Gates (Contract Tests)

| Gate | Verificación |
|---|---|
| 1 | Versión semántica válida |
| 2 | API responde health check |
| 3 | Pipeline ejecuta plan completo |
| 4 | SQLite WAL-mode activo |
| 5 | JWT auth funcional |
| 6 | Calidad de código Ruff |
| 7 | Políticas YAML cargadas |
| 8 | Auditoría append-only |
| 9 | ModelRouter multi-proveedor |

---

## 7. MODELO DE NEGOCIO Y SOSTENIBILIDAD

### 7.1 Estrategia de Monetización

| Modelo | Descripción | Estado |
|---|---|---|
| **Open Source (MIT)** | Núcleo gratuito, código abierto | ✅ Activo |
| **Modelos gratuitos** | 7 proveedores free preconfigurados | ✅ Activo |
| **Ollama (local)** | 100% local, sin internet, sin costo | ✅ Activo |
| **Proveedores cloud** | OpenAI, Anthropic (pago) + 5 free | ✅ Activo |

### 7.2 Diferenciación Competitiva

- **Única capa de confianza** con pipeline obligatorio de 7 pasos para IA-SO
- **Multi-proveedor** con fallback automático y circuit breaker
- **Políticas como código** en YAML con recarga en caliente
- **Híbrido local/cloud**: sin dependencia de internet gracias a Ollama
- **Auditoría forense**: append-only, trazabilidad completa
- **Despliegue profesional**: MSI firmado, SBOM, SLSA, Docker

---

## 8. MÉTRICAS CLAVE (KPIs)

| KPI | Valor Actual | Objetivo |
|---|---|---|
| Tests frontend | 116 ✅ | Mantener ≥100 |
| Tests backend | 1,693+ ✅ | Mantener ≥1,500 |
| Cobertura de funcionalidades (18 fases) | 100% | 100% |
| Proveedores IA soportados | 10 | 10+ |
| Tools registrados en gateway | 73 | Escalable vía plugins |
| Tabs frontend | 27 | — |
| Tiempo de respuesta backend | <100ms (local) | <200ms |
| Errores TypeScript | 0 | 0 |
| Errores Lint | 0 | 0 |

---

## 9. CONCLUSIÓN

Sentinel v1.0.0 es un producto **production-ready** que resuelve un problema fundamental en la interacción IA-SO: la seguridad y control de ejecución. Con un pipeline obligatorio de 7 pasos, 73 tools registrados, 195 endpoints API, 27 tabs de interfaz, 10 proveedores de IA (7 gratuitos), y un sistema completo de CI/CD con SBOM, firmado Authenticode y attestations SLSA, el producto está listo para despliegue empresarial y uso individual.

**Próximos pasos recomendados:**
1. Campaña de adopción Open Source
2. Documentación avanzada para desarrolladores de plugins
3. Marketplace público de plugins
4. Versión para macOS y Linux
5. Dashboard analítico para administradores fleet
6. Integración con asistentes empresariales (Microsoft Copilot, Google Gemini)
7. Programa de bug bounty / seguridad

---

*Documento generado a partir del código base — Julio 2026*
*AIVO / Sentinel v1.0.0 — MIT License*
