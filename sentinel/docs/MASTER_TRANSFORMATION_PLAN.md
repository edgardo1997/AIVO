# SENTINEL — MASTER PRODUCT TRANSFORMATION PLAN

**De prototipo a producto comercial**

*Documento oficial de transformación. Versión 1.0*
*Equipo: CTO / Arquitecto / Security Engineer / PM / Founder*

---

# PARTE 1 — DIAGNÓSTICO ACTUAL

## 1.1 Qué es Sentinel HOY

Sentinel es actualmente un **prototipo funcional con una crisis de identidad.**

Técnicamente, es una aplicación Python+React+Tauri que:

- Expone 11 APIs REST para monitoreo, ejecución, archivos, chat, permisos, auditoría, proactive, plugins, voz, fleet, y un pipeline de seguridad llamado "Sentinel"
- Tiene un pipeline semilla (Intent → Decision → Policy → Gateway → Execution → Audit) que funciona correctamente para una ruta específica
- Tiene bypasses documentados que permiten ejecutar comandos sin pasar por ese pipeline
- Almacena datos en SQLite, JSON, y diccionarios en memoria simultáneamente
- Define las mismas constantes de seguridad en 3 archivos diferentes

Conceptualmente, es un **híbrido** que no ha decidido qué quiere ser:

| Dimensión | Lo que parece | Lo que tiene |
|-----------|--------------|--------------|
| UI principal | Dashboard con monitoreo | Gráficas CPU/RAM/Disk |
| Interacción | Chat | Caja de texto + historial |
| Propuesta de valor | Seguridad para IA | Pipeline Intent→Decision→Policy |
| Funcionalidad | Automatización | Botones "Clean Disk", "Open Terminal" |
| Diferenciación | No clara | Podría ser Trust Layer pero nadie lo sabe |

## 1.2 Qué debería ser

Sentinel debería ser **la capa de confianza entre cualquier agente de IA y cualquier sistema operativo.**

Su identidad completa:

```
No es una herramienta.
No es un dashboard.
No es un chatbot.

Es una CAPA. 
Una capa que se inserta entre la IA y el sistema.
Invisible cuando todo está bien.
Imposible de evadir cuando algo va mal.
```

El producto debería tener:

- **Un pipeline de seguridad obligatorio** — sin excepciones, sin bypasses, sin modos "solo testing"
- **Una identidad canónica** — toda acción es rastreable a un agente/usuario específico
- **Un audit trail inmutable** — toda acción queda registrada con contexto completo
- **Políticas configurables** — no código, sino archivos YAML que cualquier organización puede modificar
- **Zero configuración para lo básico** — install y funciona con defaults seguros

## 1.3 Diferencia entre ambos

| Dimensión | Estado actual | Estado deseado |
|-----------|--------------|----------------|
| Identidad | Confusa (dashboard + chat + trust layer) | Clara (trust layer) |
| Pipeline | Opcional (solo ruta Sentinel) | Obligatorio (cualquier acción) |
| Bypasses | Múltiples y conocidos | Cero |
| Políticas | Hardcodeadas en Python | Configurables en YAML |
| Auditoría | Fragmentada (3 sistemas) | Unificada e inmutable |
| UI | 11 tabs funcionales | 3 pantallas enfocadas |
| Instalación | pip + npm + Rust | Docker / MSI |
| Documentación | Inexistente | Manual de producto + API |
| Seguridad | Inmadura (AIVO_TESTING, bypasses) | Auditable, certificable |
| Posicionamiento "rueda de prensa" | "Es un panel de control con IA" | "Es la capa de confianza para agentes de IA" |

## 1.4 Errores arquitectónicos

1. **Service Locator anti-patrón.** `modules/__init__.py` actúa como registro global de servicios. Oculta dependencias, impide testing aislado, crea singletons mutables.

2. **Dual service layer.** `sentinel/adapters/` y `sidecar/services/` implementan la misma lógica con interfaces diferentes. Los adapters son wrappers que no agregan valor real.

3. **Identity fragmentada.** `AuthContext` y `IdentityContext` coexisten. Ninguno es canónico.

4. **Políticas hardcodeadas.** `modules/__init__.py:68-99` define el mapeo permisos→herramientas en código Python, no en configuración.

5. **Tres sistemas de auditoría.** `operational_memory.py`, `audit_service.py`, y `service._log_action()` son tres implementaciones diferentes de "registrar lo que pasó."

6. **Estado global mutable.** `PENDING_ACTIONS` y `EMERGENCY_STOP` son diccionarios globales compartidos entre 3 módulos sin coordinación.

7. **No hay Quality Gate.** El pipeline termina en Execution. No hay validación de salida.

8. **No hay versión de API.** Todas las rutas son `/api/*` sin prefijo de versión.

## 1.5 Errores de producto

1. **Identidad dividida.** Dashboard, Chat, y Sentinel coexisten en la misma interfaz. Un visitante nuevo no sabe qué está viendo.

2. **Las acciones rápidas contradicen el producto.** Botones de "Clean Disk" y "Open Terminal" que bypassan el pipeline de seguridad envían el mensaje: "la seguridad es opcional."

3. **Sin caso de uso claro.** "¿Para qué instalo Sentinel?" no tiene respuesta de 10 segundos.

4. **Chat UI confunde.** Una caja de chat sugiere "soy un chatbot." Sentinel no es un chatbot.

5. **Monitoreo distrae.** Las gráficas de CPU/RAM son el feature más visible pero el menos diferencial.

6. **Voice, Fleet, Proactive** son features sin mercado validado que consumen atención de desarrollo.

## 1.6 Riesgos comerciales

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Competidores (OpenAI, Anthropic) implementan seguridad similar | Alta | Medio | Diferenciación: agnóstico a proveedor, open core, policy configurable |
| Mercado demasiado temprano (pocos usan agentes IA en producción) | Media | Alto | Apuntar a early adopters, construir comunidad, ser referencia |
| Proyecto muere por falta de foco | Alta | Alto | Este documento. Decisión clara de identidad. |
| Brecha de seguridad en el producto destruye confianza | Baja | Crítico | Security-first architecture, audit externo antes de 1.0 |
| Confusión de producto (nadie entiende qué es) | Alta | Alto | Posicionamiento claro, documentación, caso de uso concreto |
| No encontrar PMF (product-market fit) | Media | Crítico | Beta con 10 empresas antes de 1.0, iterar rápido |

---

# PARTE 2 — NUEVA ARQUITECTURA OBJETIVO

## 2.1 Visión arquitectónica de Sentinel 1.0

