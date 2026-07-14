# SENTINEL TRUST LAYER — Migration Plan v1.0

**Autor:** Arquitectura
**Estado:** Borrador
**Objetivo:** Transformar AIVO/Sentinel de un panel de control con IA a una **Capa de Confianza (Trust Layer)** entre agentes de IA y el sistema operativo.

---

## Principios rectores

1. **Nunca IA → OS directo.** Toda ejecución pasa por: Intent → Decision → Policy → Gateway → Execution → Audit.
2. **Una sola fuente de verdad** para identidad, políticas, patrones destructivos y almacenamiento.
3. **Cambios incrementales, retrocompatibles.** Cada FASE debe poder hacerse sin romper la versión anterior.
4. **Cero bypass.** No debe existir ningún camino que omita el pipeline de seguridad.
5. **Calidad a la salida.** Tanto como a la entrada.

---

## FASE 0 — Congelar arquitectura actual

**Objetivo:** Establecer línea base, backup, interfaces documentadas.

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| Todo el repositorio | Crear tag git `pre-trust-layer-v1.0` |
| `sentinel/docs/` | Generar `current-interface-catalog.md` |
| `AGENTS.md` (raíz) | Documentar comandos de build/test/lint actuales |

### Cambios necesarios

1. `git tag pre-trust-layer-v1.0 && git push --tags`
2. Ejecutar suite completa: `pytest sidecar/tests/ sentinel/tests/` — registrar resultado (603 tests).
3. Generar catálogo de interfaces públicas:
   - Módulos: `sidecar/modules/__init__.py` → `get_gateway()`, `register_*()`, `init_*()`
   - Routers: todos los `APIRouter` en `sidecar/modules/*.py`
   - Core: todas las clases exportadas en `sentinel/core/__init__.py`
   - Servicios: todos los métodos públicos en `sidecar/services/*.py`
   - Adaptadores: todos los `Tool` en `sentinel/adapters/*.py`
   - Frontend: todos los métodos en `src/api.ts`
   - Tipos: `src/types.ts`
4. Crear `CURRENT_INTERFACES.md` con firmas exactas (args, returns, excepciones).
5. Backup adicional: copia ZIP del directorio `sidecar/` y `sentinel/`.

### Riesgo: BAJO

No se modifica código de producción. Solo documentación y tags.

### Rollback

`git checkout pre-trust-layer-v1.0`

### Tests requeridos

- Suite completa: **603 tests deben pasar**.
- No se agregan tests nuevos (fase de congelación).

---

## FASE 1 — Unificar IdentityContext

**Objetivo:** Eliminar la dualidad `AuthContext` ↔ `IdentityContext`. Un solo identity canonical.

### Diagnóstico actual

- `sidecar/modules/auth.py:45-48` define `IdentityContext` (frozen, con metadata: ip, user_agent, timestamp)
- `sidecar/modules/security/interfaces.py:6-9` define `AuthContext` (mutable, user_id, client_id, session_id)
- `sidecar/modules/executor.py:30-35` construye `AuthContext` manualmente desde headers
- `sidecar/modules/filesystem.py:21-26` idem
- `sentinel/adapters/executor_tool.py` pasa `context["auth"]` → `self._svc.execute(..., auth)`
- `sentinel/adapters/filesystem_tool.py` pasa `context["auth"]` → `self._svc.read_file(..., auth)`
- `sidecar/services/executor_service.py` recibe `auth` en execute() pero no lo usa realmente
- `sidecar/services/filesystem_service.py` recibe `auth` y lo pasa a PathGuardian

### Archivos afectados

