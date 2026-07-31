## Sentinel 1.0 — Intelligence Audit

### FASE D: Decision-Making Analysis

#### Who decides the model?

**Two parallel decision-makers with no coordination:**

| Decision-Maker | When Used | Decision Basis |
|---|---|---|
| `ModelRouter.select()` | Production (via Orchestrator.process()) | Provider priority, task type, availability, offline mode, cost, feedback |
| `IntelligenceOrchestrator.orchestrate()` | Tests only | Capability matching, resource constraints, performance scores, ranking |

#### How does each decide?

**`ModelRouter.select()`** (model_router.py:762-824):
1. Calls `_try_select_from_registry()` — matches by ModelRegistry capabilities
2. Falls back to provider list, filters by:
   - Task type compatibility (via `_task_capability_map`)
   - Provider availability
   - Circuit breaker state
   - Offline mode constraints
3. Sorts by strategy: local_first, cost, priority, preferred_provider
4. Returns `RouterDecision` with provider_id, model, trace, error

**`IntelligenceOrchestrator.orchestrate()`** (intelligence_orchestrator.py:82-127):
1. Resolves capabilities via `CapabilityEngine` or intent's `to_capability_set()`
2. Selects execution strategy from `INTENT_STRATEGY_MAP`
3. Calls `_select_model()` which:
   - Uses `ModelRegistry.find_candidates()` for capability matching
   - Filters through `ResourceIntelligenceLayer.evaluate()`
   - Scores each candidate via `_score_model()`
   - Returns best-scoring model

#### What information is used?

| Information | ModelRouter.select() | IntelligenceOrchestrator.orchestrate() |
|---|---|---|
| Task type | YES | YES (via IntentCategory) |
| Provider priority | YES | NO |
| Availability | YES | NO |
| Circuit breaker | YES | NO |
| Offline mode | YES | NO |
| Cost | YES (via _smart_select) | YES (score modifier) |
| Historical feedback | YES (via _smart_select) | YES (via ModelRanking) |
| Capabilities | YES (via _try_select_from_registry) | YES (primary basis) |
| Resource constraints | NO | YES (via ResourceIntelligenceLayer) |
| Performance scores | NO | YES (via ModelRanking) |
| Speed | NO | YES (model.speed field) |
| Local/remote preference | YES | YES |

#### What happens when two models meet the same capabilities?

**In `IntelligenceOrchestrator._select_model()`** (intelligence_orchestrator.py:174-225):
- Both are scored via `_score_model()`
- Tie-breaker: lowest cost wins
- With ranking active: performance score adds bonus

**In `ModelRouter.select()`** (model_router.py:762-824):
- Models are sorted by routing strategy (priority, cost, etc.)
- First in sorted order wins

#### What happens when none meets the requirements?

**IntelligenceOrchestrator:** Returns `IntelligenceDecision(status="no_capable_model")` with zero model_id.

**ModelRouter:** Falls back to another provider via `_build_fallback_chain()` — iterates through fallback chain until one works or all fail.

**Severity: MEDIA** — The fallback behavior differs between the two paths. In the unused intelligence path, the system gracefully reports failure. In the production path, `ModelRouter.chat()` raises `RuntimeError("All providers exhausted")` after trying all fallbacks.

#### Scoring Systems

**`_score_model()`** (intelligence_orchestrator.py:150-189):
```
score = 0
  +50 per matching capability
  +30 if tool_calling capability matches and model supports it
  +10 if local
  +10 if cost == 0
  +5 if cost <= 1
  +5 if speed == "fast"
  -10 if speed == "slow"
  + resource_decision.score_modifier
  + int(model_score.performance_score / 10) if ranking available
  -20 if reliability_score < 50
  -30 if success_rate < 0.5
  -10 if success_rate < 0.7
```

**`_smart_select()`** (model_router.py:877-979) — A completely different scoring system:
```python
score = 0
  + priority_weight (configurable per provider)
  + preferred_provider_bonus
  +/ - task_type_alignment
  - system_load_penalty (high cpu/memory reduces score)
  + battery_mode_bonus (prefers local on battery)
  + permission_level_adjustment (restricted → local bonus)
  + feedback_success_rate * FEEDBACK_WEIGHT
  - feedback_avg_duration * DURATION_PENALTY
  - estimated_cost * COST_PENALTY
```

**Finding: Two completely independent scoring systems exist with zero shared logic.**
A model may score highest in `_score_model()` but lowest in `_smart_select()`.

#### Explainability

