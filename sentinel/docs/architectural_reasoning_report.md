# Architectural Reasoning Report — Sentinel Trust Layer

**Autor:** Lead Software Architect
**Propósito:** Pase de razonamiento completo antes de iniciar migración
**Estado:** Análisis interno — no vinculante hasta aprobación

---

## 1. Product Architecture — Trust Layer Fit

### 1.1 Modules that belong to the Trust Layer

| Módulo | Trust Layer? | Por qué |
|--------|-------------|---------|
| `sentinel/core/orchestrator.py` | ✅ **CORE** | Ejecuta el pipeline central: Intent → Decision → Policy → Gateway → Execution → Audit |
| `sentinel/core/tool_gateway.py` | ✅ **CORE** | Es el guardián que intercepta toda ejecución de herramientas, aplica políticas |
| `sentinel/core/decision_engine.py` | ✅ **CORE** | Risk scoring — decide si una acción puede ejecutarse según nivel de permiso |
| `sentinel/core/intent.py` | ✅ **CORE** | NLP de entrada — sin esto, el Trust Layer no entiende qué pide el agente |
| `sentinel/core/planner.py` | ✅ **CORE** | Planificación multi-step — valiosa para Trust Layer (no para atajos) |
| `sentinel/core/policy_engine.py` | ✅ **CORE** | Evaluación de políticas de seguridad |
| `sentinel/core/policy.py` | ✅ **CORE** | Definición de políticas |
| `sentinel/core/context.py` | ✅ **CORE** | Contexto del sistema para decisiones informadas |
| `sentinel/core/model_router.py` | ✅ **CORE** | Necesario para enterprise multi-provider |
| `sentinel/core/operational_memory.py` | ✅ **CORE** | Registro de ejecuciones — audit trail |
| `sentinel/core/goals.py` | ✅ **CORE** | Registro de metas — alinea acciones del AI con intención del usuario |
| `sentinel/core/capability_registry.py` | ✅ **CORE** | Catálogo de herramientas disponibles |
| `sentinel/core/tool.py` | ✅ **CORE** | Interfaz base de herramientas |
| `sentinel/core/memory.py` | ⚠️ **UTILITY** | Memoria de conversación — no es Trust Layer per se, pero útil para contexto |
| `sidecar/modules/auth.py` | ✅ **CORE** | Identidad — fundamental para Trust Layer |
| `sidecar/modules/authorization.py` | ✅ **CORE** | Control de acceso basado en niveles |
| `sidecar/modules/audit.py` | ✅ **CORE** | Log de auditoría |
| `sidecar/modules/permissions.py` | ✅ **CORE** | Gestión de permisos |
| `sidecar/modules/security/` | ✅ **CORE** | PathGuardian, políticas de path — seguridad de archivos |
| `sidecar/modules/sentinel_bridge.py` | ✅ **CORE** | API primaria del Trust Layer |
| `sentinel/policies/security_policies.py` | ✅ **CORE** | Políticas de seguridad (PermissionLevel, EmergencyStop) |

### 1.2 Modules from the OLD product vision

Estos módulos existen porque Sentinel comenzó como "panel de control con IA". Pertenecen a la visión anterior:

| Módulo | Visión anterior | Trust Layer? | Decisión |
|--------|----------------|-------------|----------|
| `sidecar/modules/monitor.py` | Dashboard de monitoreo | ❌ No | **OPTIONAL** — útil pero no central. Debe ser desacoplable |
| `sidecar/modules/proactive.py` | "Mayordomo AI" que sugiere acciones | ❌ No | **OPTIONAL** — conflicto con Trust Layer (sugerir acciones es diferente de autorizarlas) |
| `sidecar/modules/voice.py` | Text-to-speech | ❌ No | **REMOVE** — sin uso real, sin tab en frontend |
| `sidecar/modules/fleet.py` | Conexión remota | ❌ No | **OPTIONAL / HIDE** — prematuro, caso de uso no validado |
| `sidecar/modules/plugins.py` | Sistema de plugins de automatización | ⚠️ **PARCIAL** | **RE-EVALUATE** — plugins para Trust Layer (políticas personalizadas) son válidos. Plugins de automatización general no. |
| `sidecar/services/monitor_service.py` | Backend de monitoreo | ❌ No | **OPTIONAL** |
| `sidecar/services/proactive_service.py` | Motor de sugerencias | ❌ No | **OPTIONAL** |
| `sidecar/services/voice_service.py` | TTS backend | ❌ No | **REMOVE** |
| `sidecar/services/fleet_service.py` | Pairing remoto | ❌ No | **OPTIONAL / HIDE** |
| `sidecar/services/plugins_service.py` | Plugin hooks | ⚠️ **PARCIAL** | Ver plugins arriba |

