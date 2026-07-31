# Runtime Dependency Graph

> Contrato oficial del flujo de ejecución real de Sentinel.
> Basado en análisis estático del código y trazado de llamadas en `sidecar/main.py`,
> `sidecar/modules/__init__.py`, `sidecar/modules/sentinel_bridge.py`,
> `sentinel/core/orchestrator.py`, y `sentinel/core/tool_gateway.py`.

---

## 1. Flujo Principal (HTTP → Respuesta)

```
CLIENTE (HTTP)
  │
  ├── TrustedHostMiddleware        (sidecar/main.py:158)
  ├── CORSMiddleware               (sidecar/main.py:165)
  ├── auth_middleware              (sidecar/modules/auth.py)
  │     └── Extrae JWT → request.state.identity
  ├── security_boundary_middleware (sidecar/main.py:248)
  │     ├── Content-Length ≤ 10MB
  │     └── Headers: X-Content-Type-Options, X-Frame-Options, CSP, Cache-Control
  └── rate_limit_middleware        (sidecar/main.py:279)
        └── Sliding window por path (30-120 req/min según endpoint)
              │
              ▼
        ROUTE HANDLER
              │
              ├── POST /api/sentinel/chat
              │     └── sentinel_bridge.py:433 → gateway.execute("chat.respond", ...)
              │           │
              │           ▼
              │         ToolGateway.execute()          (tool_gateway.py:175)
              │           ├── 1. Identity validation
              │           ├── 2. Tool lookup → ChatRespondTool
              │           ├── 3. Context enrichment
              │           ├── 4. PolicyEngine.evaluate()   ← SEGURIDAD
              │           │     ├── IdentityPermission
              │           │     ├── CapabilityMatrix
              │           │     ├── PermissionLevel
              │           │     ├── GranularPermission
              │           │     ├── EmergencyStop
              │           │     └── Filesystem/Network/Browser/AI policies
              │           ├── 5. DENY → bloqueado
              │           │     REQUIRE_CONFIRM → ConfirmationBroker
              │           │     APPROVE → continúa
              │           ├── 6. AuditService.log_gateway_authorization()
              │           ├── 7. Grounding pre-check
              │           ├── 8. Hardening circuit breaker
              │           └── 9. ChatRespondTool.execute()
              │                  │
              │                  ▼
              │               ChatRespondTool.execute()   (chat_tools.py:145)
              │                 ├── [A] orch.classify_intent(message)
              │                 │     └── IntentEngine.parse() v1
              │                 │
              │                 ├── [B] ¿confidence >= 0.6?
              │                 │     │
              │                 │     ├── SÍ → orch.process(message, ...)
              │                 │     │        │
              │                 │     │        ▼
              │                 │     │     Orchestrator.process()    (orchestrator.py:303)
              │                 │     │       └── _process_impl()
              │                 │     │             │
              │                 │     │             ├── 1. collect_context()
              │                 │     │             │     ├── SystemContext (CPU, RAM, disk, network)
              │                 │     │             │     ├── Session history (context_engine)
              │                 │     │             │     ├── User profile (profile_manager)
              │                 │     │             │     ├── Learned memory (SQLiteBackend)
              │                 │     │             │     ├── Deep context (DeepContextEngine)
              │                 │     │             │     └── Environment learning
              │                 │     │             │
              │                 │     │             ├── 2. intent_engine.parse(utterance, context)
              │                 │     │             │     └── IntentEngine v1 (regex + LLM fallback)
              │                 │     │             │
              │                 │     │             ├── 3. planner.plan(intent, context) → Plan(steps)
              │                 │     │             │
              │                 │     │             ├── 4. model_router.select(task_type, context)
              │                 │     │             │     └── ModelRouter.select() → provider-based
              │                 │     │             │
              │                 │     │             └── _run_pipeline()       (orchestrator.py:632)
              │                 │     │                   │
              │                 │     │                   ├── 5. Validation
              │                 │     │                   ├── 6. SimulationEngine.simulate()
              │                 │     │                   ├── 7. RiskClassifier.classify()
              │                 │     │                   ├── 8. DecisionEngine.evaluate()
              │                 │     │                   │     └── ObjectiveRiskAssessor
              │                 │     │                   │     → APPROVE | REQUIRE_CONFIRM | REJECT
              │                 │     │                   │
              │                 │     │                   ├── 9. ¿REQUIRE_CONFIRM?
              │                 │     │                   │     └── ConsentService.create_pending()
              │                 │     │                   │     → espera respuesta usuario
              │                 │     │                   │
              │                 │     │                   ├── 10. _execute_single_step() [por cada step]
              │                 │     │                   │      └── ToolGateway.execute(tool_id, params)
              │                 │     │                   │            └── Tool específico
              │                 │     │                   │
              │                 │     │                   ├── 11. Post-execution grounding
              │                 │     │                   ├── 12. Memory store (ExecutionRecord)
              │                 │     │                   ├── 13. Advisory attachment
              │                 │     │                   └── 14. AuditService.log_pipeline()
              │                 │     │
              │                 │     └── NO → ai_svc.chat(message)  [conversación pura]
              │                 │            └── ModelRouter.chat() → provider LLM
              │                 │
              │                 └── [C] _persist_turn() → DB conversación
              │
              ├── POST /api/sentinel/chat/stream
              │     └── sentinel_bridge.py:457 → StreamingResponse
              │           └── Misma lógica + streaming NDJSON
              │
              ├── POST /api/sentinel/process
              │     └── sentinel_bridge.py:266 → gateway.execute("process.execute", ...)
              │           └── ProcessTool.execute() → orch.process() → pipeline completa
              │
              ├── POST /v1/execute
              │     └── routers/v1/execute.py → orchestrator.execute_direct()
              │
              ├── POST /v1/confirm
              │     └── routers/v1/confirm → gateway.confirm()
              │
              ├── GET/POST /v1/agents
              │     └── gateway.execute("agent.*", ...)
              │
              ├── GET/POST /v1/triggers
              │     └── gateway.execute("trigger.*", ...)
              │
              ├── GET /v1/audit
              │     └── AuditService.get_log()
              │
              ├── GET/POST /v1/policies
              │     └── PolicyEngine (direct)
              │
              ├── GET/PATCH /v1/profile
              │     └── gateway.execute("profile.*", ...)
              │
              ├── POST /auth/login
              │     └── JWT auth directo
              │
              ├── WebSocket /ws/events
              │     └── EventStreamService
              │
              └── GET /api/system/live
                    └── System info directo (CPU, RAM, GPU, disk)
```