```
 ┌─────────────────────────────────────────────────────┐
 │                    AI AGENT                          │
 │  (Claude Code, Copilot, OpenCode, personalizado)    │
 └─────────────────────┬───────────────────────────────┘
                       │  HTTP/gRPC
                       ▼
 ┌─────────────────────────────────────────────────────┐
 │              SENTINEL API GATEWAY                     │
 │  /v1/execute  /v1/policies  /v1/audit  /v1/identity │
 │  Rate limiting · Auth · TLS · Request validation     │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             1. IDENTITY LAYER                         │
 │  ¿Quién solicita?  →  Agent ID + Human ID + Level   │
 │  Autenticación · Autorización · Contexto de identidad│
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             2. INTENT ENGINE                          │
 │  ¿Qué solicita?  →  Action + Target + Parameters    │
 │  Parseo · Extracción · Clasificación                 │
 │  Si confianza < umbral → REJECT                     │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             3. CONTEXT ENGINE                         │
 │  ¿En qué estado está el sistema?                     │
 │  CPU · RAM · Disk · Procesos · Hora · Usuario activo│
 │  Proporciona factores para risk scoring              │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             4. DECISION ENGINE                        │
 │  ¿Qué tan riesgoso es?  →  Risk Score (0.0 - 1.0)   │
 │  Riesgo base + modificadores de contexto             │
 │  Output: risk_score + factores                       │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             5. POLICY ENGINE                          │
 │  ¿Está permitido?  →  ALLOW / DENY / CONFIRM / MODIFY│
 │  Lee políticas desde Policy Store (YAML)             │
 │  Contraste: risk_score + permission_level → veredicto│
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             6. TOOL GATEWAY                           │
 │  Ejecutar el veredicto. Enrutar a la herramienta.   │
 │  Si DENY → return block.  Si CONFIRM → pendiente.   │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             7. EXECUTION LAYER                        │
 │  Herramientas: executor, filesystem, system, etc.   │
 │  Validación de parámetros · Timeout · Sandboxing    │
 │  Ejecución con menor privilegio posible              │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             8. QUALITY GATE                           │
 │  Validar output antes de devolverlo                  │
 │  Sensitive data detection · Size limits · Sanitize  │
 │  Si falla → OUTPUT_REDACTED + log de alerta         │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
 ┌─────────────────────────────────────────────────────┐
 │             9. AUDIT LAYER                            │
 │  Registrar TODO de forma inmutable                   │
 │  identity + intent + decision + policy + execution   │
 │  + output + quality_verdict                          │
 │  Store: append-only log (local SQLite + stream)      │
 └──────────┬──────────────────────────────────────────┘
            │
            ▼
      Response al agente AI
      (resultado + metadatos + execution_id)
```

## 2.2 Componentes y responsabilidades

### Core Pipeline (8 capas, obligatorias)

| Capa | Responsabilidad | Entrada | Salida | ¿Configurable? |
|------|----------------|---------|--------|----------------|
| Identity | Autenticar y autorizar al agente | Request + credentials | IdentityContext | No (infraestructura) |
| Intent | Comprender la acción solicitada | Utterance + context | Intent (action/target/params) | Sí (intents personalizados) |
| Context | Estado del sistema para decisiones | Sistema operativo | ContextFactors (CPU, RAM, etc.) | Sí (qué factores incluir) |
| Decision | Calcular riesgo de la acción | Intent + Context | RiskScore (0.0-1.0) + factors | Sí (thresholds) |
| Policy | Aplicar reglas del usuario | RiskScore + Identity | Veredicto (ALLOW/DENY/CONFIRM) | Sí (YAML policies) |
| Gateway | Punto de enforcement | Veredicto + Intent | Execute() o DENY | No (punto fijo) |
| Execution | Ejecutar la acción de forma segura | Tool + params | ToolResult | Sí (timeouts, límites) |
| Quality | Validar output | ToolResult | ToolResult (sanitizado) | Sí (reglas de output) |
| Audit | Registrar todo | Todo lo anterior | AuditRecord | No (siempre se registra) |

### Componentes de soporte

| Componente | Responsabilidad | ¿Core? |
|------------|----------------|--------|
| Policy Store | Almacenar políticas en YAML versionados | ✅ Core |
| Audit Store | Almacenamiento append-only de registros | ✅ Core |
| Tool Registry | Registro de herramientas disponibles | ✅ Core |
| Identity Store | Agentes + usuarios registrados | ✅ Core |
| Policy Compiler | Validar YAML → PolicyEngine | ✅ Core |
| Health Monitor | /health, /ready, /metrics | ✅ Core |

### Módulos opcionales (plugables)

| Módulo | Responsabilidad | ¿Cuándo activar? |
|--------|----------------|-------------------|
| Monitor | Colección de métricas del sistema | Por defecto (contexto para Decision) |
| Plugins | Políticas personalizadas | Enterprise |
| Fleet | Gestión remota de políticas | Enterprise |
| Notifications | Slack, Teams, email en eventos | Enterprise |
| SIEM Export | Streaming de audit a Splunk/ELK | Enterprise |

## 2.3 Dependencias y límites

### Reglas de dependencia (estrictas)

```
Identity  →  Intent    (identity fluye hacia abajo, nunca hacia arriba)
Intent    →  Decision  (decision necesita intent)
Context   →  Decision  (decision necesita contexto)
Decision  →  Policy    (policy necesita risk score)
Policy    →  Gateway   (gateway ejecuta veredicto)
Gateway   →  Execution (gateway llama a execution)
Execution →  Quality   (quality valida output)
TODAS     →  Audit     (todas escriben en audit, audit no depende de ninguna)
```

### Lo que NUNCA debe ocurrir

- Execution NO conoce Intent (al ejecutar no necesita saber por qué)
- Policy NO conoce herramientas específicas (la política es abstracta)
- Quality NO conoce Identity (quality valida contenido, no quién)
- Audit NO filtra por política (todo se registra)
- Gateway NO re-evalúa decisiones (solo ejecuta el veredicto)

## 2.4 Almacenamiento

### Sentinel 1.0

```
Base de datos única: SQLite
Archivo: ~/.sentinel/sentinel.db

Tablas:
- agents              (identidad de agentes registrados)
- audit_log           (registro append-only de ejecuciones)  
- policies            (políticas activas, cache desde YAML)
- operational_state   (emergency_stop, current_level, etc.)
- schema_version      (para migraciones futuras)
```

Almacenamiento adicional:
- `~/.sentinel/policies/` — Directorio con archivos YAML de políticas
- `~/.sentinel/config.yaml` — Configuración general

### Enterprise (futuro)

- PostgreSQL como backend alternativo
- Audit streaming a SIEM vía stdout o TCP
- Políticas distribuidas desde servidor central

## 2.5 APIs

### Sentinel API v1

```
POST /v1/execute          → Pipeline completo
GET  /v1/execute/:id      → Resultado de ejecución previa

GET  /v1/policies         → Listar políticas
POST /v1/policies         → Crear/actualizar política
DELETE /v1/policies/:name → Eliminar política

GET  /v1/audit            → Query audit log (filtros: agent, action, status, desde, hasta)

POST /v1/agents           → Registrar agente AI
GET  /v1/agents           → Listar agentes
DELETE /v1/agents/:id     → Eliminar agente

GET  /v1/health           → Health check
GET  /v1/ready            → Readiness check
GET  /v1/metrics          → Prometheus metrics
```

No hay:
- `/api/monitor/cpu` (eso es contexto, no API pública)
- `/api/ai/chat` (eso es el modelo, no Sentinel)
- `/api/voice/*` (no pertenece)
- `/api/fleet/*` (enterprise, no API pública base)

## 2.6 Seguridad

### Zero Trust para agentes de IA

Cada ejecución es independientemente evaluada. No hay "sesión de confianza."

```
Principios:
- No asumir que la misma IA no hará algo diferente en el próximo request
- No asumir que el contexto del sistema es el mismo que hace 5 segundos
- No asumir que el agente autenticado no está comprometido
- Cada request es inspeccionado como si fuera el primero y el único
```

### Defense in depth