| Archivo | Acción | Líneas clave |
|---------|--------|--------------|
| `sidecar/modules/auth.py` | **MODIFICAR**: agregar `user_id`, `client_id`, `session_id` a IdentityContext; hacerlo el único identity | 45-48 |
| `sidecar/modules/security/interfaces.py` | **DEPRECAR**: AuthContext → alias de IdentityContext; agregar `UserWarning` | 6-9 |
| `sidecar/modules/executor.py` | **MODIFICAR**: reemplazar `_auth()` por `request.state.identity` | 30-35 |
| `sidecar/modules/filesystem.py` | **MODIFICAR**: reemplazar `_auth()` por `request.state.identity` | 21-26 |
| `sidecar/modules/security/path_guardian.py` | **MODIFICAR**: `validate_*()` aceptar `IdentityContext` en vez de `AuthContext` | 21-47 |
| `sidecar/services/executor_service.py` | **MODIFICAR**: parámetro `auth` → `identity: IdentityContext` | 67-68 |
| `sidecar/services/filesystem_service.py` | **MODIFICAR**: parámetro `auth` → `identity: IdentityContext` | 21, 44, 64 |
| `sentinel/adapters/executor_tool.py` | **MODIFICAR**: `context["auth"]` → `context.get("identity")` | 49, 62 |
| `sentinel/adapters/filesystem_tool.py` | **MODIFICAR**: `context["auth"]` → `context.get("identity")` | 83, 99, 116, 135 |
| `sidecar/tests/test_auth_authorization.py` | **AGREGAR**: tests de propagación de IdentityContext por el pipeline | nuevo |
| `sidecar/tests/test_executor.py` | **MODIFICAR**: fixtures usan `IdentityContext` en vez de `AuthContext` | — |
| `sidecar/tests/test_filesystem.py` | **MODIFICAR**: fixtures usan `IdentityContext` | — |

### Cambios detallados

**Paso 1** — Expandir IdentityContext en `auth.py`:

```
IdentityContext:
  user_id: str = "local"
  client_id: str = "unknown"
  session_id: str = ""
  ip_address: str = ""
  user_agent: str = ""
  timestamp: str  (ISO format, auto)
```

**Paso 2** — Migrar `AuthContext`:

```python
# sidecar/modules/security/interfaces.py
import warnings
from modules.auth import IdentityContext

AuthContext = IdentityContext  # alias retrocompatible
warnings.warn("AuthContext is deprecated, use IdentityContext", DeprecationWarning, stacklevel=2)
```

**Paso 3** — En `executor.py` y `filesystem.py`:

```python
# Antes
def _auth(request):
    return AuthContext(
        user_id=request.headers.get("x-user-id", "local"),
        ...
    )

# Después
# Usar directamente: request.state.identity (inyectado por auth_middleware)
# Eliminar función _auth()
```

**Paso 4** — En PathGuardian: cambiar type hints de `AuthContext` a `IdentityContext`.

### Riesgo: MEDIO

- `AuthContext` es usado por `PathGuardian` que controla acceso a archivos. Un error de mapeo de campos podría bloquear operaciones legítimas.
- `IdentityContext` es frozen; `AuthContext` es mutable. Cualquier código que mute `AuthContext` romperá.

### Rollback

```
git revert HEAD -- sidecar/modules/auth.py sidecar/modules/security/interfaces.py
git revert HEAD -- sidecar/modules/executor.py sidecar/modules/filesystem.py
# Mantener import de AuthContext en services por una release
```

O más seguro: mantener `AuthContext` como clase separada pero que herede de `IdentityContext`, ofreciendo ambas interfaces durante 1 release.

### Tests requeridos

- ✅ Unitario: `IdentityContext` se construye correctamente desde request
- ✅ Unitario: `auth_middleware` inyecta `request.state.identity` en todas las rutas
- ✅ Unitario: `IdentityContext` actualiza `timestamp` en cada request
- ✅ Integración: `POST /api/executor/command` propaga identity al servicio
- ✅ Integración: `POST /api/fs/read` propaga identity a PathGuardian
- ✅ Retrocompatibilidad: código legacy que usa `AuthContext` funciona con `DeprecationWarning`
- ✅ **603 tests existentes siguen pasando** (ningún test debe romperse, solo cambiar imports)

---

## FASE 2 — Fuente única de políticas

**Objetivo:** Eliminar la triple definición de `DESTRUCTIVE_PATTERNS` y centralizar todas las políticas de seguridad.

### Diagnóstico actual

