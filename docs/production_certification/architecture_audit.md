## Sentinel 1.0 — Architecture Audit

### FASE A: Current Architecture

#### Actual Runtime Flow (not the ideal flow)

```
User/API Request
  ↓
sidecar/main.py (FastAPI → auth middleware → rate limiter)
  ↓
Routers (18 routers registered)
  ↓
Orchestrator.process() [LEGACY — 2035 lines]
  ├── rate_limit.check()
  ├── identity.validate()
  ├── context_engine.collect() (system, session, user preferences, memory)
  ├── intent_engine.parse() (IntentEngine or IntentEngineV2?)
  ├── plan_cache.lookup()
  ├── planner.create()
  ├── simulation_engine.simulate()
  ├── risk_classifier.classify()
  ├── decision_engine.evaluate()
  ├── consent_service.confirm()
  ├── model_router.chat() [1664 lines]
  │     ├── select() provider-based OR select_by_capability() registry-based
  │     ├── _build_fallback_chain()
  │     ├── _call_provider() or _call_provider_stream()
  │     ├── _handle_tool_calls() → ToolGateway
  │     └── circuit_breaker.record()
  ├── execute_direct() for tool execution
  ├── audit_service.record()
  └── memory.store()
```

**WHAT IS MISSING FROM THIS ACTUAL FLOW:**
- `IntelligenceOrchestrator` is **NOT INVOKED** in `Orchestrator.process()`
- `CapabilityEngine` is not wired into the legacy flow
- `PerformanceIntelligence` is not collecting metrics
- `ModelRanking` is not consulted
- `FeedbackEngine` is not receiving feedback
- `TimePredictor` is not predicting times
- `ResourceIntelligenceLayer` is not evaluating resources
- `ModelDiscovery` is not running
- `ConversationManager` is used only by `ModelRouter.chat_with_conversation()` in a separate path

#### The Actual Two-Path System

**Path A (Legacy/Production):** `Orchestrator.process()` → `ModelRouter.chat()` → provider
This path is what actually runs in production. It does NOT use IntelligenceOrchestrator.

**Path B (New Intelligence):** `ModelRouter.chat_with_decision()` ← `IntelligenceOrchestrator.orchestrate()`
This path is **only used by tests**. No production code invokes `chat_with_decision()`.

**Evidence:**
- `sidecar/main.py` lines 375-530: wires `Orchestrator`, `ModelRouter`, `ToolGateway`, tools
- `sidecar/main.py` does NOT wire or instantiate `IntelligenceOrchestrator` anywhere
- The `IntelligenceOrchestrator` is importable but **never instantiated** at runtime
- `chat_with_decision()` is defined at `model_router.py:1569` but never called outside tests
- `chat_with_conversation()` is defined at `model_router.py:1591` but never called outside tests

---

### FASE B: Component Responsibility Analysis

| Component | Responsibility | Defined? | Invades Others? | Used? | Can Remove? |
|---|---|---|---|---|---|
| `Orchestrator` (legacy) | Full pipeline orchestration | Yes | Yes — invades ModelRouter, DecisionEngine, Policy | **YES — primary entry point** | No — currently the only active path |
| `IntelligenceOrchestrator` | Capability-aware model selection | Yes | No | **NO — not wired in runtime** | Yes — dead code in production |
| `ModelRouter` | Provider selection, fallback, tool calling | No (too broad) | Yes — invades ConversationManager, ToolGateway, circuit breaker | YES | No — core routing |
| `CapabilityEngine` | Resolve capabilities per intent type | Partially | No | Only via IntelligenceOrchestrator | Yes — dead code in production |
| `IntentEngineV2` | Classify user intent | Yes | Partially — duplicates IntentEngine in legacy orchestrator | Via tests and IntelligenceOrchestrator | Would need integration |
| `ConversationManager` | Manage conversation context | Yes | No | Only via chat_with_conversation() | Yes — dead code in production |
| `ModelCoordinator` | Multi-model task coordination | Yes | No | Only via tests | Yes — dead code in production |
| `FusionEngine` | Merge multi-model results | No (unclear merge strategy) | No | Only via tests | Yes — dead code in production |
| `ResourceIntelligenceLayer` | Evaluate hardware constraints | Yes | No | Only via IntelligenceOrchestrator | Yes — dead code in production |
| `PerformanceIntelligence` | Collect execution metrics | Yes | No | Only via tests | Yes — dead code in production |
| `FeedbackEngine` | Record user feedback | Yes | No | Only via tests | Yes — dead code in production |
| `ModelRanking` | Dynamic model ranking | Yes | No | Only via tests | Yes — dead code in production |
| `TimePredictor` | Estimate task duration | Yes | No | Only via tests | Yes — dead code in production |
| `ModelDiscovery` | Auto-discover models | Yes | No | Only via tests | Yes — dead code in production |
| `PolicyEngine` | Evaluate security policies | Yes | No | Via Orchestrator's decision_engine | No |
| `DecisionEngine` | Evaluate execution decisions | Yes | No | Via Orchestrator | No |
| `ToolGateway` | Execute tool calls | Yes | No | Via Orchestrator + ModelRouter | No |