```
Capa 1: API Gateway (TLS, rate limiting, auth)
Capa 2: Identity (autenticación del agente)
Capa 3: Intent validation (¿es una acción válida?)
Capa 4: Decision (risk scoring basado en contexto actual)
Capa 5: Policy (reglas del usuario)
Capa 6: Execution validation (path traversal, timeouts, comandos prohibidos)
Capa 7: Quality Gate (output sanitization)
Capa 8: Audit (detección de anomalías post-hoc)
```

---

# PARTE 3 — DIVISIÓN POR FASES

## FASE -1: Fundación del producto

**Objetivo:** Definir QUÉ es Sentinel antes de escribir código.

**Razón:** Todas las fases siguientes dependen de tener una identidad clara. Sin esta fase, repetiremos los errores del prototipo actual.

**Entregables:**
- Constitución de Sentinel (versión final, firmada por el equipo)
- Documento "Qué es / Qué no es Sentinel"
- Perfil de cliente ideal (ICP) documentado
- Decisión sobre modelo de negocio (Open Core + Enterprise)
- Roadmap conceptual aprobado

**Archivos afectados:** Ninguno (documentos)
**Riesgo:** Bajo — solo definición
**Criterio de finalización:** Toda decisión de identidad está tomada y documentada. No hay ambigüedad.

---

## FASE 0: Congelación y auditoría

**Objetivo:** Establecer línea base del código actual y medir la deuda.

**Razón:** No se puede transformar lo que no se entiende.

**Entregables:**

1. `git tag pre-transformation` en el estado actual
2. Mapa completo de todas las rutas de ejecución (como se hizo en el architectural reasoning report)
3. Inventario de bypasses de seguridad
4. Inventario de código muerto
5. Inventario de dependencias circulares
6. Métricas base: líneas de código por módulo, cobertura de tests, tiempo de tests
7. Backups de bases de datos SQLite y JSON

**Archivos afectados:** Ninguno (solo análisis)
**Riesgo:** Bajo
**Criterio de finalización:** Auditoría completa documentada y compartida con el equipo.

---

## FASE 1: Purificación quirúrgica

**Objetivo:** Eliminar todo lo que contradice la identidad de Trust Layer.

**Razón:** El código actual contiene módulos enteros que violan la Constitución. Mantenerlos es costoso y confuso. Hay que eliminarlos antes de construir sobre la base correcta.

**Acciones:**

| Acción | Archivos | Justificación |
|--------|----------|---------------|
| **Eliminar módulo Voice** | `sidecar/modules/voice.py`, `sidecar/services/voice_service.py`, referencias en `main.py:21` y `api.ts:51-54` | 0% relacionado con Trust Layer. Sin uso real. |
| **Deshabilitar Proactive Engine** | `sidecar/modules/proactive.py`, `sidecar/services/proactive_service.py` | Viola "Sentinel no inicia acciones." Deshabilitar por defecto. Mantener código para posible re-evaluación futura. |
| **Eliminar Dashboard quick actions** | `src/components/Dashboard/Dashboard.tsx:106-109` | Bypass crítico de seguridad. Los botones de "Clean Disk", "Open Terminal" ejecutan comandos sin pasar por pipeline. |
| **Eliminar/ocultar tab Chat** | `src/App.tsx:25`, `src/components/Chat/Chat.tsx` | Confunde posicionamiento. La interacción debe ser via Sentinel, no via Chat separado. |
| **Ocultar tab Fleet** | `src/App.tsx:32`, `src/components/Fleet/Fleet.tsx` | Prematuro. No hay caso de uso validado. Mantener código pero no visible en UI default. |
| **Eliminar AIVO_TESTING de producción** | `sidecar/modules/sentinel_bridge.py:20`, `sidecar/main.py:74`, todos los archivos con `if os.environ.get("AIVO_TESTING")` | Bypass de seguridad inaceptable en producción. Mover a test fixtures. |
| **Desconectar rutas directas executor/filesystem** | `sidecar/modules/executor.py`, `sidecar/modules/filesystem.py` | Las rutas HTTP directas deben redirigir a través del pipeline o devolver deprecation error. |

**Riesgo:** Alto — eliminar funcionalidad existente puede afectar usuarios actuales. Pero es necesario: el producto no puede tener "modo inseguro."

**Rollback:** Cada eliminación es un commit reversible. Usar feature flags para deshabilitar vs eliminar.

**Criterio de finalización:** Sentinel ya no tiene módulos que violen la Constitución. No hay rutas de ejecución que bypassen el pipeline. No hay `AIVO_TESTING` en producción.

---

## FASE 2: Identity Unification

**Objetivo:** Unificar AuthContext e IdentityContext en un único sistema de identidad.

**Razón:** Sin identidad canónica, no se puede garantizar que las políticas se apliquen a la entidad correcta.

**Acciones:**
1. `IdentityContext` en `auth.py` se convierte en la clase canónica (frozen dataclass)
2. `AuthContext` en `interfaces.py` se depreca (alias con DeprecationWarning)
3. `executor.py` y `filesystem.py` dejan de construir `AuthContext` manualmente y usan `request.state.identity`
4. `PathGuardian` acepta `IdentityContext` en vez de `AuthContext`
5. Todos los services actualizan parámetros `auth` → `identity`
6. Todos los adapters actualizan `context["auth"]` → `context["identity"]`

**Archivos afectados:** `modules/auth.py`, `modules/security/interfaces.py`, `modules/executor.py`, `modules/filesystem.py`, `modules/security/path_guardian.py`, `services/executor_service.py`, `services/filesystem_service.py`, `adapters/executor_tool.py`, `adapters/filesystem_tool.py`

**Riesgo:** Medio — cambios de interfaz. Tests deben verificar que identity se propaga correctamente en todas las rutas.

**Criterio de finalización:** Un solo concepto de identidad en toda la base de código. `AuthContext` ya no se usa. Toda ejecución tiene identity asociada.

---

## FASE 3: Pipeline Enforcement

**Objetivo:** Hacer que el pipeline completo sea obligatorio para TODA ejecución.

**Razón:** La fase 1 eliminó los bypasses obvios. Pero aún existen rutas HTTP que no pasan por Intent + Decision (aunque pasen por Gateway). Hay que eliminar toda ruta alternativa.

**Acciones:**

1. **Refactorizar routers.** `executor.py` y `filesystem.py` ya no exponen endpoints directos para operaciones. En su lugar, todo pasa por `POST /v1/execute` (o `/api/sentinel/process` como paso intermedio).

2. **Crear wrapper de compatibilidad.** Por ahora, mantener los endpoints viejos pero que internamente:
   - Construyan un Intent predefinido (ej. "user requested command execution")
   - Pasen por el pipeline completo (Decision → Policy → Gateway)
   - Registren en Audit

3. **Frontend alineado.** Dashboard.tsx ya no tiene acciones rápidas. La interacción primaria es la UI de Sentinel.

**Arquitectura de transición:**

```
API Request → (nuevo middleware de pipeline) → IntentEngine → DecisionEngine → 
  PolicyEngine → ToolGateway → Execution → Quality → Audit
```

**Archivos afectados:** `modules/executor.py`, `modules/filesystem.py`, `modules/monitor.py`, `main.py` (middleware), `orchestrator.py` (procesar intents predefinidos), `sentinel_bridge.py` (simplificar)

**Riesgo:** Alto — cambiar el flujo de ejecución puede romper integraciones existentes. Mitigación: mantener endpoints viejos como proxies que redirigen internamente.

**Criterio de finalización:** NO existe ninguna ruta HTTP que ejecute acciones sin pasar por el pipeline completo.