| Archivo | Constante | Valores |
|---------|-----------|---------|
| `sidecar/services/executor_service.py:18-23` | `DESTRUCTIVE_PATTERNS` | 16 patterns |
| `sidecar/services/permissions_service.py:7-12` | `DESTRUCTIVE_PATTERNS` | 12 patterns (faltan 4 vs executor: `rmdir`, `erase`, `rd`, `move`, `ren`, `rename-item`, `copy`) |
| `sentinel/adapters/executor_tool.py:7-11` | `FILE_DESTRUCTIVE_PATTERNS` | 10 patterns (diferente propósito, subset para operaciones de archivo) |
| `sidecar/services/permissions_service.py:14-17` | `CRITICAL_PATHS` | 4 paths protegidos |
| `sidecar/modules/security/path_policy.py` | `get_blocked_paths()`, `is_sensitive_filename()`, etc. | Reglas de path |
| `sidecar/modules/__init__.py:68-99` | `init_policies()` | Mapeo permisos → módulos |

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| `sentinel/policies/__init__.py` | **CREAR**: exportar todo desde aquí |
| **CREAR: `sentinel/policies/patterns.py`** | Fuente única de DESTRUCTIVE_PATTERNS, CRITICAL_PATHS, FILE_DESTRUCTIVE_PATTERNS |
| `sentinel/policies/security_policies.py` | **MODIFICAR**: importar patterns desde `patterns.py` en vez de definir localmente |
| `sidecar/services/executor_service.py` | **MODIFICAR**: eliminar definición local, importar desde `sentinel.policies.patterns` |
| `sidecar/services/permissions_service.py` | **MODIFICAR**: eliminar definición local, importar desde `sentinel.policies.patterns` |
| `sentinel/adapters/executor_tool.py` | **MODIFICAR**: eliminar `FILE_DESTRUCTIVE_PATTERNS`, importar desde `sentinel.policies.patterns` |
| `sidecar/modules/security/path_policy.py` | **MODIFICAR**: unificar con `sentinel/policies/patterns.py` o importar desde allí |

### Cambios detallados

**`sentinel/policies/patterns.py`** (nuevo):

```python
# Única fuente de verdad para patrones de seguridad

DESTRUCTIVE_PATTERNS: list[str] = [
    "rm ", "del ", "format", "shutdown", "reboot",
    "restart-computer", "stop-computer", "Remove-Item",
    "Clear-Content", "net user", "reg delete", "diskpart",
    "cleanmgr /sageset", "taskkill /f", "set-executionpolicy",
    "wevtutil cl", "cipher /w",
    "rd ", "rmdir", "erase", "copy ", "move ", "ren ",
    "rename-item",
]

FILE_DESTRUCTIVE_PATTERNS: list[str] = [
    "rm ", "del ", "Remove-Item", "Clear-Content",
    "copy ", "move ", "ren ", "rename-item",
    "erase", "rd ", "rmdir",
]

CRITICAL_PATHS: list[str] = [
    "C:\\Windows\\System32", "C:\\Windows",
    "C:\\Program Files",
    "~\\AppData",
]

ALLOWED_SAFE_CMDS: set[str] = {
    "dir", "ls", "echo", "type", "find", "more", "help",
    "cd", "pwd", "whoami", "ipconfig", "systeminfo",
    "tasklist", "netstat", "ver", "date", "time", "cls",
    "clear", "tree", "set", "path", "chcp",
}
```

Cada archivo cliente hace:
```python
# Antes
DESTRUCTIVE_PATTERNS = ["rm ", "del ", ...]

# Después  
from sentinel.policies.patterns import DESTRUCTIVE_PATTERNS
```

### Riesgo: BAJO

- Es puramente mover constantes. El comportamiento no cambia si los imports son correctos.
- Riesgo de que falte un pattern durante la migración. Mitigación: comparar diff de las tres listas y asegurar que la unificada contenga **todas**.
- `FILE_DESTRUCTIVE_PATTERNS` es un subset intencional — debe mantenerse separado en el archivo fuente pero desde el mismo lugar.

### Rollback

```python
# Revertir imports, restaurar definiciones locales
# O: mantener import con fallback
try:
    from sentinel.policies.patterns import DESTRUCTIVE_PATTERNS
except ImportError:
    DESTRUCTIVE_PATTERNS = ["rm ", "del ", ...]  # fallback
```

### Tests requeridos

- ✅ Unitario: `sentinel/policies/patterns.py` exporta todas las constantes esperadas
- ✅ Unitario: `executor_service.DESTRUCTIVE_PATTERNS is sentinel.policies.patterns.DESTRUCTIVE_PATTERNS` (misma identidad)
- ✅ Unitario: `executor_tool.FILE_DESTRUCTIVE_PATTERNS is sentinel.policies.patterns.FILE_DESTRUCTIVE_PATTERNS`
- ✅ Parametrizado: cada patrón en las listas anteriores sigue clasificando comandos igual que antes
- ✅ Integración: `POST /api/executor/command` con patrón destructivo es bloqueado (igual que antes)
- ✅ **603 tests existentes pasan sin modificación** (solo cambian imports)

---

## FASE 3 — Flujo obligatorio: Intent → Decision → Policy → Gateway → Execution → Audit

**Objetivo:** Garantizar que NO exista ningún camino de ejecución que omita el pipeline completo de Sentinel.