### 1.3 Frontend — Trust Layer Fit

| Tab | Trust Layer? | Decisión |
|-----|-------------|----------|
| **Sentinel** | ✅ CORE | Es la interfaz del Trust Layer |
| **Permissions** | ✅ CORE | Gestión de niveles de permiso |
| **Audit** | ✅ CORE | Visualización de auditoría |
| **Console** | ✅ ÚTIL | Terminal para comandos (pasa por Trust Layer) |
| **Files** | ✅ ÚTIL | Explorador de archivos (pasa por Trust Layer) |
| **Settings** | ✅ ÚTIL | Configuración de AI provider |
| **Dashboard** | ❌ Old vision | Monitoreo CPU/RAM/Disk + acciones rápidas. Las acciones rápidas son un **bypass del Trust Layer**. |
| **Monitor** | ❌ Old vision | Monitoreo detallado |
| **Chat** | ❌ Old vision | Hace que Sentinel parezca un chatbot. Confunde el posicionamiento. |
| **Plugins** | ⚠️ Ambiguo | Depende de la dirección del sistema de plugins |
| **Fleet** | ❌ Prematuro | Conexión remota |

**Recomendación:** El Dashboard debería **eliminar las acciones rápidas** (cleanmgr, taskmgr, cmd.exe, notepad) o migrarlas a usar `api.sentinel.process()`. El monitoreo puede quedarse como widget opcional. La tab Chat debería reconsiderarse — o es Sentinel o es Chat, no ambos.

---

## 2. Execution Flow — Mapa completo

### 2.1 Todas las rutas de ejecución

```
RUTA A — Sentinel (FULL TRUST LAYER)
  Usuario → [Frontend: api.sentinel.process(utterance)]
  → POST /api/sentinel/process
  → sentinel_bridge:78 → orchestrator.process(utterance)
    → IntentEngine.parse()               # ✅ INTENT
    → Planner.plan()                     # ✅ PLAN
    → DecisionEngine.evaluate()          # ✅ DECISION (risk score)
    → ToolGateway.execute()              # ✅ GATEWAY
      → PolicyEngine.evaluate()          # ✅ POLICY
      → tool.execute()                   # ✅ EXECUTION
      → (No QualityGate)                 # ❌ OUTPUT VALIDATION
    → MemoryBackend.store_execution()    # ✅ AUDIT
  → Response to frontend

RUTA B — Executor Direct (BYPASS PARCIAL)
  Usuario → [Frontend: api.executor.command(cmd)]
  → POST /api/executor/command
  → executor:57 → gw.execute("executor.command", params)
    → ToolGateway.execute()
      → PolicyEngine.evaluate()          # ✅ POLICY
      → executor_tool.execute()          # ✅ EXECUTION
        → executor_service.execute()     # ✅ REAL EXECUTION (validate + run)
    → service._log_action()              # ✅ AUDIT (local, no pipeline)
  ❌ NO IntentEngine → no hay parseo de intención
  ❌ NO DecisionEngine → no hay risk scoring
  ❌ NO Planner → ejecución directa
  ❌ NO QualityGate → output sin filtrar

RUTA C — Filesystem Direct (BYPASS PARCIAL)
  → POST /api/fs/read
  → filesystem:39 → gw.execute("filesystem.read", params)
    → ToolGateway.execute()
      → PolicyEngine.evaluate()          # ✅ POLICY
      → filesystem_tool.execute()        # ✅ EXECUTION
        → filesystem_service.read_file() # ✅ REAL I/O
  ❌ NO IntentEngine
  ❌ NO DecisionEngine
  ❌ NO Planner
  ❌ NO Audit (lecturas no se auditan)
  ❌ NO QualityGate

RUTA D — Monitor Direct (BYPASS COMPLETO — solo lectura)
  → GET /api/monitor/cpu
  → monitor router → monitor_service.get_cpu()
  ⚠️ No pasa por gateway / policies / audit
  ⚠️ Solo lectura — riesgo bajo pero ninguna trazabilidad

RUTA E — AI Chat Direct (BYPASS COMPLETO — dominio diferente)
  → POST /api/ai/chat
  → ai router → ai_service.chat()
  ⚠️ No pasa por gateway / policies / audit
  ⚠️ No es ejecución de OS, pero consume tokens sin control

RUTA F — Proactive Execution (BYPASS DEPENDE DE IMPLEMENTACIÓN)
  → proactive:40 → _svc.execute_suggestion(id)
  → Puede llamar a executor_service directamente o a través del gateway
  ⚠️ Depende de implementación actual — hay que verificar

RUTA G — Dashboard Quick Actions (BYPASS CRÍTICO)
  → [Frontend: <button onClick={() => api.executor.command("cleanmgr")}>]
  → Misma ruta que RUTA B pero desde UI que debería usar Sentinel
  🔴 El botón "Clean Disk" ejecuta cleanmgr sin consentimiento explícito
  🔴 "Open Terminal" → cmd.exe sin restricción
  🔴 "Notepad" → notepad.exe sin restricción
  🔴 "Task Manager" → taskmgr.exe sin restricción
```