---

## FASE 4: Quality Gate

**Objetivo:** Implementar validación de salida para toda ejecución.

**Razón:** El pipeline actual valida entrada pero no salida. Una Trust Layer debe asegurar que la IA no pueda exfiltrar datos sensibles a través de Sentinel.

**Acciones:**

1. Crear `sentinel/core/quality_gate.py` con:
   - Detección de patrones sensibles (API keys, tokens, passwords)
   - Límite de tamaño de output (1MB por defecto)
   - Redacción de contenido sensible (replace con `***REDACTED***`)
   - Framework extensible para reglas personalizadas

2. Crear `sentinel/policies/output_policies.py` con reglas por defecto

3. Integrar en `tool_gateway.py` después de `tool.execute()`:
   ```python
   result = await tool.execute(params, ctx)
   verdict = await quality_gate.evaluate(tool_id, params, result, ctx)
   if not verdict.passed:
       result = verdict.sanitized_output or result
       # Log alert
   ```

4. Crear tests para cada regla de quality gate

**Archivos afectados:** **CREAR** `sentinel/core/quality_gate.py`, **CREAR** `sentinel/policies/output_policies.py`, **MODIFICAR** `sentinel/core/tool_gateway.py`, **CREAR** `tests/test_quality_gate.py`

**Riesgo:** Medio — falsos positivos en detección de datos sensibles. Mitigación: reglas conservadoras al inicio, configurables.

**Criterio de finalización:** Todo output de herramientas pasa por Quality Gate. Outputs con datos sensibles son redactados. Tests verifican cada regla.

---

## FASE 5: Policy as Code

**Objetivo:** Mover políticas de código Python a archivos YAML configurables.

**Razón:** Las políticas hardcodeadas en `__init__.py` hacen imposible que los usuarios configuren Sentinel sin modificar código. Una Trust Layer configurable es el requisito #1 de enterprise.

**Acciones:**

1. Diseñar formato YAML para políticas:
   ```yaml
   # ~/.sentinel/policies/permissions.yaml
   version: "1.0"
   policies:
     - name: "default_permission_level"
       type: "permission_level"
       config:
         default_level: "confirm"
         levels:
           view: { auto_approve: 0.0, confirm_threshold: 0.1 }
           confirm: { auto_approve: 0.3, confirm_threshold: 0.7 }
           auto: { auto_approve: 0.6, confirm_threshold: 0.9 }
           admin: { auto_approve: 1.0, confirm_threshold: 1.0 }
     
     - name: "blocked_commands"
       type: "blocklist"
       config:
         patterns: ["format", "diskpart", "reg delete"]
     
     - name: "allowed_directories"
       type: "allowlist"
       config:
         write_paths: ["~/Documents", "~/Desktop", "~/Downloads"]
         read_paths: ["~", "C:\\Projects"]
   ```

2. Crear `sentinel/policies/loader.py` que:
   - Lee YAML desde `~/.sentinel/policies/`
   - Compila a reglas de PolicyEngine
   - Valida sintaxis y esquema
   - Soporta hot-reload (SIGHUP o watch)

3. Migrar políticas existentes:
   - `PermissionLevelPolicy` → YAML
   - `EmergencyStopPolicy` → YAML + endpoint
   - Mapeo permisos→herramientas → YAML
   - `DESTRUCTIVE_PATTERNS` → YAML

4. Deprecar/eliminar `init_policies()` en `modules/__init__.py`

**Archivos afectados:** **CREAR** `sentinel/policies/loader.py`, **CREAR** `sentinel/policies/schema.py` (validación YAML), **MODIFICAR** `sentinel/policies/security_policies.py` (leer de YAML), **MODIFICAR** `sentinel/core/policy_engine.py` (soporte hot-reload), **CREAR** `~/.sentinel/policies/*.yaml` (políticas default), **ELIMINAR** lógica de políticas en `modules/__init__.py`

**Riesgo:** Medio — cambio de formato de configuración. Migración requiere mantener compatibilidad hacia atrás.

**Criterio de finalización:** No existen políticas hardcodeadas en Python. Toda política se configura via YAML. Hot-reload funciona.

---

## FASE 6: Storage Consolidation

**Objetivo:** Unificar todos los sistemas de almacenamiento en una sola capa.

**Razón:** SQLite (database.py) + InMemoryBackend (operational_memory.py) + JSON files (repositories) + dicts (pending_actions) = 4 sistemas de almacenamiento diferentes. Esto hace imposible la auditoría consistente y la migración enterprise.

**Acciones:**

1. Definir esquema SQLite unificado:
   ```sql
   CREATE TABLE audit_log (
     id TEXT PRIMARY KEY,
     timestamp TEXT NOT NULL,
     agent_id TEXT NOT NULL,
     identity_context TEXT NOT NULL,  -- JSON
     intent TEXT NOT NULL,            -- JSON
     risk_score REAL,
     policy_verdict TEXT,
     tool_id TEXT,
     execution_result TEXT,           -- JSON
     quality_verdict TEXT,            -- JSON
     duration_ms REAL
   );
   
   CREATE TABLE operational_state (
     key TEXT PRIMARY KEY,
     value TEXT NOT NULL,
     updated_at TEXT NOT NULL
   );
   
   CREATE TABLE agents (
     id TEXT PRIMARY KEY,
     name TEXT NOT NULL,
     permission_level TEXT NOT NULL DEFAULT 'confirm',
     created_at TEXT NOT NULL,
     last_seen TEXT,
     metadata TEXT                   -- JSON
   );
   ```

2. Migrar `InMemoryBackend` → SQLite
3. Migrar JSON repositories → SQLite
4. Migrar `PENDING_ACTIONS` y `EMERGENCY_STOP` → tabla `operational_state`
5. Eliminar archivos JSON después de migración exitosa

**Archivos afectados:** `repositories/database.py` (expandir), `core/operational_memory.py` (agregar SQLiteBackend), `modules/permissions_memory.py` (usar DB), `repositories/*.py` (simplificar), `main.py` (inicialización DB)

**Riesgo:** Alto — migración de datos. Posible pérdida de registros. Mitigación: migración no destructiva (mantener JSON como backup), tests de integridad.

**Criterio de finalización:** Un solo archivo SQLite contiene todos los datos. No hay archivos JSON con datos de producción. InMemoryBackend solo se usa en tests.

---

## FASE 7: Service Layer Unification

**Objetivo:** Eliminar la dualidad adapters / services.

**Razón:** `sentinel/adapters/` y `sidecar/services/` son dos implementaciones de lo mismo. Los adapters agregan wrappers sin valor real. Los services deberían implementar Tool directamente.

**Acciones:**

1. `ExecutorService` implementa la interfaz `Tool` directamente
2. `FilesystemService` implementa la interfaz `Tool` directamente
3. Eliminar `sentinel/adapters/executor_tool.py` y `adapters/filesystem_tool.py`
4. `system_adapter.py` se mantiene (no hay service duplicado para system)
5. Actualizar `modules/__init__.py` para registrar services directamente como Tools

**Arquitectura resultante:**

```
services/executor_service.py implements Tool
services/filesystem_service.py implements Tool

modules/__init__.py:
  gateway.register(executor_service)  # directamente, sin adapter
  gateway.register(filesystem_service)  # directamente, sin adapter
```