### Diagnóstico actual

Rutas de ejecución actuales:

```
Ruta A (Sentinel):  Frontend → POST /api/sentinel/process → Orchestrator.process() →
                    IntentEngine → Planner → DecisionEngine → ToolGateway → Tool → OS
                    ✅ Completa (intent + decision + policy + audit)

Ruta B (Dashboard): Frontend → POST /api/executor/command → executor.run_command() →
                    ToolGateway.execute() → PolicyEngine → Tool → OS
                    ❌ Sin IntentEngine (no hay parseo de intención)
                    ❌ Sin DecisionEngine (no hay risk scoring)
                    ❌ Sin Planner (ejecución directa)
                    ✅ PolicyEngine (vía gateway)
                    ✅ Audit (vía executor_service._log_action)

Ruta C (Files):     Frontend → POST /api/fs/read → filesystem.read_file() →
                    ToolGateway.execute() → PolicyEngine → Tool → OS
                    ❌ Sin IntentEngine
                    ❌ Sin DecisionEngine
                    ❌ Sin Planner
                    ✅ PolicyEngine
                    ❌ Audit (filesystem_service no audita lecturas)
```

El Dashboard expone botones que llaman `api.executor.command("cleanmgr")`, `api.executor.launch("cmd.exe")` — ejecutan herramientas del sistema sin pasar por el pipeline de Sentinel.

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| `src/components/Dashboard/Dashboard.tsx` | **MODIFICAR**: reemplazar `api.executor.command()` por `api.sentinel.process()` con intent predefinido |
| `src/api.ts` | **MODIFICAR**: deprecar `executor.command()`, `executor.launch()`, `executor.kill()` |
| `sidecar/modules/executor.py` | **MODIFICAR**: agregar advertencia/log cuando se llama sin pasar por sentinel; o redirigir internamente |
| `sidecar/modules/filesystem.py` | **MODIFICAR**: idem |
| `sidecar/modules/sentinel_bridge.py` | **MODIFICAR**: exponer endpoint `/process-quick` para acciones rápidas pre-aprobadas |
| `sidecar/main.py` | **MODIFICAR**: agregar middleware de validación de flujo |
| `sentinel/core/orchestrator.py` | **MODIFICAR**: exponer método `process_quick(action, target, params)` para acciones sin NLP |

### Cambios detallados

**Paso 1** — En el frontend, las acciones rápidas del Dashboard se convierten en intents predefinidos:

```typescript
// Dashboard.tsx — antes
<button onClick={() => api.executor.command("cleanmgr")}>Clean Disk</button>

// Dashboard.tsx — después
<button onClick={() => api.sentinel.process("run system tool: cleanmgr")}>Clean Disk</button>
```

Esto fuerza el pipeline completo: intent parsing → "system.clean" → decision → risk score → policy → execution → audit.

**Paso 2** — Opcionalmente, crear `POST /api/sentinel/quick-action` para acciones pre-aprobadas de bajo riesgo:

```json
POST /api/sentinel/quick-action
{
  "action": "executor.command",
  "params": { "command": "cleanmgr" },
  "risk_level": "low"
}
```

El Orchestrator procesa sin NLP (skip IntentEngine) pero con PolicyEngine + DecisionEngine + Audit.

**Paso 3** — Los routers directos (`executor.py`, `filesystem.py`) registran `DeprecationWarning` en el log y redirigen internamente al gateway con `skip_intent=True` (pero sin saltar policies ni audit).

### Riesgo: ALTO

- Cambiar los botones del Dashboard afecta UX directamente. Si el pipeline de Sentinel falla, las acciones rápidas dejan de funcionar.
- `sentinel.process()` depende del IntentEngine que puede malinterpretar "cleanmgr" como "clean memory" vs "run disk cleanup".
- Solución: usar intents predefinidos con `quick-action` endpoint que evita NLP pero mantiene risk scoring + policies.

### Rollback

```typescript
// Frontend: feature flag
const USE_SENTINEL_FLOW = localStorage.getItem("use_sentinel_flow") === "true";
if (USE_SENTINEL_FLOW) {
  await api.sentinel.process(text);
} else {
  await api.executor.command(cmd);  // ruta legacy
}
```

En backend: mantener ambos routers funcionales durante al menos 2 releases.

### Tests requeridos