---

## 2. Componentes que NO participan en el flujo real

```
IntelligenceOrchestrator    ✗  No se instancia en runtime
CapabilityEngine           ✗  No se instancia en runtime
IntentEngineV2             ✗  No se instancia en runtime (Orchestrator usa v1)
ConversationManager        ✗  No se instancia en runtime (chat usa persistencia propia)
ModelCoordinator           ✗  No se instancia en runtime
FusionEngine               ✗  No se instancia en runtime
ResourceIntelligenceLayer  ✗  No se instancia en runtime
PerformanceIntelligence    ✗  No se instancia en runtime
FeedbackEngine             ✗  No se instancia en runtime
ModelRanking               ✗  No se instancia en runtime
TimePredictor              ✗  No se instancia en runtime
ModelDiscovery             ✗  No se instancia en runtime
```

---

## 3. Tabla de Estado por Componente

| Componente | Archivo | Líneas | Runtime | Estado | Evidencia |
|---|---|---|---|---|---|
| `Orchestrator` | `orchestrator.py` | 2035 | Activo | **Legacy** | Instanciado en `modules/__init__.py:852` |
| `ModelRouter` | `model_router.py` | 1664 | Activo | **Riesgo** | Usado por Orchestrator y ai_service |
| `ToolGateway` | `tool_gateway.py` | 480 | Activo | **Crítico** | Punto de entrada único para toda ejecución |
| `PolicyEngine` | `policy_engine.py` | 214 | Activo | **Crítico** | Evaluado en cada gateway.execute() |
| `DecisionEngine` | `decision_engine.py` | 334 | Activo | **Legacy** | Usado en Orchestrator._run_pipeline() |
| `IntentEngine v1` | `intent.py` | 584 | Activo | **Legacy** | Usado por Orchestrator |
| `AuditService` | `services/audit_service.py` | 139 | Activo | **OK** | Llamado en gateway y orchestrator |
| `ConsentService` | (vía módulos) | — | Activo | **OK** | Integrado con orchestrator |
| `ContextEngine` | `context.py` | 259 | Activo | **OK** | Usado por gateway y orchestrator |
| `Planner` | `planner.py` | — | Activo | **OK** | Usado en Orchestrator._process_impl() |
| `RiskClassifier` | — | — | Activo | **OK** | Usado en Orchestrator._run_pipeline() |
| `SimulationEngine` | — | — | Activo | **OK** | Usado en Orchestrator._run_pipeline() |
| `IntelligenceOrchestrator` | `intelligence_orchestrator.py` | 349 | Inactivo | **Huérfano** | No instanciado en main.py |
| `CapabilityEngine` | `capability_engine.py` | 162 | Inactivo | **Huérfano** | No instanciado |
| `IntentEngineV2` | `intent_engine_v2.py` | 645 | Inactivo | **Huérfano** | No instanciado |
| `ConversationManager` | `conversation_manager.py` | 471 | Inactivo | **Huérfano** | Chat usa persistencia propia |
| `ModelCoordinator` | `model_coordinator.py` | 423 | Inactivo | **Huérfano** | No instanciado |
| `FusionEngine` | `fusion_engine.py` | 242 | Inactivo | **Huérfano** | No instanciado |
| `ResourceIntelligenceLayer` | `resource_intelligence.py` | 340 | Inactivo | **Huérfano** | No instanciado |
| `PerformanceIntelligence` | `performance_intelligence.py` | 206 | Inactivo | **Huérfano** | No instanciado |
| `FeedbackEngine` | `feedback_engine.py` | 172 | Inactivo | **Huérfano** | No instanciado |
| `ModelRanking` | `model_ranking.py` | 263 | Inactivo | **Huérfano** | No instanciado |
| `TimePredictor` | `time_predictor.py` | 161 | Inactivo | **Huérfano** | No instanciado |
| `ModelDiscovery` | `model_discovery.py` | 476 | Inactivo | **Huérfano** | No instanciado |