**Archivos afectados:** **ELIMINAR** `sentinel/adapters/executor_tool.py`, **ELIMINAR** `sentinel/adapters/filesystem_tool.py`, **MODIFICAR** `services/executor_service.py` (implementar Tool), **MODIFICAR** `services/filesystem_service.py` (implementar Tool), **MODIFICAR** `modules/__init__.py` (registrar services directamente)

**Riesgo:** Medio — cambio estructural. Tests deben verificar que cada herramienta retorna el mismo resultado que antes.

**Criterio de finalización:** No existe `sentinel/adapters/`. Services implementan Tool directamente.

---

## FASE 8: API Redesign

**Objetivo:** Crear API versionada centrada en el pipeline, no en las herramientas.

**Razón:** La API actual expone 11 routers diferentes que reflejan la arquitectura de módulos, no la del producto. Una Trust Layer necesita una API que refleje su propósito: ejecutar acciones, configurar políticas, consultar auditoría.

**Acciones:**

1. Diseñar API v1 (especificación OpenAPI completa)
2. Implementar nuevos endpoints
3. Marcar endpoints viejos como deprecados con `DeprecationWarning` en headers
4. Migrar frontend a la nueva API

**API v1:**

```
POST /v1/execute           → Pipeline completo
  Body: { agent_id, utterance, context? }
  Response: { execution_id, approved, result, audit_ref }

GET  /v1/execute/:id       → Obtener resultado de ejecución
  
GET  /v1/policies          → Listar políticas
POST /v1/policies          → Crear política
PUT  /v1/policies/:name    → Actualizar política
DELETE /v1/policies/:name  → Eliminar política

GET  /v1/audit             → Query audit log
  Params: agent_id, action, status, from, to, limit, offset

GET  /v1/agents            → Listar agentes registrados
POST /v1/agents            → Registrar agente
DELETE /v1/agents/:id      → Eliminar agente

GET  /v1/identity/me       → Información del agente/usuario actual
PUT  /v1/identity/level    → Cambiar nivel de permiso

GET  /v1/health            → Health check
GET  /v1/metrics           → Prometheus metrics
```

**Archivos afectados:** **CREAR** routers para `/v1/*`, **MODIFICAR** `main.py` (incluir routers v1), **MODIFICAR** `src/api.ts` (apuntar a v1), **DEPRECAR** routers antiguos

**Riesgo:** Alto — cambio de API que puede romper integraciones externas. Mitigación: mantener ambas versiones durante período de transición.

**Criterio de finalización:** API v1 implementada y documentada. API vieja responde con deprecation headers. Frontend usa solo API v1.

---

## FASE 9: UI Redesign

**Objetivo:** Rediseñar el frontend para reflejar la identidad de Trust Layer.

**Razón:** La UI actual con 11 tabs confunde al usuario. Un Trust Layer necesita una interfaz enfocada en tres cosas: ejecutar acciones controladas, configurar políticas, y ver auditoría.

**Nuevas pantallas:**

```
1. EXECUTE (pantalla principal)
   - Input para utterance del agente AI
   - Pipeline visualization en tiempo real
   - Historial de ejecuciones recientes
   - Resultado de última ejecución

2. POLICIES
   - Lista de políticas activas
   - Editor de políticas (YAML con validación)
   - Estado actual (emergency_stop, permission level)
   - Agentes registrados y sus niveles

3. AUDIT
   - Búsqueda y filtros en audit log
   - Timeline de ejecuciones
   - Detalle de cada ejecución (pipeline completo)
   - Export a JSON
```

**No existen:**
- Dashboard con gráficas CPU/RAM
- Chat separado
- Monitor
- Fleet
- Voice
- Plugins (se mueve a settings si es necesario)

**Archivos afectados:** **REESCRIBIR** `src/App.tsx`, **CREAR** `Execute.tsx`, `Policies.tsx`, `Audit.tsx`, **ELIMINAR** `Dashboard/`, `Chat/`, `Monitor/`, `Fleet/`, `Voice/` (referencias)

**Riesgo:** Alto — cambio de UX completo. Usuarios actuales pueden senterse perdidos. Mitigación: release progresiva con opción de UI clásica por un tiempo.

**Criterio de finalización:** Tres pantallas implementadas y funcionales. Sin referencias a UI antigua.

---

## FASE 10: Enterprise Readiness

**Objetivo:** Preparar Sentinel para adopción empresarial.

**Razón:** El mercado enterprise paga por seguridad, compliance, y escalabilidad. Sin estas capacidades, Sentinel es una herramienta de nicho para developers.

**Acciones:**

1. **Docker image** — Dockerfile multi-stage, ~50MB, ejecuta Sentinel como servicio
2. **Instalador Windows** — MSI package con PyInstaller + Tauri
3. **Documentación completa** — Guía de inicio rápido, guía de políticas, referencia de API, guía de deployment
4. **Plugin sandboxing** — Plugins se ejecutan en Wasm sandbox, no Python directo
5. **Audit export** — Export a JSON, CSV, y streaming a stdout (para SIEM)
6. **Health checks** — `/health`, `/ready`, `/metrics` (Prometheus)
7. **Rate limiting** — Por agente, no por IP
8. **TLS** — Soporte HTTPS nativo

**Archivos afectados:** **CREAR** `Dockerfile`, **CREAR** `.github/workflows/release.yml`, **CREAR** `docs/` (documentación), **MODIFICAR** `main.py` (TLS, metrics)

**Riesgo:** Bajo — son adiciones que no rompen funcionalidad existente.

**Criterio de finalización:** Docker image publicada. Instalador Windows funcional. Documentación completa. Plugin sandboxing implementado.

---

## FASE 11: Beta Privada

**Objetivo:** Validar producto con clientes reales antes del lanzamiento.

**Razón:** Todo lo anterior son hipótesis. La beta las valida o las refuta.

**Acciones:**

1. Reclutar 10 empresas/organizaciones para beta cerrada
2. Onboarding guiado (instalación, configuración, primeros casos de uso)
3. Sesiones semanales de feedback
4. Iteración rápida sobre issues de producto
5. Medir métricas clave:
   - Tiempo de instalación a primera ejecución exitosa
   - Número de ejecuciones por día
   - Tasa de aprobación/denegación de políticas
   - Issues de seguridad reportados
   - NPS (Net Promoter Score) semanal

**Criterio de finalización:** 10 usuarios activos con NPS ≥ 40. Feedback documentado y priorizado.

---

## FASE 12: Sentinel 1.0 Launch

**Objetivo:** Lanzamiento público comercial.

**Acciones:**

1. Sitio web: sentinel.ai (o similar)
2. Documentación pública
3. GitHub repository (open source core)
4. Pricing page (Open Core + Enterprise)
5. Security audit por firma externa
6. Comunicado de lanzamiento
7. Demo video (3 minutos)
8. Integraciones pre-construidas con Claude Code, Copilot, OpenCode

**Criterio de finalización:** Producto disponible públicamente. Clientes pueden instalarlo y usarlo. Primeros ingresos enterprise.

---

# PARTE 4 — ESTRATEGIA DE PRODUCTO

## 4.1 Cliente inicial ideal

**Perfil #1: Security Engineer / Developer individual**
- Usa Claude Code, Copilot, o agentes AI personalizados
- Le preocupa que la IA ejecute comandos peligrosos
- Quiere un audit trail de lo que hace la IA
- Tiene capacidad técnica para instalar y configurar
- Presupuesto: $0 (open source) o $20-50/mes (personal)

