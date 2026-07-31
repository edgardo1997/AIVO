# Runtime Ownership Rules

> Reglas de gobierno para la arquitectura de ejecución de Sentinel.
> Toda modificación al runtime debe cumplir estas reglas.

---

## Regla 1: Un Solo Gate de Ejecución

**Ningún componente ejecuta herramientas directamente.**

```
INCORRECTO:
  ModelRouter ──→ ToolGateway.execute()        # Sin policy
  Orchestrator ──→ Tool específico             # Sin audit
  ChatRespondTool ──→ ToolGateway.execute()    # Sin decisión

CORRECTO:
  CUALQUIER componente
    └── SentinelRuntime.process()
          └── PolicyLayer.evaluate()
          └── DecisionEngine.evaluate()
          └── ConsentService.confirm()
          └── ToolGateway.execute()            # Único punto de salida
          └── AuditService.log()
          └── PerformanceIntelligence.record()
```

**Excepciones:** Ninguna.

**Sanción:** Cualquier código que ejecute `ToolGateway.execute()` sin pasar por
PolicyEngine constituye un security bypass y debe ser tratado como CRITICAL.

---

## Regla 2: Un Solo Dueño del Flujo

**SentinelRuntime es el único orquestador.**

```
INCORRECTO:
  Orchestrator.process()          # Pipeline legacy
  IntelligenceOrchestrator.orchestrate()  # Pipeline nuevo (huérfano)
  ModelRouter.chat()              # Routing directo
  ai_svc.chat()                   # Chat directo
  ChatRespondTool.execute()       # Decisión propia

CORRECTO:
  SentinelRuntime.process(request)
    ├── decide si es chat o acción
    ├── ejecuta pipeline completo
    └── retorna respuesta
```

**Migración:** El `Orchestrator` existente se refactoriza a `SentinelRuntime`.
`IntelligenceOrchestrator` se fusiona dentro de `SentinelRuntime.learning_layer`.

**Excepciones:** Endpoints puramente informativos (`/health`, `/system/live`)
no requieren pasar por SentinelRuntime.

---

## Regla 3: Los Módulos Inteligentes Deben Estar Conectados

**Ningún módulo de Phase 9-10 puede existir aislado.**

```
INCORRECTO:
  ModelRanking.compute_scores()    # Nadie consulta el resultado
  PerformanceIntelligence.record() # Nadie llama record()
  FeedbackEngine.record_feedback() # No hay endpoint que reciba feedback

CORRECTO:
  ModelRanking
    └── consultado por ModelRouter._smart_select()
    └── consultado por SentinelRuntime._resolve_task_type()

  PerformanceIntelligence
    └── llamado por ToolGateway después de cada execute()
    └── llamado por SentinelRuntime después de cada process()

  FeedbackEngine
    └── conectado a un endpoint POST /api/feedback
    └── llamado por ChatRespondTool después de cada interacción
```

**Regla:** Si un módulo no tiene al menos un caller en runtime, está en estado
"HUÉRFANO" y debe ser conectado o removido.

---

## Regla 4: Separación Entre Decisión y Ejecución

**Quien decide no ejecuta. Quien ejecuta no decide.**

```
CORRECTO:
  DecisionEngine.evaluate()        # Decide
    └── retorna APPROVE | REJECT | REQUIRE_CONFIRM

  ToolGateway.execute()            # Ejecuta
    └── recibe decisión ya tomada
    └── ejecuta la herramienta
    └── registra auditoría
    └── registra métricas
```

**Prohibido:**
- Que un componente decida Y ejecute en el mismo método
- Que un componente omita la decisión y ejecute directamente

---

## Regla 5: Auditoría Obligatoria

**Toda operación que termine en ToolGateway.execute() debe generar un registro de auditoría.**

```
FLUJO:
  ToolGateway.execute()
    ├── AuditService.log_gateway_authorization()  # Pre-ejecución
    ├── Tool.execute()
    └── AuditService.log_action()                 # Post-ejecución
```

**Excepciones:** Operaciones de solo lectura del sistema (`/health`).

---

## Regla 6: Consistencia de Tipos

**Un solo sistema de tipos para intenciones y tareas.**

```
ACTUAL (INCORRECTO):
  ┌─────────────────────────┬──────────────────────────┐
  │ IntentEngine v1         │ IntentEngineV2            │
  │ action: str             │ category: IntentCategory  │
  │ target: str             │ 10 categorías             │
  │ 5 acciones              │                           │
  ├─────────────────────────┼──────────────────────────┤
  │ ModelRouter.TaskType    │ Orchestrator.INTENT_TO_TASK│
  │ 6 tipos                 │ Mapa de 5 entradas        │
  └─────────────────────────┴──────────────────────────┘

OBJETIVO:
  IntentCategory como único tipo de intención.
  TaskType como derivado de IntentCategory.
```

---

## Regla 7: Política de Seguridad en Tiempo de Compilación

**No puede existir un camino de ejecución que evite PolicyEngine.**

Verificación:
- `ModelRouter._handle_tool_calls()` DEBE llamar a `PolicyEngine.evaluate()`
  antes de `ToolGateway.execute()`
- `ModelRouter._call_provider()` DEBE llamar a `PolicyEngine.evaluate()`
  antes de enviar el mensaje al LLM
- Cualquier nuevo endpoint DEBE documentar qué políticas aplica

---

## Regla 8: Inmutabilidad del Runtime Contract

**Una vez establecido, `SentinelRuntime.process()` no puede ser reemplazado.**

Toda evolución del sistema debe ocurrir DENTRO de SentinelRuntime,
no creando un nuevo punto de entrada paralelo.

---

## Checklist de Cumplimiento

| Regla | Descripción | Verificación |
|---|---|---|
| R1 | Un solo gate de ejecución | Buscar `ToolGateway.execute()` → todos deben tener policy antes |
| R2 | Un solo dueño del flujo | No debe haber `Orchestrator.process()` + `IntelligenceOrchestrator.orchestrate()` |
| R3 | Módulos conectados | Cada módulo Phase 9-10 debe tener un caller en runtime |
| R4 | Separación decisión/ejecución | Ningún método que decide también ejecuta |
| R5 | Auditoría obligatoria | Todo `ToolGateway.execute()` debe tener audit antes y después |
| R6 | Consistencia de tipos | IntentCategory como único tipo de intención |
| R7 | No bypass de seguridad | PolicyEngine debe estar en todos los caminos de ejecución |
| R8 | Inmutabilidad del contract | `SentinelRuntime.process()` es el único entry point |