### 2.2 Verify: ¿Cada ruta satisface el pipeline completo?

| Ruta | Intent | Decision | Policy | Gateway | Execution | Audit | Veredicto |
|------|--------|----------|--------|---------|-----------|-------|-----------|
| A (Sentinel) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **CUMPLE** |
| B (Executor) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | **BYpass** |
| C (Filesystem) | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | **BYpass** |
| D (Monitor) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | **BYpass** |
| E (AI Chat) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | **BYpass** |
| F (Proactive) | ❌ | ❌ | ⚠️ | ⚠️ | ✅ | ⚠️ | **BYpass** |
| G (Dashboard) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | **BYpass** |

**Totales:**
- 1 ruta cumple completamente (A)
- 6 rutas tienen bypasses de diversa gravedad
- 2 bypasses son críticos (B, G) porque ejecutan comandos en OS
- 2 bypasses afectan seguridad de archivos (C, F)
- 2 bypasses son de solo lectura (D, E) — riesgo bajo pero incoherente

---

## 3. Responsibility Analysis

### 3.1 ¿Por qué existe cada capa?

| Capa | ¿Por qué existe? | Responsabilidad única | ¿Podría otra capa hacerlo? |
|------|-----------------|----------------------|---------------------------|
| `sentinel/core/` | Arquitectura del Trust Layer | Pipeline de seguridad | No — es la capa central |
| `sentinel/adapters/` | Wrapper de servicios para interfaz Tool | Convertir servicios en Tools | **SÍ** — los services podrían implementar Tool directamente |
| `sentinel/policies/` | Reglas de seguridad | Definición de políticas | No — única |
| `sidecar/modules/` | Routers HTTP + estado global | Enrutamiento HTTP + DI | Parcial — el routing es necesario, la DI podría ser más explícita |
| `sidecar/services/` | Lógica de negocio real | Ejecución real de operaciones | No — es la implementación real |
| `sidecar/repositories/` | Persistencia | Acceso a datos | No — única |
| `sidecar/modules/security/` | Seguridad de paths | Validación de rutas de archivos | No — única pero debería estar en `sentinel/` |
| `src/` (frontend) | Interfaz de usuario | UX + visualización | No — única |

### 3.2 Duplicación detectada

La única duplicación **real** entre capas es:

1. **`sentinel/adapters/` ↔ `sidecar/services/`**: Los adapters NO agregan lógica de negocio única. Son wrappers que convierten `params` dict → kwargs posicionales. Sin embargo, SÍ agregan:
   - `executor_tool.py`: PathGuardian check extra + ToolResult wrapping
   - `filesystem_tool.py`: ToolResult wrapping
   
   **Veredicto:** Los adapters son delgados pero NO son pura duplicación. El problema real es que los services no implementan Tool directamente. Si executor_service implementara Tool, el adapter desaparecería.

2. **`DESTRUCTIVE_PATTERNS` en 3 lugares**: Ya documentado.

3. **`_auth()` en executor.py y filesystem.py**: Misma función, escrito dos veces.

### 3.3 Abstracciones innecesarias

1. **`CapabilityRegistry`**: Es un wrapper delgado alrededor de `dict[str, Capability]`. Su lógica es trivial (register, get, count, list). Podría ser un dict simple dentro de ToolGateway.

