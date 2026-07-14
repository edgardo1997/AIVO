# Fase 4: Intent Engine + Model Router - Cierre

## Objetivo
El usuario expresa una intencion en lenguaje natural y el sistema la traduce a una accion estructurada, selecciona el modelo IA adecuado y la ejecuta contra las herramientas disponibles.

## Archivos creados

### sentinel/core/intent.py
- Intent: dataclass con action, target, parameters, confidence, raw_input
- IntentPattern: patron con regex, extractores de parametros, prioridad
- IntentEngine:
  - 12 patrones predefinidos que cubren: CPU, RAM, disco, red, procesos, sistema, health, uptime, AI config, providers, comandos
  - parse(utterance, context): evalua todos los patrones, selecciona el mejor por puntuacion (match_ratio + prioridad)
  - Fallback seguro (confidence 0.3) cuando no hay match
  - egister_pattern(): para extender con nuevos patrones
  - list_supported_targets(): introspeccion para el frontend

### sentinel/core/model_router.py
- TaskType: REASONING, ANALYSIS, QUICK, CODE, CREATIVE, LOCAL
- ProviderSpec: especificacion de cada proveedor con capacidades
- ModelRouter:
  - 10 proveedores predefinidos con sus tipos de tarea
  - select(task_type): elige el mejor proveedor segun estrategia
  - Estrategias: priority, cost, local_first, manual
  - Gestion de API keys con set_api_key() / has_api_key()
  - Fallback a proveedores sin key si ninguno con key disponible
  - list_providers(): introspeccion

### sentinel/core/orchestrator.py
- ExecutionPlan: intent resuelto + tool_id + parametros + router_decision
- ExecutionResult: plan + resultado + errores
- Orchestrator:
  - process(utterance): flujo completo:
    1. Recolectar contexto (ContextEngine)
    2. Parsear intencion (IntentEngine)
    3. Construir plan (accion -> herramienta -> parametros)
    4. Seleccionar modelo (ModelRouter)
    5. Ejecutar tool (ToolGateway con policy check)
    6. Retornar ExecutionResult
  - get_capabilities(): introspeccion completa (intents + tools + models)

## Prueba de aceptacion superada
- IntentEngine: 7 utterances parseadas correctamente, fallback funciona, 12 targets
- ModelRouter: QUICK->ollama, REASONING->openrouter, ANALYSIS->groq, local_first funciona
- Orchestrator: flujo completo intent->policy->tool, parametros extraidos (limit=10), router selecciona modelo
- 13/13 subtests pasan

## No se modifico
- sidecar/ intacto
- src/ intacto
- src-tauri/ intacto
- Ningun runtime, DB, log o proceso activo

## Proxima fase
Fase 5: Planner + Decision Engine
- Planner: descompone una intencion en pasos multi-herramienta
- DecisionEngine: evalua riesgos, costos y alternativas antes de ejecutar
- Integracion: el Orchestrator puede decidir NO ejecutar si el riesgo es muy alto