**Perfil #2: CISO / Head of AI Engineering**
- Empresa de 200-5000 empleados
- Está evaluando o ya usa agentes de IA
- Necesita cumplir con compliance (SOC2, ISO 27001)
- Quiere políticas centralizadas para toda la empresa
- Presupuesto: $10,000-100,000/año

**Perfil #3: AI Tool Vendor (Cursor, Copilot, etc.)**
- Quiere integrar seguridad en su producto
- Prefiere no construir su propia Trust Layer
- Busca una solución open source o white-label
- Presupuesto: Partnership / revenue share

## 4.2 Problema que compra el cliente

**No compran "un pipeline de seguridad."**

Compran:
- "Poder dormir tranquilo sabiendo que la IA no va a borrar mis archivos"
- "Pasar una auditoría de compliance cuando el CISO pregunta cómo controlamos la IA"
- "Poder decir 'sí' a los equipos que quieren usar IA sin poner en riesgo la empresa"
- "No ser el próximo titular de 'empresa pierde datos por culpa de un agente de IA'"

## 4.3 ¿Por qué pagarían?

- **Open Source Core:** Gratis para individuos y equipos pequeños. Pago por features enterprise.
- **Enterprise License:** Políticas centralizadas, audit export, SSO, soporte, multi-endpoint.
- **Managed Cloud:** (Futuro) SaaS donde Sentinel se despliega como proxy en la nube.

Modelo de pricing sugerido:

| Tier | Precio | Features |
|------|--------|----------|
| Community | Gratis | Pipeline completo, 1 agente, políticas locales, audit local |
| Team | $99/mes | 5 agentes, políticas compartidas, audit export |
| Enterprise | $999/mes | Agentes ilimitados, SSO, SIEM integration, soporte, fleet management |

## 4.4 Competencia

| Competidor | ¿Qué hacen? | ¿Cómo se diferencia Sentinel? |
|------------|-------------|------------------------------|
| OpenAI (computer use) | Seguridad propietaria para su modelo | Sentinel es agnóstico a proveedor. Funciona con cualquier modelo. |
| Anthropic (Claude) | Seguridad propietaria para su modelo | Mismo. Agnóstico. |
| Copilot | GitHub's own safety layer | Propietario. Solo para GitHub. Sentinel es universal. |
| Cursor | Sandbox para ejecución | Solo dentro de Cursor. Sentinel protege todo el sistema. |
| Docker/Containers | Aislamiento a nivel de contenedor | Sentinel es una capa de autorización, no de aislamiento. Complementario. |
| Firewalls/EDR | Seguridad de red y endpoints | No entienden intenciones de IA. Sentinel es específico para interacción IA-SO. |
| Políticas de SO (SELinux, AppArmor) | Control de acceso a nivel de kernel | Difíciles de configurar. No entienden "intención." Sentinel es alto nivel. |

## 4.5 Diferenciación sostenible

1. **Agnóstico a proveedor de IA.** La única Trust Layer que funciona con OpenAI, Anthropic, modelos locales, y cualquier agente futuro. Esto es una ventaja estructural — mientras más proveedores de IA existan, más valioso es un intermediario neutral.

2. **Pipeline completo y obligatorio.** No es "mejores prácticas" o "recomendaciones." Es enforcement. Las acciones NO pasan si el pipeline no las aprueba.

3. **Open Source Core.** La Trust Layer misma es open source. Esto genera confianza: cualquiera puede auditar el código que protege su sistema.

4. **Policy as Code.** Las políticas en YAML son versionables, revisables, y desplegables como cualquier otro código de infraestructura.

---

# PARTE 5 — ROADMAP TÉCNICO

## 30 DÍAS (FASES -1, 0, 1)

```
Semana 1-2: Fundación del producto + Congelación
  - Constitución finalizada
  - Tag git + backup
  - Auditoría completa documentada
  - Equipo alineado en identidad

Semana 3-4: Purificación quirúrgica
  - Voice eliminado
  - Proactive deshabilitado
  - Dashboard quick actions eliminadas
  - Chat tab oculta (unificada con Sentinel)
  - AIVO_TESTING eliminado de producción
  - Fleet oculto
  - Tests actualizados
```

✅ **Checkpoint:** Sentinel ya no tiene módulos que contradigan su identidad.

## 90 DÍAS (FASES 2, 3, 4)

```
Semana 5-6: Identity Unification (FASE 2)
  - IdentityContext canónico
  - AuthContext deprecado
  - Identity propagado en todas las rutas
  
Semana 7-9: Pipeline Enforcement (FASE 3)
  - Todas las rutas pasan por pipeline completo
  - Routers de compatibilidad (deprecation warnings)
  - Frontend alineado
  
Semana 10-12: Quality Gate (FASE 4)
  - QualityGate implementado
  - Reglas de output configuradas
  - Tests de quality gate
```

✅ **Checkpoint:** Sentinel es una Trust Layer funcional. Pipeline completo y obligatorio.

## 6 MESES (FASES 5, 6, 7)

```
Semana 13-17: Policy as Code (FASE 5)
  - Formato YAML definido
  - Loader implementado
  - Políticas migradas de Python a YAML
  - Hot-reload funcional
  
Semana 18-22: Storage Consolidation (FASE 6)
  - Esquema SQLite unificado
  - Migración de datos exitosa
  - JSON legacy eliminado
  - InMemoryBackend solo para tests
  
Semana 23-26: Service Layer Unification (FASE 7)
  - Services implementan Tool
  - Adapters eliminados
  - Tests verifican igualdad de comportamiento
```

✅ **Checkpoint:** Arquitectura consolidada. Sin duplicación. Sin bypasses. Sin código legacy.

## 12 MESES (FASES 8, 9, 10)

```
Semana 27-32: API Redesign (FASE 8)
  - API v1 implementada
  - OpenAPI spec completa
  - Frontend migrado a API v1
  - API vieja deprecada

Semana 33-38: UI Redesign (FASE 9)
  - Tres pantallas: Execute, Policies, Audit
  - UI antigua removida
  - Tests E2E de nuevas pantallas
  
Semana 39-44: Enterprise Readiness (FASE 10)
  - Docker image publicada
  - MSI installer funcional
  - Documentación completa
  - Plugin sandboxing
  - SIEM export
  - TLS nativo
```

✅ **Checkpoint:** Producto completo. Listo para beta enterprise.

## 18-24 MESES (FASES 11, 12)

```
Semana 45-52: Beta Privada (FASE 11)
  - 10 beta customers
  - Feedback iterativo
  - Ajustes de producto basados en uso real
  
Semana 53+: Sentinel 1.0 Launch (FASE 12)
  - Lanzamiento público
  - Sitio web + docs + pricing
  - Security audit externo
  - Integraciones con Claude Code, Copilot, OpenCode
```

✅ **Checkpoint:** Producto comercial. Clientes pagando. Roadmap enterprise futuro definido.

---

# PARTE 6 — DECISIONES DIFÍCILES

## ¿Qué eliminarías completamente?

