# Runtime Trace Analysis

> Trazado real de una petición a través del sistema.
> Basado en el código verificado, no en el diseño deseado.
> Cada paso marcado como: ✅ PASSED | ❌ FAILED | ⚠️ BYPASSED | ❓ MISSING

---

## Escenario: "abre chrome"

Suposiciones:
- Usuario autenticado con JWT
- Sesión activa
- Rate limit no excedido

### Traza completa

```
PASO 0: HTTP REQUEST
────────────────────────────────────────────────────────────
  POST /api/sentinel/chat  {"message": "abre chrome", "session_id": "abc-123"}
  → ✅ PASSED: Llega al router correcto (sentinel_bridge.py:433)

PASO 1: AUTH MIDDLEWARE
────────────────────────────────────────────────────────────
  auth_middleware: extrae JWT, valida, setea request.state.identity
  → ✅ PASSED: Usuario autenticado

PASO 2: SECURITY BOUNDARY
────────────────────────────────────────────────────────────
  security_boundary_middleware: verifica Content-Length, agrega headers
  → ✅ PASSED: Petición dentro de límites

PASO 3: RATE LIMIT
────────────────────────────────────────────────────────────
  rate_limit_middleware: chequea sliding window para /api/sentinel/*
  → ✅ PASSED: 30 req/min, no excedido

PASO 4: ROUTE HANDLER
────────────────────────────────────────────────────────────
  sentinel_chat(): extrae params, llama gateway.execute("chat.respond", ...)
  → ✅ PASSED

PASO 5: TOOL GATEWAY — SEGURIDAD
────────────────────────────────────────────────────────────
  ToolGateway.execute():
    ├── Identity validation        → ✅ PASSED
    ├── Tool lookup                → ✅ PASSED: ChatRespondTool encontrado
    ├── Status check (DISABLED?)   → ✅ PASSED: Tool habilitado
    ├── Context enrichment         → ✅ PASSED
    ├── PolicyEngine.evaluate()    → ✅ PASSED: Permiso "chat.respond" otorgado
    ├── Grounding pre-check        → ✅ PASSED: No requiere grounding
    ├── Hardening circuit breaker  → ✅ PASSED: Circuito cerrado
    └── Audit log auth decision    → ✅ PASSED: Registrado en auditoría

PASO 6: CHAT RESPOND TOOL — INTENT CLASSIFICATION
────────────────────────────────────────────────────────────
  ChatRespondTool.execute():
    └── orch.classify_intent("abre chrome")
          └── IntentEngine v1.parse()
                ├── Regex parse → action=execute, target=app.discovery
                │   → confidence calculado
                └── ¿Confianza >= 0.6?
                      → ✅ PASSED: "abre chrome" es claro, confianza > 0.6

PASO 7: ORCHESTRATOR.PROCESS() — PIPELINE COMPLETA
────────────────────────────────────────────────────────────
  orch.process("abre chrome", identity, session_id)
    └── _process_impl():
          ├── collect_context()
          │     ├── SystemContext (CPU, RAM, disk, network)  → ✅
          │     ├── Session history                          → ✅
          │     ├── User profile                             → ✅
          │     ├── Learned memory                           → ✅
          │     └── Environment learning                     → ✅
          │
          ├── intent_engine.parse("abre chrome", context)
          │     → Intent(action="execute", target="app.discovery", ...)
          │     → ✅ PASSED: Intención detectada correctamente
          │
          ├── planner.plan(intent, context)
          │     → Plan con steps: [discover_chrome, launch_chrome]
          │     → ✅ PASSED: Plan generado
          │
          ├── model_router.select(TaskType.ACTION, context)
          │     → RouterDecision(provider="sentinel_local", model="local")
          │     → ✅ PASSED: Modelo seleccionado (local, sin costo)
          │
          └── _run_pipeline()
                │
                ├── 5. Validation
                │     → ✅ PASSED: Plan válido
                │
                ├── 6. Simulation
                │     → SimulationEngine.simulate(plan, context)
                │     → ✅ PASSED: Simulación completada
                │
                ├── 7. Risk Classification
                │     → RiskClassifier.classify(intent, plan, context)
                │     → Riesgo: BAJO (abrir Chrome es seguro)
                │     → ✅ PASSED
                │
                ├── 8. Decision Engine
                │     → DecisionEngine.evaluate(plan, context, simulation, risk)
                │       ├── RiskClassification = LOW
                │       └── ObjectiveRiskAssessor.assess()
                │     → Decision.APPROVE
                │     → ✅ PASSED: Decisión automática aprobada
                │
                ├── 9. Consent Service (solo si REQUIRE_CONFIRM)
                │     → No aplica: Decisión = APPROVE
                │     → ✅ SKIPPED (correctamente)
                │
                ├── 10. Ejecución de Steps
                │     └── _execute_single_step("launch", "chrome")
                │           └── ToolGateway.execute("app.launch", {name: "chrome"})
                │                 ├── PolicyEngine.evaluate()
                │                 │     → PermissionLevel, GranularPermission...
                │                 │     → ✅ PASSED: Permitido
                │                 ├── Audit log
                │                 │     → ✅ PASSED
                │                 └── AppLauncherTool.execute({name: "chrome"})
                │                       → Chrome launched
                │                       → ✅ PASSED: Herramienta ejecutada
                │
                ├── 11. Post-execution grounding
                │     → ✅ PASSED
                │
                ├── 12. Memory store
                │     → ExecutionRecord almacenado
                │     → ✅ PASSED
                │
                ├── 13. Advisory attachment
                │     → AdvisoryService.attach()
                │     → ✅ PASSED
                │
                └── 14. Audit pipeline
                      → AuditService.log_pipeline(...)
                      → ✅ PASSED

PASO 8: RESPUESTA AL USUARIO
────────────────────────────────────────────────────────────
  ChatRespondTool:
    ├── ¿Pipeline tiene governed response?
    │     → Sí: "Chrome abierto correctamente"
    │     → Se devuelve directamente, SIN llamada LLM
    │     → ✅ PASSED: Respuesta rápida sin costo de API
    │
    └── _persist_turn() → DB conversación
          → ✅ PASSED

  → HTTP 200: {"response": "Chrome abierto correctamente", ...}
```

