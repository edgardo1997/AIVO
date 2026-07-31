# Current Sentinel Architecture

## Entry Points

| Endpoint | Método | Handler | Propósito |
|---|---|---|---|
| `/api/sentinel/chat` | POST | `sentinel_bridge.py → ChatRespondTool` | Chat con IA + ejecución opcional de tools |
| `/api/sentinel/chat/stream` | POST | `sentinel_bridge.py → AIService.stream_chat()` | Chat streaming |
| `/api/sentinel/process` | POST | `sentinel_bridge.py → Orchestrator.process()` | Pipeline completo de ejecución |
| `/api/sentinel/process/multi-agent` | POST | `sentinel_bridge.py → MultiAgentOrchestrator` | Pipeline multi-agente (separado) |
| `/api/ai/chat` | POST | `AIService.chat()` | Chat directo sin pipeline |
| `/api/consent/respond` | POST | `ConsentService.respond_consent()` | Aprobación de consentimiento |
| `/api/executor/launch` | POST | `ExecutorService.launch_app()` | Lanzar app (HTTP directo) |
| `/api/executor/command` | POST | `ExecutorService.run_command()` | Ejecutar comando (HTTP directo) |
| `/api/executor/kill/{pid}` | POST | `ExecutorService.kill_process()` | Matar proceso (HTTP directo) |

## Request Flow (Chat → Tool Execution)

```
Usuario
  │
  ▼ POST /api/sentinel/chat { message: "abre bloc de notas" }
  │
  ▼ sentinel_bridge.py: sentinel_chat()
  │
  ▼ ToolGateway.execute("chat.respond", { message, context, session_id })
  │
  ▼ ChatRespondTool.execute()
      │
      ├── orch.classify_intent(message)
      │     └── IntentEngine.parse(utterance) → regex → Intent(confidence)
      │
      ├── [antes del fix: confidence < 0.6 → solo chat]
      │   [después del fix: siempre intenta pipeline]
      │
      ├── orch.process(message, identity, session_id)
      │     │
      │     ├── ContextEngine.collect() → system state
      │     ├── IntentEngine.parse(utterance, context) → Intent
      │     ├── ReasoningEngine.reason() → goals, risk
      │     ├── Planner.plan(intent, context) → Plan(steps)
      │     ├── ModelRouter.select(task_type) → provider, model
      │     ├── SimulationEngine.simulate(plan, context)
      │     ├── RiskClassifier.classify() → RiskLevel
      │     ├── DecisionEngine.evaluate() → APPROVE/REJECT/CONFIRM
      │     ├── GroundingEngine.enforce() → verify facts
      │     └── ToolGateway.execute(tool_id, params, context)
      │           │
      │           ├── Identity Gate
      │           ├── Authorization Gate (RoleCapabilityMatrix)
      │           ├── Consent Gate (HIGH/CRITICAL only)
      │           ├── Policy Engine (multi-policy)
      │           ├── Grounding
      │           ├── Circuit Breaker
      │           ├── Tool.execute(params, context)
      │           └── Quality Gate (post-execution)
      │
      └── Response formatting
            ├── Governed response (via PresentationLayer)
            └── LLM formatting (via AIService.chat())
```

## Core Components

### Orchestrator (`sentinel/core/orchestrator.py` — 2163 lines)
- **Responsabilidad:** Coordinar el pipeline completo de ejecución
- **Composición:** 30+ dependencias opcionales
- **Pipeline:** Context → Intent → Reason → Plan → Route → Simulate → Risk → Decide → Ground → Execute → Verify → Record → Advisory
- **Timeout:** Configurable (default 60s)
- **Rate limiting:** Pipeline-level + per-tool
- **Rollback:** Automático en multi-step failures

### ModelRouter (`sentinel/core/model_router.py` — 1354 lines)
- **Responsabilidad:** Seleccionar proveedor/modelo por task type
- **Task types:** REASONING, ANALYSIS, QUICK, CODE, CREATIVE, LOCAL
- **Estrategias:** priority, local_first, cost, smart, manual
- **Fallback chain:** Provider → default_fallback → select_all()
- **Health checks:** TTL-based availability caching
- **Circuit breaker:** Provider-level failure tracking
- **Limitación:** No envía tool calling (`tools`/`functions` nunca incluidos)

### IntentEngine (`sentinel/core/intent.py` — 584 lines)
- **Responsabilidad:** Clasificar intención del usuario
- **Método dual:** Regex primero (rápido, determinista), LLM fallback
- **Categorías:** query, execute, analyze, configure
- **Targets:** system.*, executor.*, filesystem.*, app.discovery, settings.*
- **Deficiencia:** No diferencia CHAT vs ACTION vs CODING vs SEARCH

### ToolGateway (`sentinel/core/tool_gateway.py` — 537 lines)
- **Responsabilidad:** Ejecutar herramientas con validación multi-capa
- **Gates:** Identity → Auth → Consent → Policy → Grounding → Circuit Breaker → Execute → Quality
- **Registro:** Tools registrados con ToolSpec (id, name, permissions, timeout)
- **Timeout:** Spec → Hardening config → 30s default

### Planner (`sentinel/core/planner.py`)
- **Responsabilidad:** Generar plan de ejecución multi-step
- **Características:** Dependency resolution, parallel execution levels, tool-specific step generation

### RiskClassifier (`sentinel/core/risk_classifier.py` — 337 lines)
- **Responsabilidad:** Clasificar riesgo de cada acción
- **Niveles:** LOW, MEDIUM, HIGH, CRITICAL
- **Problema:** CRITICAL_TOOLS = {} (vacío)
- **Heurísticas:** App name analysis, path suspicion, simulation impact