- ✅ Unitario: `Orchestrator.process_quick()` ejecuta con risk scoring pero sin NLP
- ✅ Integración: `POST /api/sentinel/quick-action` ejecuta comando y registra en audit
- ✅ Integración: `POST /api/executor/command` emite `DeprecationWarning` pero sigue funcionando
- ✅ E2E: Dashboard → Clean Disk button → pasa por sentinel pipeline → comando ejecutado
- ✅ Security: intentar bypass via `POST /api/executor/command` directamente es registrado como warning
- ✅ **603 tests existentes**: algunos pueden romperse si los tests de executor esperan respuestas directas. MODIFICAR tests para usar el nuevo flujo.

---

## FASE 4 — Resolver dualidad: `sentinel/adapters/` vs `sidecar/services/`

**Objetivo:** Eliminar la capa duplicada. Una sola implementación de cada herramienta.

### Diagnóstico actual

```
sentinel/adapters/executor_tool.py:
  ExecutorCommandTool.execute(params, context) → self._svc.execute(command, ...)
  
sidecar/services/executor_service.py:
  ExecutorService.execute(command, timeout, confirmed, action_id) → dict

sentinel/adapters/filesystem_tool.py:
  FilesystemReadTool.execute(params, context) → self._svc.read_file(path, auth)
  
sidecar/services/filesystem_service.py:
  FilesystemService.read_file(path, auth) → dict
```

Los adapters NO agregan lógica de dominio significativa. Son wrappers de 3-10 líneas cada uno que convierten `params` dict → kwargs posicionales.

### Estrategia: Absorber servicios en adapters

En lugar de tener dos capas, mover la lógica de `sidecar/services/*.py` DENTRO de `sentinel/adapters/*.py`. Los adapters se convierten en la implementación real. Para módulos sin contraparte en sentinel (monitor, plugins, voice, fleet), mantener services como están pero apuntar a migrarlos en FASE 6.

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| `sentinel/adapters/executor_tool.py` | **ABSORBER**: inlinear lógica de `ExecutorService` (validate, classify, execute, kill, launch) |
| `sentinel/adapters/filesystem_tool.py` | **ABSORBER**: inlinear lógica de `FilesystemService` |
| `sentinel/adapters/system_adapter.py` | **REVISAR**: ya es autosuficiente (usa psutil directamente) |
| `sidecar/services/executor_service.py` | **DEPRECAR**: redirigir a `sentinel/adapters/executor_tool` |
| `sidecar/services/filesystem_service.py` | **DEPRECAR**: redirigir a `sentinel/adapters/filesystem_tool` |
| `sidecar/modules/executor.py` | **MODIFICAR**: importar desde `sentinel.adapters` en vez de `services` |
| `sidecar/modules/filesystem.py` | **MODIFICAR**: importar desde `sentinel.adapters` |
| `sidecar/modules/__init__.py` | **MODIFICAR**: `register_tools()` ya usa adapters, actualizar imports |
| `sidecar/main.py` | **MODIFICAR**: `wire_dependencies()` cambia según nueva estructura |
| `sidecar/tests/test_executor_service.py` | **RENOMBRAR / ACTUALIZAR**: tests se mueven a `sentinel/tests/` |

### Cambios detallados

**Adapter final** (ej. `executor_tool.py`):

```python
class ExecutorCommandTool(Tool):
    def __init__(self, guardian=None):
        self._guardian = guardian or PathGuardian()
        self._audit = None  # inyectado externamente
        self._perm = None
    
    def set_dependencies(self, audit_svc, perm_svc):
        self._audit = audit_svc
        self._perm = perm_svc
    
    async def execute(self, params, context):
        # TODO: FASE 2 — import desde sentinel.policies.patterns
        command = self.validate_command(params["command"])
        # TODO: FASE 1 — context.get("identity") en vez de context.get("auth")
        ...
```

**Services deprecados**:

```python
# sidecar/services/executor_service.py
import warnings
from sentinel.adapters.executor_tool import ExecutorCommandTool

warnings.warn("sidecar.services is deprecated, use sentinel.adapters", DeprecationWarning)

# Mantener clase como wrapper por 1 release
class ExecutorService:
    def __init__(self, *args, **kwargs):
        self._tool = ExecutorCommandTool()
    def execute(self, *args, **kwargs):
        return self._tool.execute({"command": args[0]}, {})
```

### Riesgo: ALTO

- Es el cambio estructural más grande del plan.
- `executor_service.py` tiene 246 líneas con lógica de validación, ejecución, plugin hooks, y logging.
- `filesystem_service.py` tiene 142 líneas con PathGuardian, audit.
- Mover toda esa lógica requiere cuidado extremo para no romper nada.
- Las dependencias circulares son posibles si `modules/` y `adapters/` se referencian mutuamente.

