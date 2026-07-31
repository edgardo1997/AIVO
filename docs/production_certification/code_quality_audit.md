## Sentinel 1.0 — Code Quality Audit

### FASE K: Static Analysis

---

#### Finding K1: `Orchestrator` is a God Class (2035 lines)

**Severity: CRÍTICA**
**File:** `sentinel/core/orchestrator.py`
**Violation:** Single Responsibility Principle (SOLID — S)

**Analysis:**
`Orchestrator` handles:
- Intent parsing
- Plan creation and caching
- Simulation
- Risk classification
- Decision evaluation
- Policy enforcement
- Consent service wiring
- Model routing delegation
- Tool execution with retry/fallback
- Rate limiting (3 tiers)
- Audit recording
- Memory storage
- Multi-agent delegation
- Offline queue management
- Network monitoring
- Event bus subscriptions
- Alert management

**Evidence:** The `__init__` has ~30 optional parameters (orchestrator.py:141-246).

---

#### Finding K2: `ModelRouter` is a God Class (1664 lines)

**Severity: CRÍTICA**
**File:** `sentinel/core/model_router.py`
**Violation:** Single Responsibility Principle (SOLID — S)

**Analysis:**
`ModelRouter` handles:
- Provider configuration (13 providers)
- Provider selection (4 strategies)
- Fallback chains (3 strategies)
- Circuit breaker
- Health checking
- Tool calling (validation, execution, round management)
- Streaming responses
- Conversation management
- Cost tracking
- Feedback integration
- API key management
- Routing history

**Evidence:** The file has 1664 lines and 30+ methods. Multiple concerns are mixed:
`chat()`, `chat_stream()`, `chat_with_tools()`, `chat_with_decision()`,
`chat_with_conversation()`, `chat_with_provider()`, `select()`, `select_all()`,
`select_by_capability()`, `_smart_select()`, `_handle_tool_calls()`,
`_execute_tool_call()`, `_validate_tool_call_compatibility()`.

---

#### Finding K3: Two Intent Engines