### DecisionEngine (`sentinel/core/decision_engine.py` — 334 lines)
- **Responsabilidad:** Decidir APPROVE/REJECT/REQUIRE_CONFIRM
- **Base:** ObjectiveRiskAssessment + thresholds
- **Límite:** MODIFY definido pero nunca producido; LLM advisor desactivado

### PolicyEngine (`sentinel/core/policy_engine.py` — 214 lines)
- **Responsabilidad:** Evaluar políticas de seguridad
- **Políticas:** RoleMatrix, PermissionLevel, IdentityPermission, GranularPermission, EmergencyStop, Filesystem, Network, Browser, AI, Output
- **Default:** DENY si no hay políticas

### ConsentManager (`sentinel/core/consent_manager.py` — 336 lines)
- **Responsabilidad:** Gestión de consentimiento del usuario
- **Tipos:** ONCE, SESSION, PERMANENT
- **TTL:** 10 minutos para pending; 24h para SESSION
- **Storage:** InMemory o JSON file

### CostTracker (`sentinel/core/cost_tracker.py` — 374 lines)
- **Responsabilidad:** Registrar costos de inferencia
- **Storage:** SQLite con WAL
- **Pricing:** Modelo → precio por 1K tokens
- **Limitación:** Budgets registrados pero no enforced en pipeline

### Memory System (fragmentado)
- `memory.py` — SQLite KV + sesiones + snapshots
- `operational_memory.py` — ExecutionRecords, EpisodicMemory, LearnedPreferences
- `database.py` — ConversationThreads (por el bridge HTTP)

### Conversation (`sentinel/conversation/`)
- `SentinelCoreConversation` — Núcleo determinista sin LLM (fallback)
- `ConversationAvailabilityLayer` — Wrapper con failover a core
- No hay estado de conversación entre turnos

## Model System

### Proveedores Soportados (14 built-in)
1. `nvidia-nemotron` — Predeterminado (REASONING, ANALYSIS, CREATIVE)
2. `openrouter` — Multi-modelo (todos los task types)
3. `openai` — GPT-4o, GPT-4o-mini
4. `deepseek` — deepseek-chat
5. `anthropic` — Claude 3.5 Sonnet (proxy OpenAI)
6. `google` — Gemini 2.0 Flash
7. `github_models` — GPT-4o-mini
8. `together` — Mistral, Llama
9. `groq` — Mixtral, Llama (rápido)
10. `mistral` — Mistral Large, Small
11. `cohere` — Command R+
12. `sentinel_local` — Qwen3-1.7B-Q8_0.gguf (local)
13. `ollama` — qwen2.5-coder:1.5b (local)
14. `custom` — OpenAI-compatible endpoint

### Routing
- **Input:** `AIService._task_type_for_message()` — keyword matching básico
- **Proceso:** `ModelRouter.select(task_type, context)` → filtra por task_type + disponibilidad + hardware
- **Estrategias:** priority (default), local_first, cost, smart, manual
- **Output:** ProviderSpec.default_model (string plano)

## Security Pipeline

```
Request
  │
  ├── 1. Authentication (JWT/session token)
  ├── 2. Authorization (RoleCapabilityMatrix)
  ├── 3. Rate Limiting (hierarchical: global/session/user/tool)
  ├── 4. Consent (HIGH/CRITICAL only)
  ├── 5. Policy Engine (8+ policies)
  ├── 6. Risk Classification (rule-based)
  ├── 7. Decision Engine (objective thresholds)
  ├── 8. Grounding (fact verification)
  ├── 9. Circuit Breaker (per-tool)
  └── 10. Quality Gate (post-execution)
```

## Known Limitations

| Limitación | Impacto | Componente |
|---|---|---|
| Sin Model Registry | No hay metadata de capacidades por modelo | ModelRouter |
| Sin tool calling | Modelos no pueden llamar funciones nativamente | ModelRouter |
| Budget sin enforce | No se puede bloquear por costo | CostTracker |
| CRITICAL_TOOLS vacío | Ninguna tool se clasifica CRITICAL | RiskClassifier |
| Memoria fragmentada | Historial de conversación no unificado | memory.py / operational_memory / database.py |
| Context window no re-manejado en fallback | Overflow si fallback tiene menos contexto | AIService.chat() |
| Offline queue no-op | La cola offline no sincroniza | Orchestrator._sync_offline_item() |
| MODIFY en DecisionEngine dead code | Nunca se produce decisión MODIFY | DecisionEngine |
| HTTPException en ExecutorService | Excepción de transporte en lógica de dominio | ExecutorService |

## Technical Debt

| Deuda | Archivo | Severidad |
|---|---|---|
| FREE_PROVIDERS duplicado (desincronizado con BUILTIN_PROVIDERS) | `ai_service.py` | Alta |
| ModelRouter.select() llamado dos veces en pipeline | `orchestrator.py` | Media |
| ExecutorService viola SRP (1 clase = 4 tools + validación + resolución) | `executor_service.py` | Media |
| Risk defaults hardcoded en dict (nuevas tools = LOW por defecto) | `capability_registry.py` | Media |
| Authorize_execution + CapabilityMatrixPolicy hacen lo mismo | `tool_gateway.py` / `capability_matrix.py` | Media |
| _ToolAdapter muta spec.id in-place | `__init__.py` | Baja |
| Guardian set después de construcción | `executor_service.py` | Baja |