| Módulo | Decisión | Justificación |
|--------|----------|---------------|
| Voice | **ELIMINAR** | 0% relación con Trust Layer. Código muerto. Sin caso de uso. |
| Proactive Engine | **ELIMINAR (código)** / **DESHABILITAR (features)** | Viola "Sentinel no inicia acciones." La identidad del producto lo prohibe. |
| Dashboard Monitoring | **ELIMINAR del producto core** | Las gráficas CPU/RAM son ruido. No son Trust Layer. Mover a proyecto separado si alguien lo necesita. |
| Chat UI | **ELIMINAR / FUSIONAR con Sentinel** | Confunde posicionamiento. La interacción es con Sentinel, no con un chatbot. |
| AIVO_TESTING | **ELIMINAR de producción** | Bypass de seguridad inaceptable. Poner en fixtures de test. |
| Quick Actions | **ELIMINAR** | Bypass del pipeline. Contradicen la Constitución. |
| Fleet (implementación actual) | **OCULTAR / DESHABILITAR** | Prematuro. No hay caso de uso validado. Mantener para enterprise futuro. |

## ¿Qué conservarías?

| Componente | Decisión | Justificación |
|------------|----------|---------------|
| Pipeline core (orchestrator, intent, decision, policy, gateway) | **CONSERVAR** | Es la esencia del producto. Bien diseñado conceptualmente. |
| PathGuardian | **CONSERVAR** | Excelente implementación de seguridad de paths. Bien pensado. |
| Audit system | **CONSERVAR (unificar)** | Buen concepto. Necesita unificación y formato inmutable. |
| IdentityContext (auth.py) | **CONSERVAR (expandir)** | Buen diseño de identidad. Hacerlo canónico. |
| PolicyEngine | **CONSERVAR** | Buena arquitectura. Necesita config externalizada. |
| ToolGateway | **CONSERVAR** | Punto central de enforcement. Correcto por diseño. |
| Tool interface | **CONSERVAR** | Abstracción correcta. |

## ¿Qué reconstruirías?

| Componente | Decisión | Por qué reconstruir |
|------------|----------|---------------------|
| Frontend (React) | **REESCRIBIR** | 11 tabs confusas → 3 pantallas enfocadas. El código actual refleja la identidad anterior. |
| API (FastAPI routers) | **REESCRIBIR** | De API de módulos a API de producto. `/v1/execute`, no `/api/executor/command` |
| Policy configuration | **REESCRIBIR** | De hardcodeada en Python a YAML configurable. Cambio fundamental de arquitectura. |
| Storage layer | **REESCRIBIR** | De fragmentada (SQLite + JSON + dicts + in-memory) a unificada (SQLite única). |
| Service layer | **REESCRIBIR** | De dual (services + adapters) a single (services implement Tool). |

## ¿Qué nunca implementarías?

| Capacidad | Por qué nunca |
|-----------|---------------|
| Iniciativa proactiva | Viola la Constitución. Sentinel no inicia acciones. |
| Hosting de modelos | Competiría con complementos (OpenAI, Ollama). Destruye la posición de capa neutral. |
| Generación de código | No es el propósito. Eso es trabajo de la IA. |
| File sync / almacentamiento | No es Dropbox ni Google Drive. |
| Plataforma de comunicación | No es Slack ni Teams. |
| Remote desktop / VNC | No es TeamViewer. |
| App store / marketplace general | Plugins de seguridad OK. Marketplace general NO. |
| BI / Analytics platform | No es Tableau. Reportes de compliance OK, analytics general NO. |
| Identity provider | No es Okta. Integrar con ellos, no reemplazarlos. |

## ¿Qué características parecen atractivas pero destruirían la identidad?

1. **"AI assistant mode"** — Dejar que el usuario hable en lenguaje natural y Sentinel decida qué hacer. Esto convierte a Sentinel en un agente de IA, contradiciendo "Sentinel no inicia acciones."

2. **"Auto-fix mode"** — Sentinel detecta un problema y lo corrige automáticamente. Suena útil, pero destruye "Toda acción debe pasar por el pipeline." Sentinel no puede iniciar acciones.

3. **"Recipes / Playbooks"** — Secuencias predefinidas de acciones. Suena como producto, pero convierte a Sentinel en una herramienta de automatización. Hay muchas herramientas de automatización. No es el diferenciador.

4. **"Sentinel Copilot"** — Un asistente AI dentro de Sentinel. Confunde: "¿Sentinel es la Trust Layer o el agente?" La línea se vuelve borrosa.

5. **"Community templates"** — Repositorio de políticas compartidas. Útil, pero riesgo de que Sentinel se convierta en un marketplace, no en una Trust Layer.

---

# PARTE 7 — EVALUACIÓN EMPRESARIAL

## ¿Invertiría en Sentinel?

**Como CTO de una empresa de infraestructura de IA:** Depende de qué versión.

### Invertiría en la VISIÓN

El concepto de Trust Layer entre IA y SO es:
- **Necesario.** El problema existe y crece exponencialmente.
- **Bien posicionado.** Agnóstico a proveedor es una ventaja estructural en un mercado de múltiples modelos.
- **Timing correcto.** 2026 es el año en que los agentes de IA empiezan a estar en producción empresarial. Hay ventana de oportunidad.
- **Defendible.** Policy as Code + audit trail + agnosticismo crea un moat. No es solo "una feature" — es una plataforma.

### NO invertiría en el código ACTUAL

El prototipo actual tiene:
- Crisis de identidad de producto
- Bypasses de seguridad documentados
- 4 sistemas de almacenamiento
- Sin Quality Gate
- Sin documentación
- Sin instalación profesional
- Sin clientes

Invertir en esto hoy sería especulación. Invertiré en la visión + el equipo + el plan de transformación.

### ¿Qué tendría que ocurrir para que una empresa confiara en Sentinel?

1. **Security audit externo.** Una firma de seguridad revisa el código y confirma que no hay bypasses, no hay fugas de datos, no hay vulnerabilidades críticas.

2. **Caso de éxito documentado.** Al menos 3 empresas usándolo en producción con resultados medibles.

3. **Open source confiable.** Repositorio activo, contribuciones, comunidad, governance claro.

4. **Documentación profesional.** No solo API docs — guías de deployment, troubleshooting, best practices, architecture decision records.

5. **SLAs.** Para la versión enterprise, garantías de disponibilidad y soporte.

6. **Roadmap público.** Saber que el producto tiene futuro y dirección.

7. **Foundation / Company.** Una entidad legal responsable, no un proyecto de un solo desarrollador.

---

# PARTE 8 — PLAN DE EJECUCIÓN

## PRIMEROS 10 PASOS (ordenados por prioridad, no por facilidad)

### Paso 1: Finalizar la Constitución
**Prioridad:** #1
**Responsable:** Founder / CTO
**Acción:** Tomar la Constitución esbozada en este documento y refinarla con el equipo hasta que no quede ambigüedad. Publicarla en el README del repositorio como `CONSTITUTION.md`.
**Duración:** 2 días
**Depende de:** Nada

### Paso 2: Backup y etiquetado
**Prioridad:** #2
**Responsable:** Arquitecto
**Acción:** `git tag pre-transformation-v1.0`. Backup de bases de datos SQLite y JSON. Capturar métricas base (tests, líneas de código, cobertura).
**Duración:** 1 día
**Depende de:** Paso 1

### Paso 3: Auditar todas las rutas de ejecución
**Prioridad:** #3
**Responsable:** Security Engineer
**Acción:** Mapear CADA ruta de ejecución desde frontend hasta sistema operativo. Identificar bypasses. Documentar en `ARCHITECTURE.md` como "Execution paths."
**Duración:** 3 días
**Depende de:** Paso 2
**Entregable:** Mapa de rutas con veredicto de compliance por cada una.