2. **`ToolSpec` como dataclass separado de `Tool`**: Cada Tool tiene un `spec()` que retorna ToolSpec. Esto es razonable para separar metadata de implementación, pero introduce complejidad.

3. **`PolicyEffect` enum + `PolicyResult` dataclass**: Separado de `Policy` y `PolicyEngine`. Razonable para un sistema de políticas.

4. **`OperationalMemory` como clase separada**: Podría ser parte de `Orchestrator` o del DataLayer. La abstracción es innecesaria para el tamaño actual del proyecto, pero valiosa para testabilidad.

---

## 4. Dependency Analysis — Hallazgos

### 4.1 Service Locator Pattern (anti-patrón)

`sidecar/modules/__init__.py` actúa como Service Locator:

```python
_gateway = None

def get_gateway():
    global _gateway
    if not _gateway:
        _init_gateway()
    return _gateway
```

Cualquier módulo puede llamar `get_gateway()` sin declarar la dependencia. Esto:
- Oculta el grafo de dependencias real
- Hace imposible aislar módulos para testing
- Crea un singleton mutable global
- El orden de inicialización importa y no está explicitado

**Impacto:** 8 archivos importan `get_gateway()` — no hay manera de saberlo sin grep.

### 4.2 Estado global compartido

```python
# permissions_memory.py
PENDING_ACTIONS = PendingActionsDict()  # dict global
EMERGENCY_STOP = EmergencyStopFlag()    # lista global

# permissions.py
PENDING_ACTIONS = permissions_memory.PENDING_ACTIONS  # re-export
EMERGENCY_STOP = permissions_memory.EMERGENCY_STOP     # re-export

# executor.py
from modules.permissions import PENDING_ACTIONS  # importa el mismo objeto mutable
```

**Problema:** 3 módulos diferentes modifican el mismo dict global sin coordinación. Si un request modifica PENDING_ACTIONS mientras otro lo lee, hay race condition.

### 4.3 Acoplamiento oculto

`executor_service.py` accede a `self._perm.pending_actions` directamente (línea 77):
```python
if action_id and action_id in (self._perm.pending_actions if self._perm else {}):
    action = self._perm.pending_actions.pop(action_id)
```

Esto acopla `ExecutorService` a la estructura interna de `PermissionsService`. Si `PermissionsService` cambia la implementación de `pending_actions`, `ExecutorService` se rompe.

### 4.4 Código muerto

1. `sidecar/modules/voice.py` — router TTS existe, API en frontend existe, pero ninguna tab lo usa realmente
2. `sidecar/modules/executor.py:38-39` — `validate_command = _svc.validate_command` y `classify_command = _svc.classify_command` — re-exportados "for backward compatibility". ¿Algo los importa?
3. `sidecar/modules/permissions.py:42` — `check_permission = _svc.check_permission` — re-export.
4. `sentinel/core/memory.py` — Separado de `operational_memory.py`. La memoria de conversación no se usa en el pipeline actual.

### 4.5 Dependencia circular potencial

La inicialización en `main.py` hace:
```python
import modules.permissions as permissions_mod
# ...
executor_mod.wire_dependencies(permissions_svc=permissions_mod._svc, ...)
```

Y `executor.py` hace:
```python
from modules.permissions import PENDING_ACTIONS  # en tiempo de ejecución dentro de run_command()
```

No hay circular en import time, pero sí en runtime: `executor → permissions → executor` (a través del gateway y pending_actions).

---

## 5. Security Analysis — Profundidad

### 5.1 Operaciones privilegiadas por nivel de permiso

| Operación | view | confirm | auto | admin |
|-----------|------|---------|------|-------|
| Ejecutar comando | ❌ Denied | ⚠️ Requires confirm | ⚠️ Auto si riesgo bajo | ✅ Auto |
| Matar proceso | ❌ Denied | ⚠️ Requires confirm | ⚠️ Auto si riesgo bajo | ✅ Auto |
| Lanzar app | ❌ Denied | ⚠️ Requires confirm | ⚠️ Auto si riesgo bajo | ✅ Auto |
| Leer archivo | ⚠️ Requires confirm | ⚠️ Requires confirm | ✅ Auto | ✅ Auto |
| Escribir archivo | ❌ Denied | ⚠️ Requires confirm | ⚠️ Auto si riesgo bajo | ✅ Auto |
| Cambiar nivel permiso | ❌ ¿? | ❌ ¿? | ❌ ¿? | ✅ Solo admin |
| Ver audit log | ✅ Sí | ✅ Sí | ✅ Sí | ✅ Sí |
| Gestionar goals | ❌ Solo admin | ❌ Solo admin | ❌ Solo admin | ✅ Solo admin |
| Emergency stop/resume | ❌ ¿? | ❌ ¿? | ❌ ¿? | ✅ ¿? |