**Severity: ALTA**
**Files:** `sentinel/core/intent.py` and `sentinel/core/intent_engine_v2.py`
**Violation:** DRY (Don't Repeat Yourself)

**Analysis:**
There are two intent engines:
- `IntentEngine` (intent.py) — used by legacy `Orchestrator`
- `IntentEngineV2` (intent_engine_v2.py, 645 lines) — used by `IntelligenceOrchestrator`

Both parse user input and return classified intent. They have overlapping but
incompatible type systems (`Intent` vs `ClassifiedIntent`, `IntentCategory`
vs legacy categories).

**Impact:** Duplicate maintenance burden. Behavior differs between v1 and v2,
so the same input can produce different intent classifications depending on
which engine processes it.

---

#### Finding K4: Two Task Type Systems

**Severity: ALTA**
**Files:** `sentinel/core/model_router.py` (`TaskType` enum), `sentinel/core/intent_engine_v2.py` (`IntentCategory` enum)
**Violation:** DRY

**Analysis:**
- `ModelRouter.TaskType`: REASONING, ANALYSIS, QUICK, CODE, CREATIVE, LOCAL (6 values)
- `IntentCategory`: CHAT, ACTION, SYSTEM_OPERATION, AUTOMATION, CODING, SEARCH, DOCUMENT, MEMORY, REASONING, UNKNOWN (10 values)
- `Orchestrator.INTENT_TO_TASK`: Maps 5 legacy intents to `TaskType`

These enum systems are different but semantically overlapping. There's no
canonical mapping.

---

#### Finding K5: Dead Code — `Orchestrator.execute_direct()`

**Severity: BAJA**
**File:** `sentinel/core/orchestrator.py`, lines 1048-1073
**Evidence:** The method exists but `_process_impl()` does not call it for normal
pipeline execution. It's only reachable through external caller.

---

#### Finding K6: Dead Code — `ModelCoordinator`, `FusionEngine`, `ConversationManager`

**Severity: ALTA**
**Files:**
- `sentinel/core/model_coordinator.py` (423 lines)
- `sentinel/core/fusion_engine.py` (242 lines)
- `sentinel/core/conversation_manager.py` (471 lines)

**Evidence:** None of these are instantiated in `sidecar/main.py`. They are
importable through `core/__init__.py` but never wired into the runtime.

---

#### Finding K7: Dead Code — All Phase 9 and Phase 10 Components

**Severity: CRÍTICA**
**Files:**
- `sentinel/core/model_discovery.py` (476 lines)
- `sentinel/core/performance_intelligence.py` (206 lines)
- `sentinel/core/feedback_engine.py` (172 lines)
- `sentinel/core/model_ranking.py` (263 lines)
- `sentinel/core/time_predictor.py` (161 lines)

**Evidence:** None instantiated in `sidecar/main.py`. Total: **1,278 lines of dead code.**

---

#### Finding K8: `_validate_tool_call_compatibility()` Redundancy

**Severity: BAJA**
**File:** `sentinel/core/model_router.py`, lines 523-545
**Violation:** DRY

**Analysis:**
`chat_with_tools()` (line 585) calls `_validate_tool_call_compatibility()` which
checks `ModelRegistry` for `tool_calling` capability. But `select()` (line 762)
already filters by capability in `_try_select_from_registry()`. The same check
happens twice.

---

#### Finding K9: Orchestrator Dependency Injection Anti-Pattern

**Severity: MEDIA**
**File:** `sentinel/core/orchestrator.py`, lines 141-246
**Violation:** Interface Segregation Principle (SOLID — I)

**Analysis:**
The `Orchestrator.__init__` takes ~30 optional parameters. Most are `None`-checked
at usage time. The constructor has become an untyped dependency injection container:

```python
def __init__(
    self,
    intent_engine=None,
    tool_gateway=None,
    planner=None,
    decision_engine=None,
    model_router=None,
    context_engine=None,
    memory=None,
    audit_service=None,
    profile_manager=None,
    # ... 20+ more
):
```

This makes it impossible to determine which dependencies are truly required
without reading the entire implementation.

---

#### Finding K10: Threading Model Inconsistency

**Severity: MEDIA**
**File:** Multiple files
**Violation:** Consistent concurrency model

**Analysis:**
- `ModelRegistry` uses `threading.Lock`
- `CostTracker` uses `threading.local()` + locks
- `ModelFeedbackStore` uses `threading.local()`
- `Orchestrator` is not thread-safe
- `EventBus` is async
- `ModelRouter` is not thread-safe for state mutations
- `ToolGateway` is not thread-safe

There's no consistent threading model. Mixing synchronous and async code
(`_execute_tool_call` creating new event loops) compounds the problem.

---

#### Finding K11: No Type Hints Everywhere

**Severity: BAJA**
**File:** Various
**Evidence:** `Orchestrator.__init__` uses `Optional[Any]` for many parameters.
Type safety is lost when everything is `Any`.

---

#### Finding K12: Magic Numbers

**Severity: BAJA**
**File:** `sentinel/core/intelligence_orchestrator.py`, `_score_model()` at lines 150-189

**Analysis:**
The scoring function uses hardcoded weights:
- +50 per capability
- +30 for tool calling
- +10 for local
- -10 for slow
- +10 for free
- etc.

These weights are not configurable, documented, or justified.

---

### Code Quality Summary

| Finding | Severity | Lines Impacted |
|---|---|---|
| K1: Orchestrator god class (2035 lines) | CRÍTICA | 2035 |
| K2: ModelRouter god class (1664 lines) | CRÍTICA | 1664 |
| K3: Two intent engines | ALTA | IntentEngine + IntentEngineV2 |
| K4: Two task type systems | ALTA | TaskType vs IntentCategory |
| K5: Dead code in Orchestrator | BAJA | ~25 lines |
| K6: Dead components (ModelCoordinator, FusionEngine, ConversationManager) | ALTA | ~1136 lines |
| K7: Dead code (all Phase 9-10) | CRÍTICA | ~1278 lines |
| K8: Redundant tool compatibility check | BAJA | ~20 lines |
| K9: DI anti-pattern (30 params) | MEDIA | orchestrator.py:141-246 |
| K10: Threading model inconsistency | MEDIA | Multiple files |
| K11: Insufficient type hints | BAJA | Various |
| K12: Magic numbers in scoring | BAJA | intelligence_orchestrator.py:150 |
