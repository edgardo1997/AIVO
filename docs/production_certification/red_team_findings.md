## Sentinel 1.0 — Red Team Findings

### Objective: Break Sentinel Intellectually

This document identifies edge cases, inconsistencies, race conditions,
conflicts between components, and unexpected behaviors.

---

#### RT1: The Intelligence Pipeline is a Simulation

**Severity: CRÍTICA**
**Type:** Architectural Bypass

**Scenario:** A developer wires `IntelligenceOrchestrator` into a new endpoint,
not realizing `Orchestrator.process()` is the production entry point. The new
endpoint makes decisions that are incompatible with the legacy pipeline.

**Root Cause:** Two orchestrators with no documented relationship.
`IntelligenceOrchestrator` selects models based on capabilities + performance.
`Orchestrator` selects models based on provider priority + fallback chain.
The same request could result in two different model selections.

**Impact:** Decision inconsistency. Half the system uses capability-based
routing, half uses provider-based routing. There is no single source of truth.

---

#### RT2: ModelRouter Has Three Model Selection Paths

**Severity: ALTA**
**Type:** Decision Ambiguity

`ModelRouter` has three distinct model selection mechanisms that can return
different results:

1. **`_try_select_from_registry()`** (model_router.py:725-760) — Capability-based using ModelRegistry
2. **`select()`** (model_router.py:762-824) — Provider-based with strategy sorting
3. **`select_by_capability()`** (model_router.py:495-521) — ModelRegistry capabilities only

**Scenario:**
- User request arrives at `ModelRouter.chat()`
- `chat()` calls `select()` which MAY call `_try_select_from_registry()` first
- If registry selection returns a candidate, it's used
- If registry selection fails (no matching capabilities), falls back to provider-based selection
- A model that is NOT in the registry but IS configured as a provider may be selected

**Conflict:** A request for "coding" may select a provider-based model (e.g., from priority list)
even when a capability-matched model exists in the registry but is rated lower by priority.

---

#### RT3: Rate Limiting Has a Blind Spot for Tool Calls

**Severity: ALTA**
**Type:** Resource Exhaustion

**Scenario:** User sends 30 chat requests in 60 seconds (rate limit maximum).
Each request triggers 5 tool calls (e.g., web search, file operations).
Result: 30 × 5 = 150 tool calls in 60 seconds.

**Why this works:**
- Rate limit is per API request URL, not per tool call
- `ModelRouter._handle_tool_calls()` has no rate limiting
- `Orchestrator._execute_single_step()` has tool-level rate limiting
  but `ModelRouter` tool execution path bypasses the Orchestrator
- `ToolGateway.execute()` has no rate limiting

---

#### RT4: Feedback Loop Contradiction

**Severity: MEDIA**
**Type:** Learning Inconsistency

**Scenario:**
1. Model A has 100 successful executions, 0 failures → performance_score = 95
2. Model B is newly discovered, 1 execution, success → performance_score = 60
3. The system routes to Model A because of higher score
4. Model B never gets enough traffic to improve its score
5. Model A's score continues to increase, reinforcing its dominance

**Root Cause:** The scoring formula (model_ranking.py:63-91) includes
`execution_score = min(100, total_executions / 10 * 100)` which gives
a popularity bonus. New models can never catch up.

```
performance_score = (
    reliability * 0.35 +
    latency_score * 0.20 +
    cost_score * 0.15 +
    feedback_ratio * 100 * 0.20 +
    execution_score * 0.10     # ← This is a popularity contest
)
```

This creates a **rich-get-richer** dynamic where established models dominate
regardless of actual quality.

---

#### RT5: ConversationManager + ModelRouter Context Conflict

**Severity: MEDIA**
**Type:** State Conflict

**Scenario:**
1. Request comes in via `Orchestrator.process()`
2. `Orchestrator` collects context via `context_engine` (its own context system)
3. `Orchestrator` calls `ModelRouter.chat()` with messages
4. If `ConversationManager` were also wired, both would maintain separate
   conversation state for the same conversation_id

**Root Cause:** Two independent context systems:
- `ConversationManager` with `_active_contexts: Dict[str, ConversationContext]`
- `Orchestrator` with `context_engine: ContextEngine` (from `sentinel/core/context.py`)

If both are active, they would diverge — the ConversationManager might trim
history while the ContextEngine retains it, or vice versa.

---

#### RT6: ModelRouter Circuit Breaker Doesn't Cover Tool Execution Failures

**Severity: ALTA**
**Type:** Blind Spot

**Scenario:**
1. Provider responds successfully with a tool call
2. ToolGateway.execute() fails (e.g., command not found)
3. The provider's circuit breaker stays closed (successful LLM response)
4. The tool keeps getting called and failing, wasting resources