**Problema:** `POST /api/permissions/level` no verifica quién hace el cambio. Si un agente AI con acceso a la API llama a `POST /api/permissions/level {"level": "auto"}`, se auto-autoriza.

### 5.2 Propagación de identidad

| Operación | IdentityContext | AuthContext | ¿Ambos? |
|-----------|----------------|-------------|---------|
| auth_middleware inyecta | ✅ `request.state.identity` | ❌ | Solo IdentityContext |
| executor.py construye | ❌ | ✅ `_auth(request)` | Solo AuthContext |
| filesystem.py construye | ❌ | ✅ `_auth(request)` | Solo AuthContext |
| sentinel_bridge.py recibe | ✅ del middleware | ❌ | Solo IdentityContext |
| executor_tool.py recibe | ❌ `context["auth"]` | ✅ | Solo AuthContext |
| filesystem_tool.py recibe | ❌ `context["auth"]` | ✅ | Solo AuthContext |

**Problema:** La identidad se crea DOS VECES en cada request que pasa por executor/filesystem: una por el middleware (IdentityContext), otra por `_auth()` (AuthContext). Y NO son el mismo objeto ni contienen los mismos campos.

### 5.3 Propagación de auditoría

| Operación | ¿Se audita? | ¿Dónde? | ¿Por el pipeline? |
|-----------|------------|---------|-------------------|
| Sentinel process | ✅ | orchestrator → operational_memory | ✅ Sí |
| Executor command | ✅ | executor_service._log_action → AuditService | ❌ No (servicio local) |
| File read | ❌ No | — | ❌ No |
| File write | ✅ | filesystem_service._log_action (si audit_svc está configurado) | ❌ No (servicio local) |
| Kill process | ✅ | executor_service._log_action | ❌ No |
| Launch app | ✅ | executor_service._log_action | ❌ No |
| AI chat | ❌ No | — | ❌ No |
| Plugin load | ❌ No | — | ❌ No |
| Fleet pairing | ❌ No | — | ❌ No |

**Problema:** La auditoría ocurre en dos lugares distintos:
1. Pipeline: `Orchestrator → MemoryBackend.store_execution()` — solo para Ruta A
2. Servicios: `servicio._log_action()` — para Rutas B, C, F, G

Esto significa que NO hay un audit trail unificado. Los records de OperationalMemory tienen un formato diferente a los de AuditService.

### 5.4 Propagación de políticas

| Policy | ¿Se aplica? | ¿Dónde? |
|--------|------------|---------|
| PermissionLevelPolicy | ✅ En todas las rutas que pasan por ToolGateway | `__init__.py:96-98` → ToolGateway.set_policy_engine |
| EmergencyStopPolicy | ✅ En todas las rutas que pasan por ToolGateway | `__init__.py:97` → ToolGateway.set_policy_engine |
| PathGuardian | ✅ En filesystem_service (siempre) | `filesystem_service.py:24` → guardian.validate_read |
| PathGuardian | ⚠️ En executor_tool SOLO si es file op | `executor_tool.py:47-55` → guardian.validate_write |
| PathGuardian | ❌ En executor_service.validate | Solo usa DESTRUCTIVE_PATTERNS, no PathGuardian |
| Blocklist/Allowlist | ✅ En permissions_service | `permissions_service.py` |

**Problema:** Las políticas se aplican en diferentes capas dependiendo de la ruta. No hay un punto único de enforcement.

### 5.5 Protección de filesystem

`PathGuardian` (164 líneas) es sorprendentemente completo:
- Path traversal detection
- Symlink resolution + validation
- Sensitive filename patterns
- Blocked paths list
- Allowlist for write operations
- Path length limits
- Risk level assessment

