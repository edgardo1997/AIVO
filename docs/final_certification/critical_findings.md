# Critical Findings — Sentinel 1.0 Certification

## FINDING 1: SentinelRuntime is Dead Code in Production

**Severity:** CRITICAL
**Area:** Architecture
**Evidence:**
- `sidecar/modules/__init__.py` creates `Orchestrator()`, NOT `SentinelRuntime()`
- `SentinelRuntime` is only instantiated in `tests/e2e/fixtures/sentinel_test_environment.py`
- 21 components accepted by `SentinelRuntime` are disconnected from production
- **Files:** `sentinel/core/runtime.py:233`, `sidecar/modules/__init__.py:989`

## FINDING 2: ToolExecutionGuard NOT in Production Path

**Severity:** CRITICAL
**Area:** Security
**Evidence:**
- `Orchestrator` (production entry point) contains NO reference to `ToolExecutionGuard`
- `grep "ToolExecutionGuard" sentinel/core/orchestrator.py` returns empty
- Production path calls `self._tool_gateway.execute()` directly at line 1309
- **Impact:** Argument validation, per-tool rate limiting, and guard-level consent are skipped

## FINDING 3: 5 Direct ToolGateway Calls Bypass All Outer Security

**Severity:** CRITICAL
**Area:** Security
**Evidence:**
1. `grounding.py:284` — GroundingEngine calls gateway directly
2. `orchestrator.py:1309` — Main execution (production path)
3. `orchestrator.py:1593` — Rollback operations
4. `runtime.py:454` — SentinelRuntime (dead code, but still exists)
5. `skill_engine.py:115` — Skill-based execution

## FINDING 4: All 3000+ Tests Use Stubs — ZERO Real Integration Tests

**Severity:** CRITICAL
**Area:** Testing
**Evidence:**
- E2E tests test `SentinelRuntime` (dead code path), not `Orchestrator` (production path)
- No test in the entire codebase calls a real model API
- `ModelDiscovery` tests use `httpretty` to mock HTTP responses
- Tool tests use `StubToolGateway`, `StubPolicyEngine`, etc.

## FINDING 5: Intelligence Data Lost on Restart

**Severity:** HIGH
**Area:** Persistence
**Evidence:**
- `PerformanceIntelligence` stores metrics in `List[ExecutionMetrics]` — no DB persistence
- `ModelRanking` stores scores in `Dict[str, ModelScore]` — no DB persistence
- `FeedbackEngine` stores feedback in `List[UserFeedback]` — no DB persistence
- Storage repositories exist (`metric_repository.py`, `feedback_repository.py`, `ranking_repository.py`) but are NOT wired

## FINDING 6: 14 API Endpoints Without Visible Authentication

**Severity:** HIGH
**Area:** Security
**Evidence:**
- Scanned `sidecar/routers/` — 14 of 34 endpoints lack `request_identity()` or auth token checks
- Files: `v1/audit.py`, `v1/agents.py`, `v1/triggers.py`, `v1/profile.py`, `events.py`, `system_live.py`

## FINDING 7: Intelligence Not Wired into Production Orchestrator

**Severity:** HIGH
**Area:** Intelligence
**Evidence:**
- `Orchestrator` does NOT accept or use: `PerformanceIntelligence`, `ModelRanking`, `FeedbackEngine`, `TimePredictor`, `ModelDiscovery`, `IntelligenceEngine`, `ObservabilityEngine`
- Orchestrator uses older classes: `ModelFeedbackStore`, `PerformanceTracker`, `CostTracker`
- Two parallel intelligence codebases exist (`sentinel/core/` vs `sentinel/intelligence/`)

## FINDING 8: Multi-Model Intelligence Not Connected

**Severity:** MEDIUM
**Area:** Intelligence
**Evidence:**
- `MultiModelCoordinator` exists in `sentinel/intelligence/multi_model_coordinator.py`
- `ModelRouter.enable_multi_model()` exists
- But neither is called from the production `Orchestrator`
- **Impact:** All production requests use single-model routing, not multi-model intelligence

## FINDING 9: /v1/confirm Bypasses Orchestrator Entirely

**Severity:** HIGH
**Area:** Security
**Evidence:**
- `sidecar/routers/v1/execute.py:42` — directly calls `gateway.confirm()`
- Skips Orchestrator, DecisionEngine, AuditService, Memory
- **Impact:** User confirmation of actions bypasses audit logging

## FINDING 10: Performance Intelligence Not Tracked in Production

**Severity:** MEDIUM
**Area:** Intelligence
**Evidence:**
- Orchestrator tracks metrics using `PerformanceTracker` (older class), NOT `PerformanceIntelligence`
- `PerformanceIntelligence` (with full summary, ranking integration) is only used in SentinelRuntime (dead code)
- Production cannot learn from tool execution metrics