**Root Cause:** Circuit breaker tracks provider call failures, not downstream
tool execution failures. A provider that consistently suggests bad tool calls
is never penalized.

---

#### RT7: Async/Sync Boundary Violation

**Severity: ALTA**
**Type:** Runtime Error

**Scenario:** A request triggers `_handle_tool_calls()` in an async context
(e.g., from an async endpoint handler). The method calls `_execute_tool_call()`
which creates a NEW event loop via `asyncio.new_event_loop()`.

**Python Behavior:**
- On the main thread, `asyncio.new_event_loop()` creates a new loop
- `loop.run_until_complete()` runs the coroutine synchronously
- If the current thread already has a running loop (e.g., in an async handler),
  some Python versions may raise `RuntimeError: Cannot run the event loop
  while another loop is running`
- `loop.close()` may not properly clean up if an exception occurs

**Evidence:** model_router.py:530-535:
```python
loop = asyncio.new_event_loop()
try:
    result = loop.run_until_complete(self._tool_gateway.execute(...))
finally:
    loop.close()
```

---

#### RT8: Scoring Divergence Between Paths

**Severity: ALTA**
**Type:** Decision Inconsistency

**Scenario:** Two intelligence paths produce different model rankings:

**IntelligenceOrchestrator._score_model():**
- qwen-coder: +50 (coding) +50 (reasoning) +10 (local) +10 (free) +5 (fast) = 125

**ModelRouter._smart_select():**
- qwen-coder: priority=30, local_bonus, no feedback data (new model), no cost
- gpt-4o: priority=22, remote, existing feedback, higher cost
- Result: gpt-4o may score higher due to feedback weight

**Impact:** The same intent classified the same way could result in different
model selections depending on which path processes it.

---

#### RT9: FusionEngine Cannot Actually Fuse

**Severity: MEDIA**
**Type:** False Promise

**Scenario:** `FusionEngine.fuse()` is called with two model results:
- Model A says: "The answer is 42"
- Model B says: "The answer is 7"

**Actual behavior:** `fuse()` concatenates both results with delimiters.
No conflict detection. No weighted voting. No consensus mechanism.

**Evidence:** fusion_engine.py, `fuse()` method iterates results and appends
them to a list. The `FusionResult` contains both findings with no resolution.

---

#### RT10: Missing Model Fallback When Registry Returns No Candidates

**Severity: MEDIA**
**Type:** Brittle Failure

**Scenario:**
1. `IntelligenceOrchestrator._select_model()` calls `find_candidates()`
2. No models match the required capabilities → returns None
3. `orchestrate()` returns `IntelligenceDecision(status="no_capable_model")`
4. **No fallback** — the system has no option to use a different model

**Contrast with ModelRouter:** `ModelRouter.chat()` has fallback chains that
try multiple providers when the primary fails. The IntelligenceOrchestrator
has no fallback mechanism at all.

---

#### RT11: Auto-Discovery Runs on Instantiation, Not on Schedule

**Severity: MEDIA**
**Type:** Stale State

**Evidence:** `ModelDiscovery.discover_all()` is called once when `run_full_discovery()`
is invoked. There's no polling, no webhook, no periodic refresh. If a new model
appears on an Ollama instance after discovery runs, it won't be detected until
discovery is manually triggered again.

---

#### RT12: PerformanceIntelligence Event Handlers Are Never Registered

**Severity: ALTA**
**Type:** Dead Code

**Evidence:** `PerformanceIntelligence.subscribe_to_events()` subscribes to
`MODEL_EXECUTION_STARTED`, `MODEL_EXECUTION_COMPLETED`, `MODEL_EXECUTION_FAILED`.

These events are **never emitted** by any production code. Neither `Orchestrator`
nor `ModelRouter` emits these events. The subscribers exist but there are no publishers.

---

### Red Team Summary

| ID | Finding | Severity |
|---|---|---|
| RT1 | Intelligence pipeline is a simulation (never wired) | CRÍTICA |
| RT2 | ModelRouter has 3 inconsistent selection paths | ALTA |
| RT3 | Rate limiting bypassable via tool calls | ALTA |
| RT4 | Scoring creates rich-get-richer feedback loop | MEDIA |
| RT5 | Two independent context systems would conflict | MEDIA |
| RT6 | Circuit breaker doesn't cover tool failures | ALTA |
| RT7 | Async/sync boundary violation (new_event_loop) | ALTA |
| RT8 | Scoring divergence between paths | ALTA |
| RT9 | FusionEngine cannot actually fuse | MEDIA |
| RT10 | No fallback in IntelligenceOrchestrator | MEDIA |
| RT11 | Auto-discovery runs once, never refreshes | MEDIA |
| RT12 | Event handlers exist, events never emitted | ALTA |