**Pero:** Sólo se aplica cuando se llama explícitamente. La ruta B (executor direct) NO llama a PathGuardian para validar paths dentro de comandos a menos que `executor_tool._is_file_operation()` devuelva True.

**Escenario de ataque:** Un agente AI ejecuta `echo malicious_content > C:\Windows\System32\drivers\etc\hosts` — este comando NO contiene `del`, `rm`, `copy`, etc. `_is_file_operation()` devuelve False. PathGuardian NO se aplica. El comando se ejecuta directamente.

### 5.6 Protección de ejecución de comandos

`executor_service.validate_command()` hace:
1. Verifica longitud máxima (8192)
2. Detecta shell metachars (&, \|, ;, \`, $, etc.)
3. Si hay metachars + patrón destructivo → bloquea
4. Si no hay metachars → permite (incluso si es peligroso)

**Escenario de ataque:** `format C: /Y` — no tiene metachars, no está en DESTRUCTIVE_PATTERNS (busca "format" pero el patrón es exactamente "format" sin espacios — `format C:` contiene "format" sí). Realmente:
- `DESTRUCTIVE_PATTERNS` incluye `"format"` — esto detecta `format C: /Y`. OK.
- Pero `del /F /S C:\*` — `"del "` con espacio al final detecta. OK.
- `wevtutil cl system` — `"wevtutil cl"` detecta. OK.
- `echo malicioso > archivo` — sin metachars (">" SÍ es metachar), `SHELL_METACHARS` tiene `>` y `<`. Entonces detecta metachar + busca patrón destructivo. No hay patrón destructivo en `echo >`. ¿Permitiría `echo > C:\Windows\system.ini`? El comando `echo > archivo` con > es redirección. Los metachars incluyen `>`. Pero no hay patrón destructivo matching. Entonces:
  - `has_metachars = True` (por `>`)
  - Busca DESTRUCTIVE_PATTERNS en "echo malicioso > archivo"... no hay match
  - `is_allowed_builtin = True` (echo está en ALLOWED_SAFE_CMDS)
  - `has_metachars and not is_allowed_builtin` → `True and False` → no bloquea por metachar
  - **PASA LA VALIDACIÓN**

Este es un problema: `echo` está en ALLOWED_SAFE_CMDS, entonces aunque tenga metachars y haga algo destructivo, se permite.

### 5.7 Seguridad de plugins

El sistema de plugins ejecuta hooks arbitrarios:
```python
# executor_service.py:122
plugin_results = self._plugins.run_hook("on_command", command=command, classification=classification)
```

Un plugin puede:
- Ejecutar código arbitrario Python
- Modificar comandos antes de ejecutarlos
- Retornar resultados falsos
- Acceder a cualquier recurso del proceso

No hay sandboxing, no hay limitación de permisos, no hay verificación de plugins.

---

## 6. Product Analysis — Honestidad

### 6.1 ¿Por qué una empresa COMPRARÍA Sentinel hoy?

1. **Seguridad por diseño en ejecución de AI.** El pipeline Intent → Decision → Policy es único. Productos como GitHub Copilot, Claude's computer use, y OpenAI's code interpreter ejecutan sin este nivel de control.

2. **Audit trail completo.** Cada ejecución registra intención, decisión, riesgo, y resultado. Esto es valioso para SOC2, SOX, ISO 27001.

3. **On-premise / offline.** No depende de la nube para funcionalidad core (monitoreo, filesystem, executor). Crítico para entornos con datos sensibles.

4. **Multi-nivel de permisos simple.** View / Confirm / Auto / Admin es fácil de entender y comunicar a auditors.

### 6.2 ¿Por qué una empresa lo IGNORARÍA?

1. **Inmadurez.** Puntuación 4.9/10 en madurez arquitectónica. Empresas no compran plataformas inmaduras para Trust Layer — es demasiado crítico.

2. **Sin documentación.** No hay manual de usuario, guía de despliegue, ni docs de API para el producto. Solo código.

3. **Sin instalación enterprise.** No hay Docker image, no hay Helm chart, no hay MSI installer. Solo `pip install` + `npm run`.

4. **Sin multi-tenencia.** Un solo usuario "local". Esto excluye casos de uso enterprise.

5. **Confusión de producto.** ¿Es un dashboard? ¿Un chatbot? ¿Un Trust Layer? La presencia de Dashboard (monitoreo), Chat (conversación), y Sentinel (Trust Layer) en el mismo producto diluye el mensaje.

6. **Sin certificaciones.** No hay SOC2, no hay compliance documentation.

### 6.3 Diferenciador más fuerte

El pipeline **Intent → Decision → Policy → ToolGateway → Execution → Audit** para ejecución de AI en sistema local. Es el único producto que hace esto de forma nativa para Windows.

### 6.4 Capacidades que son DISTRACCIONES

1. **Dashboard de monitoreo** — CPU/RAM/Disk. Toda herramienta tiene esto. No es diferencial.
2. **Voice TTS** — Cero relación con Trust Layer. Eliminar.
3. **Chat** — Confunde el posicionamiento. Si es Trust Layer, la interfaz debe ser Sentinel, no Chat.
4. **Fleet** — Remoto. Prematuro. No hay caso de uso validado.
5. **Proactive suggestions** — "AI butler" es lo opuesto a Trust Layer. Trust Layer AUTHORIZA, no SUGIERE.
6. **Plugins (automation)** — Si los plugins son para automatización general, son distracción. Si son para políticas de seguridad personalizadas, son core.

### 6.5 Dilema fundamental

Sentinel tiene una **identidad dividida**:

```
Producto actual:   Panel de control + AI chatbot + Trust Layer
                    (hace todo, nada bien)

Producto deseado:  Trust Layer para AI agents
                    (una cosa, excelente)
```

Cada línea de código de Dashboard, Monitor, Chat, Voice, Fleet, y Proactive que se mantiene es una **deuda de identidad** que diluye el mensaje del producto.

---

## 7. Long-Term Architecture — Enterprise Readiness

### 7.1 ¿Sobreviviría la arquitectura actual a escala enterprise?

**No.** Rotundamente no.

| Requisito Enterprise | ¿Soporta hoy? | Por qué no |
|---------------------|--------------|------------|
| 10,000+ endpoints | ❌ | Monolítico Python, sin escalado horizontal |
| Multi-AI provider failover | ⚠️ Parcial | ModelRouter existe pero sin health checks |
| RBAC (roles + grupos) | ❌ | Solo 4 niveles planos, sin grupos |
| SSO / LDAP / OAuth | ❌ | Solo `x-user-id` header |
| Base de datos centralizada | ❌ | SQLite local, no PostgreSQL |
| Alta disponibilidad | ❌ | Single process, sin replica |
| API versionada | ❌ | `/api/*` sin versión |
| Rate limiting por usuario | ❌ | Por IP, no por identidad |
| Compliance auditing | ❌ | Audit trail local, no exportable |
| Despliegue Docker/K8s | ❌ | No hay container image |
| Policy-as-code | ❌ | Políticas hardcodeadas en Python |
| Plugin sandboxing | ❌ | Plugins con acceso total al proceso |

### 7.2 ¿Por qué no sobrevive?

1. **Monolito en un solo proceso.** Todo (API, proactive engine, plugins) corre en un proceso uvicorn. Un crash del proactive engine tira todo.

2. **Sin event bus.** No hay comunicación asíncrona entre componentes. Proactive engine no puede emitir eventos que otros componentes consuman.

3. **Singletons globales.** `PENDING_ACTIONS`, `EMERGENCY_STOP`, `_gateway` son mutables y globales. Imposible de escalar horizontalmente.

4. **Sin aislamiento de plugins.** Cualquier plugin puede hacer `os.system("rm -rf /")`.

5. **Sin API gateway.** No hay throttling, autenticación externa, ni logging centralizado de API.

6. **Persistencia local.** SQLite no escala. No hay migración a PostgreSQL.

### 7.3 ¿Qué habría que cambiar para enterprise?

No es solo refactor — es **re-arquitectura**:

```
HOY:                  MAÑANA (enterprise):

Monolith              →  Microservices (o modular monolith con procesos separados)
Sync HTTP             →  Event bus (RabbitMQ / NATS / Redis Streams)
SQLite                →  PostgreSQL + migraciones manejadas
Env vars              →  Config server (Consul / etcd)
Single user           →  OAuth2 + RBAC + multi-tenant
Local plugins         →  Wasm sandbox + plugin registry
Local audit           →  Audit stream → SIEM (Splunk, ELK)
Manual deploy         →  Docker + Helm + K8s
No health checks      →  /health, /ready, /metrics (Prometheus)
No tracing            →  OpenTelemetry
```

**Pero esto es premature optimization.** Para el estado actual del proyecto (4.9/10), enterprise readiness no es el objetivo inmediato. El objetivo inmediato es:

> **Ser un Trust Layer funcional, bien arquitectado, y demostrable para AI agents en un solo equipo.**

Enterprise readiness es para FASE 9+.

---

## 8. Impacto en el Plan de Migración

### 8.1 Lo que el plan original hizo BIEN

1. **Orden incremental.** FASE 0 (freeze) → FASE 1 (identity) → FASE 2 (policies) es lógico.
2. **Cada fase incluye rollback y tests.** Esto es profesional.
3. **FASE 5 (Quality Gate)** es correcta y necesaria.
4. **FASE 6 (storage)** es correcta pero debe ser la última.

### 8.2 Lo que el plan original debe CAMBIAR

| Aspecto | Plan original | Debe cambiar a |
|---------|---------------|----------------|
| **Prioridad de FASE 3** | Después de FASE 2 | **Antes de FASE 2.** Los bypasses de ejecución son la violación más crítica del Trust Layer. Identity unification (FASE 1) debe preceder, pero FASE 3 debe ser inmediatamente después. |
| **FASE 4 (adapters)** | "Absorber services en adapters" | Repensar. La solución correcta NO es mover services a adapters. Es hacer que `services` implementen `Tool` directamente. O: convertir services en implementaciones Tool y eliminar adapters. |
| **Módulos opcionales** | No mencionado | Necesitamos una FASE para **separar módulos core de opcionales.** Voice, Fleet, Proactive, Monitor deben ser desactivables. |
| **Identidad dividida (producto)** | No mencionado | La confusión Chat vs Sentinel vs Dashboard debe resolverse a nivel de producto. El plan de migración técnico no puede ignorar esto. |
| **Plugin safety** | No mencionado | Debería ser una sub-fase de seguridad. |
| **Event Bus** | No mencionado | No es urgente, pero debe estar en roadmap (FASE 7+). |
| **Eliminar voice** | "Absorber servicios" | Voice debe ser **eliminado**, no migrado. Es código muerto. |

### 8.3 Orden revisado recomendado

```
FASE 0 — Freeze (sin cambios)
FASE 1 — Identity unification (sin cambios)
FASE 3 — Mandatory flow (mover a posición 2 — crítico para Trust Layer)
FASE 2 — Single policy source (mover a posición 3 — dependencies ok)
FASE 3b— Module separation (NUEVA: core vs optional)
FASE 5 — Quality Gate (sin cambios)
FASE 4 — Service/Adapter resolution (modificado: services implement Tool)
FASE 6 — Storage consolidation (sin cambios)
FASE 7+ — Event Bus, Plugin Sandbox, Multi-user (futuro)
```

### 8.4 Lo que NO debe cambiar del plan original

1. Principios rectores ✅
2. Cada fase incluye archivos exactos, riesgo, rollback, tests ✅
3. Prohibición de rewrites grandes ✅
4. Backward compatibility ✅
5. Feature flags y deprecation ✅

---

## 9. Decisión

El plan de migración actual (`SENTINEL_TRUST_LAYER_MIGRATION_v1.0.md`) es **técnicamente sólido pero incompleto desde la perspectiva de producto.**

### Aprobado para continuar:

✅ FASE 0 — Freeze architecture
✅ FASE 1 — Unify IdentityContext
✅ FASE 2 — Single policy source
✅ FASE 5 — Quality Gate
✅ FASE 6 — Storage consolidation (con observaciones)

### Requiere revisión:

⚠️ FASE 3 — Mandatory flow: debe priorizarse (FASE 1.5, no FASE 3)
⚠️ FASE 4 — Service/Adapter resolution: cambiar estrategia (services → Tool, no adapters → services)

### Falta agregar:

➕ FASE 3b — Module separation (core vs optional, eliminar voice)
➕ FASE 7+ — Event Bus, Plugin Sandbox, Multi-user (roadmap futuro)

### Recomendación final:

Proceder con FASE 0 (freeze + backup) para establecer la línea base.
Durante FASE 0, revisar este reporte y ajustar el plan de migración según las decisiones de producto.
No comenzar FASE 1 hasta que el plan revisado sea aprobado.

---

*Fin del reporte de razonamiento arquitectónico.*