### Rollback

```python
# Mantener imports duales
try:
    from sentinel.adapters.executor_tool import ExecutorCommandTool
    _svc = ExecutorCommandTool()  # nuevo
except ImportError:
    from services.executor_service import ExecutorService
    _svc = ExecutorService()  # legacy
```

### Tests requeridos

- ✅ Para cada herramienta: test de humo que ejecute `execute()` y retorne el mismo resultado que antes
- ✅ Comparación de outputs: ejecutar en paralelo adapter nuevo vs service legacy, verificar igualdad
- ✅ Integración: `POST /api/executor/command` produce mismo resultado con adapter absorbido
- ✅ Plugin hooks siguen funcionando (el adapter debe llamar a `_svc._run_plugin_hooks` o a plugins_service directamente)
- ✅ **603 tests existentes**: los tests de `sidecar/tests/test_executor_service*` deben migrarse a `sentinel/tests/`

---

## FASE 5 — Crear Quality Gate

**Objetivo:** Validar no solo lo que entra (inputs, comandos) sino también lo que sale (outputs, datos).

### Diagnóstico actual

- `executor_service.py:142-161` ejecuta comando y retorna stdout/stderr **sin filtrar**
- `filesystem_service.py` lee archivos y retorna contenido **sin analizar**
- Cualquier comando puede exponer información sensible (passwords en procesos, tokens en archivos, etc.)
- No hay sanitización de output a ningún nivel

### Arquitectura propuesta

```
ToolGateway.execute()
  → PolicyEngine.evaluate()       # control de entrada (existente)
  → tool.execute()                 # ejecución (existente)
  → QualityGate.evaluate()         # ★ NUEVO: control de salida
    → output result or error
```

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| **CREAR: `sentinel/core/quality_gate.py`** | Implementación de QualityGate |
| **CREAR: `sentinel/policies/output_policies.py`** | Reglas de filtrado de output |
| `sentinel/core/tool_gateway.py` | **MODIFICAR**: agregar paso de QualityGate después de `tool.execute()` |
| `sentinel/core/tool.py` | **MODIFICAR**: agregar hook `validate_output()` opcional en Tool |
| `sentinel/core/orchestrator.py` | **MODIFICAR**: integrar QualityGate a nivel de pipeline |
| `sentinel/core/__init__.py` | **MODIFICAR**: exportar QualityGate |
| `sentinel/tests/test_quality_gate.py` | **CREAR**: tests completos |

### Cambios detallados

**`sentinel/core/quality_gate.py`**:

```python
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class QualityVerdict:
    passed: bool
    reason: Optional[str] = None
    sanitized_output: Optional[Any] = None
    risk_level: str = "low"

class QualityGate:
    def __init__(self):
        self._rules = []
    
    def register_rule(self, rule):
        self._rules.append(rule)
    
    async def evaluate(self, tool_id: str, params: dict, output: Any,
                       context: dict) -> QualityVerdict:
        for rule in self._rules:
            verdict = await rule.check(tool_id, params, output, context)
            if not verdict.passed:
                return verdict
        return QualityVerdict(passed=True)
```

**Reglas iniciales** (`sentinel/policies/output_policies.py`):

```python
# No exponer patrones de clave/token en output
SENSITIVE_PATTERNS = [
    r'(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*["\']?\w{8,}["\']?',
    r'(?i)(sk-[a-zA-Z0-9]{20,})',  # OpenAI keys
    r'(?i)(ghp_[a-zA-Z0-9]{36})',   # GitHub tokens  
    r'(?i)(-----BEGIN (RSA |EC )?PRIVATE KEY-----)',
]

MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB

class SensitiveDataRule:
    async def check(self, tool_id, params, output, context):
        if isinstance(output, dict):
            text = str(output.get("stdout", "") + output.get("stderr", ""))
        elif isinstance(output, str):
            text = output
        else:
            return QualityVerdict(passed=True)
        
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                redacted = re.sub(pattern, "***REDACTED***", text)
                return QualityVerdict(
                    passed=True,
                    sanitized_output=redacted,
                    risk_level="medium",
                    reason=f"Sensitive data pattern matched in output: {pattern[:30]}..."
                )
        return QualityVerdict(passed=True)
```

### Riesgo: MEDIO