### Paso 4: Eliminar bypasses críticos
**Prioridad:** #4
**Responsable:** Arquitecto + Developer
**Acción:** 
- Eliminar Dashboard quick actions (Dashboard.tsx:106-109)
- Eliminar AIVO_TESTING de producción (mover a test fixtures)
- Hacer que executor y filesystem routers pasen por pipeline (no directamente)
**Duración:** 1 semana
**Depende de:** Paso 3
**Riesgo:** Alto (cambia UX existente)
**Mitigación:** Feature flags. Mantener endpoints viejos como proxies deprecados.

### Paso 5: Eliminar Voice y deshabilitar Proactive
**Prioridad:** #5
**Responsable:** Developer
**Acción:** 
- Eliminar `sidecar/modules/voice.py`, `sidecar/services/voice_service.py`
- Deshabilitar Proactive Engine (no arrancar en startup, ocultar UI)
- Eliminar Fleet de la navegación principal
**Duración:** 2 días
**Depende de:** Paso 2 (no necesita la auditoría)
**Riesgo:** Bajo

### Paso 6: Unificar IdentityContext
**Prioridad:** #6
**Responsable:** Security Engineer + Developer
**Acción:** 
- Hacer IdentityContext canónico
- Deprecar AuthContext
- Propagar identity en todas las rutas
- Actualizar PathGuardian y services
**Duración:** 1 semana
**Depende de:** Paso 4 (porque las rutas cambian)
**Riesgo:** Medio

### Paso 7: Implementar Quality Gate MVP
**Prioridad:** #7
**Responsable:** Developer
**Acción:**
- Crear `sentinel/core/quality_gate.py`
- Detección de patrones sensibles (API keys, tokens)
- Integrar en ToolGateway
- Tests
**Duración:** 1 semana
**Depende de:** Paso 6 (identity necesario para contexto de quality)
**Riesgo:** Medio

### Paso 8: Policy as Code MVP
**Prioridad:** #8
**Responsable:** Arquitecto + Developer
**Acción:**
- Diseñar formato YAML
- Crear `sentinel/policies/loader.py`
- Migrar DESTRUCTIVE_PATTERNS a YAML
- Migrar PermissionLevelPolicy a YAML
- Hot-reload básico (SIGHUP)
**Duración:** 2 semanas
**Depende de:** Paso 6 (políticas usan identity)
**Riesgo:** Medio

### Paso 9: Storage Consolidation
**Prioridad:** #9
**Responsable:** Developer (backend)
**Acción:**
- Diseñar esquema SQLite unificado
- Migrar operational_memory a SQLite
- Migrar pending_actions a SQLite
- Migrar JSON repositories a SQLite
- Tests de migración
**Duración:** 2 semanas
**Depende de:** Paso 7 (quality gate usa tool gateway, que usa operational_memory)
**Riesgo:** Alto

### Paso 10: Service Layer Unification
**Prioridad:** #10
**Responsable:** Arquitecto + Developer
**Acción:**
- ExecutorService implementa Tool
- FilesystemService implementa Tool
- Eliminar adapters
- Actualizar registros en modules/__init__.py
- Tests de comparación (mismo input → mismo output)
**Duración:** 2 semanas
**Depende de:** Paso 8, 9 (estabilidad de services y storage)
**Riesgo:** Alto

---

## RESUMEN DE PRIMEROS 10 PASOS

| # | Paso | Días | Riesgo | Depende de |
|---|------|------|--------|------------|
| 1 | Constitución | 2 | Bajo | — |
| 2 | Backup + tag | 1 | Bajo | 1 |
| 3 | Auditoría de rutas | 3 | Bajo | 2 |
| 4 | Eliminar bypasses | 5 | Alto | 3 |
| 5 | Voice/Proactive/Fleet | 2 | Bajo | 2 |
| 6 | Identity Unification | 5 | Medio | 4 |
| 7 | Quality Gate MVP | 5 | Medio | 6 |
| 8 | Policy as Code | 10 | Medio | 6 |
| 9 | Storage Consolidation | 10 | Alto | 7 |
| 10 | Service Unification | 10 | Alto | 8, 9 |

**Total primeros 10 pasos: ~53 días hábiles (~11 semanas)**

---

## DOCUMENTO FINAL — CONSTITUCIÓN DE SENTINEL

```
╔═══════════════════════════════════════════════════════════════╗
║                 CONSTITUCIÓN DE SENTINEL                      ║
║                                                               ║
║  Sentinel es una capa de confianza entre agentes de           ║
║  inteligencia artificial y sistemas operativos.               ║
║                                                               ║
║  Su propósito es garantizar que ninguna acción iniciada       ║
║  por IA llegue al sistema sin ser:                            ║
║                                                               ║
║     1. Comprendida  (Intent)                                  ║
║     2. Evaluada     (Decision)                                ║
║     3. Autorizada   (Policy)                                  ║
║     4. Controlada   (Gateway → Execution)                     ║
║     5. Validada     (Quality)                                 ║
║     6. Registrada   (Audit)                                   ║
║                                                               ║
║  ─── PRINCIPIOS IRROMPIBLES ───                               ║
║                                                               ║
║  I.   Nunca IA → SO directo.                                  ║
║  II.  Toda acción pasa por el pipeline completo.              ║
║  III. Sentinel no inicia acciones.                            ║
║  IV.  Toda salida es validada antes de entregarse.            ║
║  V.   No existe ejecución sin auditoría.                      ║
║  VI.  Toda identidad es canónica y única.                     ║
║  VII. Toda política es configurable, no hardcodeada.          ║
║  VIII.Una sola fuente de verdad para cada concepto.           ║
║  IX.  Las dependencias son unidireccionales.                  ║
║  X.   Todo bypass es una vulnerabilidad.                      ║
║                                                               ║
║  ─── QUÉ NO ES SENTINEL ───                                   ║
║                                                               ║
║  No es un chatbot.                     No es un IDE.          ║
║  No es un dashboard.                   No es un framework.    ║
║  No es un sistema operativo.           No es un agente.       ║
║  No es un proveedor de modelos.        No es un antivirus.    ║
║  No es una herramienta de monitoreo.   No es un RPA.          ║
║  No es una plataforma de comunicación. No es un file sync.    ║
║                                                               ║
║  ─── ENFOQUE ───                                              ║
║                                                               ║
║  Este producto no compite con Claude, Copilot, Cursor,        ║
║  OpenAI, Anthropic, Ollama, ni ninguna IA.                    ║
║                                                               ║
║  Este producto COMPLEMENTA a todas ellas.                     ║
║                                                               ║
║  Mientras más proveedores de IA existan, más importante       ║
║  es tener una capa neutral, abierta y auditable que           ║
║  garantice que ninguna IA actúa sin control.                  ║
║                                                               ║
║  ─── MÉTRICA DE ÉXITO ───                                     ║
║                                                               ║
║  Sentinel tiene éxito cuando un equipo de seguridad puede     ║
║  decir: "Usamos cualquier modelo de IA que queramos porque    ║
║  Sentinel garantiza que ninguna acción peligrosa llega al     ║
║  sistema sin autorización."                                   ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

---

*Documento completado. 12 fases definidas. 10 pasos iniciales priorizados. Constitución redactada.*

*Este documento es el plan oficial de transformación de Sentinel desde prototipo hasta producto comercial.*

*Próximo paso: Aprobación del equipo y ejecución del Paso 1 — Constitución.*