**IntelligenceOrchestrator** produces `_build_reasoning()` (intelligence_orchestrator.py:241-306):
```
"Intent: CODING | Model: qwen-coder (provider=ollama) | Capabilities: ['coding', 'reasoning'] | Strategy: coding | Performance: 85/100 (high) | Success rate: 100% | Avg latency: 2.3s | Cost: free | Estimated time: 2.5 minutes (confidence: 92%)"
```

**ModelRouter** produces `RouterDecision` with `trace` (model_router.py:193-214):
```python
trace = {
    "selected": provider_id,
    "strategy": strategy,
    "model": model_name,
    "candidates_considered": [...],
    "rejections": [...],
}
```

**Finding:** The `IntelligenceOrchestrator` reasoning is human-readable but only available in tests.
The `ModelRouter` trace is structured but not exposed in API responses.

#### Auditability

**IntelligenceOrchestrator:** Has `_audit_log` (list of decisions) and `ModelRanking` has its own audit log.

**ModelRouter:** Has `routing_history` (max 500 entries) and circuit breaker state.

**Finding:** Both audit logs are in-memory only and lost on restart.

### FASE E: Conversation Continuity

**Actual state:** No conversation continuity exists in production.

- `ConversationManager` is defined (471 lines) but never instantiated in `sidecar/main.py`
- `ModelRouter.chat_with_conversation()` (model_router.py:1591-1633) wraps the conversation flow
  but is never called by any production code path
- The legacy `Orchestrator` maintains its own `context_engine` (from `sentinel/core/context.py`)
  for session history, but this is separate from `ConversationManager`

#### Key Issues:

1. **No conversation persistence** — Active contexts stored in `_active_contexts: Dict[str, ConversationContext]`
   (conversation_manager.py:398). A restart loses all conversations.

2. **No conversation continuity** — When `ModelRouter.chat()` is called without `ConversationManager`,
   each call is stateless. The model receives only the current user message with no history.

3. **Two independent context systems:**
   - `ConversationManager` (new, unused in production)
   - `ContextEngine` (legacy, used in `Orchestrator._process_impl()`)

4. **Personality system is theoretical** — `PersonalityLayer` exists but is not wired to the runtime.

5. **Model switching not possible** — `ConversationManager.switch_model_context()` exists but
   cannot be invoked because `ConversationManager` is not instantiated.

**Severity: CRÍTICA** — In production, every ModelRouter.chat() call is stateless.
The user saying "Continúa donde nos quedamos" will get a blank response with no context.

### FASE F: Multi-Modelo

**Actual state:** No multi-model coordination exists in production.

- `ModelCoordinator` (423 lines) — Never instantiated in `sidecar/main.py`
- `FusionEngine` (242 lines) — Never instantiated in `sidecar/main.py`

#### What they would do (if wired):

**ModelCoordinator** (model_coordinator.py):
- Creates `ModelTask` objects with dependencies
- `execute_plan()` runs tasks sequentially (with optional `depends_on`)
- Tasks are executed one at a time via `model_router.chat()`
- Results are collected into `MultiModelResult`

**FusionEngine** (fusion_engine.py):
- Takes multiple model results
- Compares for conflicts
- Produces `FusionResult` with merged findings
- No weighted voting, no confidence scoring in merge logic

#### Issues:

1. **No parallel execution** — ModelCoordinator's `execute_multi()` (model_coordinator.py:~285)
   uses `for task in tasks:` — sequential execution only, despite having a `parallel` field on tasks.

2. **No partial failure handling** — If one task fails, the entire plan fails. No retry per task.

3. **Fusion is identity** — `FusionEngine.fuse()` (fusion_engine.py:~120) concatenates results.
   No actual conflict resolution or consensus mechanism exists.

4. **Dependency resolution is linear** — `depends_on` is just a list of task IDs checked in order.
   No DAG-based scheduling.

**Severity: ALTA** — Multi-model capability is architecturally present but non-functional.

---

### Intelligence Audit Summary

| Finding | Severity | Evidence |
|---|---|---|
| Two independent scoring systems | ALTA | intelligence_orchestrator.py:150 vs model_router.py:877 |
| Intelligence pipeline never wired at runtime | CRÍTICA | sidecar/main.py:375-530 — no IntelligenceOrchestrator instantiation |
| No conversation continuity in production | CRÍTICA | conversation_manager.py never instantiated |
| Multi-model coordination is theoretical | ALTA | ModelCoordinator not instantiated, FusionEngine concatenates only |
| Audit logs are in-memory only | MEDIA | model_router.py routing_history max 500, lost on restart |
| Decisions not exposed in API responses | BAJA | RouterDecision trace not included in chat responses |