- Falsos positivos: `SENSITIVE_PATTERNS` puede redactar contenido legítimo (ej. una API key de ejemplo en documentación).
- Sobrecarga de rendimiento: escanear outputs grandes (multi-MB) en cada request afecta latencia.
- El output sanitizado puede corromperse si no se maneja bien la redacción.

### Rollback

```python
# En ToolGateway
try:
    verdict = await self._quality_gate.evaluate(tool_id, params, result, ctx)
except Exception:
    logger.warning("QualityGate failed, allowing raw output: %s", e)
    # Fallback: permitir output sin filtrar
```

Feature flag: `DISABLE_QUALITY_GATE=1` env var que salta el QualityGate completamente.

### Tests requeridos

- ✅ Unitario: `SensitiveDataRule` detecta patrones en stdout/stderr
- ✅ Unitario: `SensitiveDataRule` redacta sin modificar el resto del output
- ✅ Unitario: `SensitiveDataRule` NO da falsos positivos en texto normal
- ✅ Unitario: `MAX_OUTPUT_SIZE` trunca output excesivo
- ✅ Integración: `tool_gateway.execute()` con QualityGate activo
- ✅ Integración: QualityGate pasa output sanitizado de vuelta (no raw)
- ✅ Performance: escaneo de 10MB de output < 100ms
- ✅ **603 tests existentes pasan** (QualityGate es nuevo, no debe romper nada)

---

## FASE 6 — Consolidar almacenamiento

**Objetivo:** Unificar los múltiples backends de almacenamiento en una sola capa de datos.

### Diagnóstico actual

| Backend | Ubicación | Propósito | Formato |
|---------|-----------|-----------|---------|
| SQLite | `sidecar/repositories/database.py` | Config, migración JSON→SQLite | SQLite |
| InMemoryBackend | `sentinel/core/operational_memory.py` | Execution records (volátil) | Dict en RAM |
| Memory (SQLite) | `sentinel/core/memory.py` | Conversación | SQLite (archivo separado) |
| JSON files | `sidecar/repositories/*.py` | Datos legacy (migrados a SQLite) | JSON |
| PendingActionsDict | `sidecar/modules/permissions_memory.py` | Acciones pendientes | Dict en RAM con respaldo a OperationalMemory |
| EmergencyStopFlag | `sidecar/modules/permissions_memory.py` | Parada de emergencia | Lista[bool] con respaldo |

### Estrategia

1. **SQLite como único backend persistente.** Un solo archivo `.db` (ej. `~/.aivo/aivo.db`).
2. **InMemoryBackend → SQLiteBackend** para execution records (opcional: retener InMemory para tests).
3. **PendingActionsDict y EmergencyStopFlag** migran a SQLite con tabla `operational_state`.
4. **Eliminar archivos JSON** después de migración completa (FASE 6.2).

### Archivos afectados

| Archivo | Acción |
|---------|--------|
| `sidecar/repositories/database.py` | **MODIFICAR**: convertirse en `DataLayer` canónico; exponer métodos unificados |
| `sidecar/repositories/*.py` | **MODIFICAR**: eliminar backends JSON, usar solo DatabaseManager |
| `sentinel/core/operational_memory.py` | **MODIFICAR**: agregar `SQLiteBackend` además de `InMemoryBackend` |
| `sentinel/core/memory.py` | **MODIFICAR**: usar instancia de DB compartida en vez de SQLite propio |
| `sidecar/modules/permissions_memory.py` | **MODIFICAR**: `PendingActionsDict` usa tabla `pending_actions` en SQLite |
| `sidecar/main.py` | **MODIFICAR**: inicialización de DB única al startup |
| `sentinel/core/__init__.py` | **MODIFICAR**: exportar nuevo `SQLiteBackend` |
| `sidecar/modules/__init__.py` | **MODIFICAR**: pasar DB compartida a todos los módulos |
| `sidecar/tests/test_database.py` | **AGREGAR**: tests de migración y unificación |

### Cambios detallados

**Paso 1** — `database.py` se expande:

```python
class DataLayer:
    def __init__(self, db_path: str = "~/.aivo/aivo.db"):
        self._engine = create_engine(f"sqlite:///{expanduser(db_path)}")
        self._init_schema()
    
    def _init_schema(self):
        # Tablas: config, audit_log, operational_state, pending_actions,
        #         execution_records, conversation_memory, goals
        ...
    
    # Métodos unificados
    def store_execution(self, record): ...
    def get_last_execution(self): ...
    def store_pending_action(self, action): ...
    def get_config(self, key): ...
    def log_audit(self, entry): ...
```