**CRITICAL FINDING: 9 of 19 components are dead code in production runtime.** The entire
Phase 9 (ModelDiscovery) and Phase 10 (Production Intelligence) exist only in tests.

#### Components Never Instantiated at Runtime

Based on `sidecar/main.py` wiring (lines 375-530):
- `IntelligenceOrchestrator` — NOT instantiated
- `CapabilityEngine` — NOT instantiated
- `IntentEngineV2` — NOT instantiated (Orchestrator uses `IntentEngine` from `sentinel/core/intent.py`)
- `ConversationManager` — NOT instantiated
- `ModelCoordinator` — NOT instantiated
- `FusionEngine` — NOT instantiated
- `ResourceIntelligenceLayer` — NOT instantiated
- `PerformanceIntelligence` — NOT instantiated
- `FeedbackEngine` — NOT instantiated
- `ModelRanking` — NOT instantiated
- `TimePredictor` — NOT instantiated
- `ModelDiscovery` — NOT instantiated

**Total: 12 components defined but never wired at runtime.**

---

### FASE C: Pipeline Walkthrough — 8 Scenarios

For ALL 8 scenarios, the actual runtime path is identical:

```
sidecar/main.py (FastAPI)
  → Router handler
  → Orchestrator.process() [LEGACY]
  → intent_engine.parse() (IntentEngine v1, NOT v2)
  → planner.create()
  → decision_engine.evaluate()
  → model_router.chat() (provider-based selection, TaskType from INTENT_TO_TASK)
  → _call_provider() (OpenAI-compatible API call)
  → response returned
```

**None of the 8 scenarios ever touch:**
- IntelligenceOrchestrator
- CapabilityEngine
- IntentEngineV2
- ModelCoordinator
- FusionEngine
- ResourceIntelligence
- PerformanceIntelligence
- FeedbackEngine
- ModelRanking
- TimePredictor
- ConversationManager (for continuity)
- ModelDiscovery

**Evidence:**
- `Orchestrator.process()` (orchestrator.py:303) calls `_process_impl()` (line 379)
- `_process_impl()` calls `_run_pipeline()` (line 632)
- `_run_pipeline()` calls `model_router.process_safely()` or similar
- The `model_router` is `ModelRouter.chat()` which does provider-based routing
- No step in this pipeline consults `IntelligenceOrchestrator`

**Scenario-specific differences:**

| Scenario | Would Use | Actually Uses |
|---|---|---|
| "Hola" | IntentCategory.CHAT → direct reply | Legacy pipeline → provider chat |
| "Explícame Python" | IntentCategory.REASONING → reasoning model | Legacy pipeline → provider chat |
| "Abre Spotify" | IntentCategory.ACTION → tool execution | Legacy pipeline → tool via ToolGateway |
| "Analiza mi proyecto" | IntentCategory.CODING → coding model | Legacy pipeline → provider chat |
| "Crea un archivo Python" | IntentCategory.CODING → coding model | Legacy pipeline → tool via ToolGateway |
| "Busca documentación" | IntentCategory.SEARCH → search tool | Legacy pipeline → tool via ToolGateway |
| "No tengo internet" | Offline mode → local model | Legacy pipeline → offline check in ModelRouter |
| "Continúa donde nos quedamos" | Conversation continuity | Legacy pipeline → no continuity (no ConversationManager used) |

---

### Severity Ratings

| Finding | Severity | File | Impact |
|---|---|---|---|
| Two parallel orchestrators, one unused | CRÍTICA | orchestrator.py, intelligence_orchestrator.py | Full intelligence pipeline is dead code |
| 9 of 19 Phase 9-10 components never wired | CRÍTICA | sidecar/main.py | Phases 9-10 produce zero runtime value |
| No end-to-end integration test | CRÍTICA | tests/ | Impossible to verify pipeline correctness |
| ConversationManager not used at runtime | ALTA | model_router.py:1591-1633 | No conversation continuity in production |
| ModelCoordinator not used | MEDIA | model_coordinator.py | Multi-model capability is theoretical |
| FusionEngine not used | MEDIA | fusion_engine.py | Multi-model fusion is theoretical |
| ResourceIntelligence not wired | MEDIA | resource_intelligence.py | Hardware constraints not considered |