---

## 4. Rutas de Ejecución Alternativas (Bypasses)

### Ruta A — Tool Calling vía ModelRouter (BYPASS de seguridad)

```
ModelRouter.chat_with_tools()         (model_router.py:585)
  └── _call_provider() → LLM responde con tool_calls
        └── _handle_tool_calls()      (model_router.py:537)
              └── _execute_tool_call()  (model_router.py:530)
                    └── ToolGateway.execute()
                          └── Tool ejecutado

⚠️  NO pasa por:
      PolicyEngine.evaluate()
      DecisionEngine.evaluate()
      ConsentService
      AuditService.log_gateway_authorization()
      RiskClassifier
      SimulationEngine
```

### Ruta B — Provider Directo (SIN gobernanza)

```
ModelRouter.chat()                    (model_router.py:1031)
  └── _call_provider()                (model_router.py:1430)
        └── OpenAI client → LLM provider

⚠️  Sólo pasa por circuit breaker y métricas de costo.
     NO hay policy, NO hay audit, NO hay consent.
     El LLM recibe el mensaje del usuario directamente.
```

### Ruta C — Ejecución Gobernada (La correcta)

```
gateway.execute()                     (tool_gateway.py:175)
  ├── PolicyEngine.evaluate()         ← Seguridad
  ├── Audit logging                   ← Auditoría
  ├── Grounding pre-check             ← Verificación
  ├── Hardening circuit breaker       ← Resiliencia
  └── Tool.execute()                  ← Ejecución controlada
```

---

## 5. Resumen de Flujo Real

```
HTTP API
  │
  ▼
[Middleware Stack]
  │  auth → rate-limit → security-headers
  ▼
[Route Handler]
  │
  ├── /chat ───────── gateway.execute("chat.respond")
  │                     └── ChatRespondTool
  │                           ├── classify_intent() → IntentEngine v1
  │                           ├── [acción] → orch.process() → pipeline completa
  │                           └── [chat]   → ai_svc.chat() → ModelRouter → provider
  │
  ├── /chat/stream ── [preflight] → orch.process() → [streaming] → ai_svc.stream_chat()
  │
  ├── /process ────── gateway.execute("process.execute")
  │                     └── ProcessTool → orch.process() → pipeline completa
  │
  └── /v1/execute ─── orchestrator.execute_direct()
                        └── gateway.execute(tool_id)

NUNCA participan:
  IntelligenceOrchestrator, CapabilityEngine, PerformanceIntelligence,
  FeedbackEngine, ModelRanking, TimePredictor, ModelDiscovery,
  ConversationManager, ModelCoordinator, FusionEngine, ResourceIntelligence,
  IntentEngineV2
```

---

## 6. Contrato: Lo que NO existe en runtime

| Lo que el diseño dice | Lo que realmente corre |
|---|---|
| IntelligenceOrchestrator decide el modelo | Orchestrator delega en ModelRouter.select() (provider-based) |
| CapabilityEngine resuelve capacidades | No se resuelven capacidades; se usa TaskType |
| PerformanceIntelligence colecciona métricas | No se coleccionan métricas de ejecución |
| FeedbackEngine recibe feedback | No hay feedback de usuario |
| ModelRanking ajusta selección | No hay ranking dinámico |
| ConversationManager mantiene contexto | chat_tools.py persiste conversación en DB propia |
| ModelCoordinator orquesta multi-modelo | No hay multi-modelo en producción |
| FusionEngine fusiona respuestas | No hay fusión |
| ResourceIntelligence evalúa hardware | No hay evaluación de hardware para routing |