**Paso 2** — `InMemoryBackend` en `operational_memory.py` se convierte en backend abstracto:

```python
class MemoryBackend(ABC):
    @abstractmethod
    def store_execution(self, record): ...
    @abstractmethod
    def get_last_execution(self): ...

class InMemoryBackend(MemoryBackend):
    # Para tests

class SQLiteBackend(MemoryBackend):
    def __init__(self, data_layer: DataLayer):
        self._db = data_layer
```

**Paso 3** — `permissions_memory.py`:

```python
class PendingActionsDict(UserDict):
    def __init__(self, data_layer=None):
        self._db = data_layer
        if self._db:
            self._load_from_db()
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self._db:
            self._db.store_pending_action(key, value)
```

### Riesgo: ALTO

- Migración de datos: pasar de archivos JSON + SQLite dispersos a un solo DB puede perder datos si la migración falla.
- Tiempo de migración: si hay miles de records de auditoría, la migración debe ser progresiva o tener un script dedicado.
- Compatibilidad hacia atrás: versión anterior no podrá leer el nuevo formato.

### Rollback

```python
# En database.py: mantener modo legacy
LEGACY_FALLBACK = os.environ.get("AIVO_LEGACY_STORAGE", "0") == "1"
if LEGACY_FALLBACK:
    # Usar repositorios JSON como antes
    ...
```

La migración debe ser **no destructiva**: los JSON originales no se eliminan hasta confirmar que el nuevo SQLite funciona correctamente (1 release de solapamiento).

### Tests requeridos

- ✅ Migración: script `test_migrate_json_to_sqlite()` — crea JSON de prueba, migra, verifica datos
- ✅ Integridad: migración de 1000+ audit records, verificar counts
- ✅ Unitario: `SQLiteBackend.store_execution()` + `get_last_execution()` = roundtrip exitoso
- ✅ Unitario: `PendingActionsDict` con respaldo SQLite persiste + recupera acciones
- ✅ Integración: reiniciar app, verificar que pending_actions sobreviven al reinicio
- ✅ Performance: SQLiteBackend < 10ms por operación
- ✅ **603 tests existentes**: modificar fixtures de tests para usar `InMemoryBackend` (rápido) en lugar de SQLite (lento)

---

## Resumen de riesgos por FASE

| FASE | Riesgo | Impacto | Tests nuevos | Cambio estructural |
|------|--------|---------|-------------|-------------------|
| 0 — Freeze | 🟢 Bajo | Ninguno | 0 | No |
| 1 — Identity | 🟡 Medio | Auth puede romperse | +6 suites | Sí (interfaces) |
| 2 — Policies | 🟢 Bajo | Mínimo | +4 suites | No |
| 3 — Flow | 🔴 Alto | UX + ejecución rota | +5 suites | Sí (pipeline) |
| 4 — Adapters | 🔴 Alto | Muchos archivos | +6 suites | Sí (estructural) |
| 5 — Quality Gate | 🟡 Medio | Falsos positivos | +5 suites | No |
| 6 — Storage | 🔴 Alto | Pérdida de datos | +5 suites | Sí (infraestructura) |

**Orden recomendado:** 0 → 2 → 1 → 5 → 3 → 4 → 6

- FASE 2 (bajo riesgo) prepara el terreno para FASE 3 y 4.
- FASE 5 puede ir antes de 3 y 4 porque es aditivo (no modifica existente).
- FASE 6 (riesgo alto) al final porque es la más disruptiva y se beneficia de tener las interfaces estables.

---

## Métricas de éxito

Al completar FASE 6:

1. **Zero bypass paths:** no existe ruta de ejecución que omita el pipeline completo.
2. **Single identity:** `IdentityContext` es la única representación de identidad en todo el código.
3. **Single policy source:** todas las listas de patrones viven en `sentinel/policies/patterns.py`.
4. **Single storage:** un solo archivo SQLite, una sola clase `DataLayer`.
5. **Output validation:** todo output pasa por QualityGate antes de llegar al usuario.
6. **No duplication:** `sentinel/adapters/` y `sidecar/services/` son una sola capa.
7. **Tests ≥ 650:** todas las fases agregan tests, ninguna reduce cobertura.
8. **Maturity score ≥ 7.0/10:** subir del 4.9 actual mediante eliminación de deuda técnica.

---

*Documento generado el 2026-07-10. Próxima revisión: post-FASE-3.*