---

## Resumen de Estado por Paso

| Paso | Componente | Estado |
|---|---|---|
| 0 | HTTP Request | ✅ |
| 1 | Auth Middleware | ✅ |
| 2 | Security Boundary | ✅ |
| 3 | Rate Limiter | ✅ |
| 4 | Route Handler | ✅ |
| 5 | ToolGateway Security | ✅ |
| 6 | Intent Classification (v1) | ✅ |
| 7a | Context Collection | ✅ |
| 7b | Intent Parsing | ✅ |
| 7c | Planning | ✅ |
| 7d | Model Selection (provider-based) | ✅ |
| 7e | Validation | ✅ |
| 7f | Simulation | ✅ |
| 7g | Risk Classification | ✅ |
| 7h | Decision Engine | ✅ |
| 7i | Consent Service | ✅ (skipped correctly) |
| 7j | Tool Execution | ✅ |
| 7k | Post-grounding | ✅ |
| 7l | Memory Storage | ✅ |
| 7m | Audit Pipeline | ✅ |
| 8 | Response | ✅ |

---

## Escenario Alternativo: "abre chrome" vía ModelRouter bypass

Si el mismo mensaje llegara a `ModelRouter.chat()` directamente
(por ejemplo, en una llamada a `ai_svc.chat()` sin pipeline):

```
PASO 5 (ALTERNATIVO): MODELROUTER.CHAT()
────────────────────────────────────────────────────────────
  ModelRouter.chat("abre chrome")
    ├── select() → provider
    ├── _call_provider() → LLM responde "No puedo abrir apps"
    │                       (el LLM no tiene contexto de herramientas)
    │
    ⚠️  BYPASS: No hay PolicyEngine
    ⚠️  BYPASS: No hay DecisionEngine
    ⚠️  BYPASS: No hay ConsentService
    ⚠️  BYPASS: No hay AuditService
    ⚠️  BYPASS: No hay RiskClassifier
    ⚠️  BYPASS: No hay SimulationEngine
    ⚠️  BYPASS: No hay herramienta ejecutada
    ⚠️  MISSING: No hay execution record
```

---

## Escenario: "abre chrome" si el ModelRouter usara tool calling

```
PASO 5 (ALTERNATIVO CON TOOL CALLING):
────────────────────────────────────────────────────────────
  ModelRouter.chat_with_tools("abre chrome")
    ├── _call_provider() → LLM responde con tool_call: launch_app
    └── _handle_tool_calls()
          └── _execute_tool_call("launch_app", {name: "chrome"})
                └── ToolGateway.execute("launch_app", {name: "chrome"})
                      → ✅ Tool ejecutada
                      → ⚠️  BYPASS: PolicyEngine NO EVALUADO
                      → ⚠️  BYPASS: DecisionEngine NO EVALUADO
                      → ⚠️  BYPASS: ConsentService NO CONSULTADO
                      → ⚠️  BYPASS: AuditService LOG SOLO EN GATEWAY
                      → ⚠️  BYPASS: RiskClassifier NO CONSULTADO
                      → ⚠️  MISSING: No hay registro en audit de pipeline
```

---

## Componentes del Diseño que NO Aparecen en Ningún Escenario Real

| Componente | ¿Aparece en trace? | Motivo |
|---|---|---|
| IntelligenceOrchestrator | ❌ | No instanciado en runtime |
| CapabilityEngine | ❌ | No instanciado |
| IntentEngineV2 | ❌ | Orchestrator usa v1 |
| ConversationManager | ❌ | Chat usa persistencia directa en DB |
| ModelCoordinator | ❌ | No instanciado |
| FusionEngine | ❌ | No instanciado |
| ResourceIntelligenceLayer | ❌ | No instanciado |
| PerformanceIntelligence | ❌ | No instanciado |
| FeedbackEngine | ❌ | No instanciado |
| ModelRanking | ❌ | No instanciado |
| TimePredictor | ❌ | No instanciado |
| ModelDiscovery | ❌ | No instanciado |
| EventBus (como observabilidad) | ❌ | No hay suscriptores en runtime |
| Production Intelligence events | ❌ | Eventos nunca emitidos |
