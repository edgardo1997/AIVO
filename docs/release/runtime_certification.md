# Runtime Architecture Certification — Sentinel 1.0 RC

## Execution Flow (Actual)

```
                               ┌─────────────────────────────┐
                               │  Orchestrator.process()     │ ← PRODUCTION ENTRY POINT
                               │  sentinel/core/orchestrator │
                               │  line 306                   │
                               └─────────────┬───────────────┘
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    │                      process()                  │
                    │  1. RateLimit                                   │
                    │  2. ContextEngine                               │
                    │  3. IntentEngine + Planner                      │
                    │  4. ModelRouter                                 │
                    │  5. SimulationEngine                            │
                    │  6. RiskClassifier                              │
                    │  7. DecisionEngine                              │
                    │  8. ConsentService                              │
                    │  9. GroundingEngine                             │
                    │ 10. ToolGateway.execute()                       │
                    │ 11. RollbackManager                             │
                    │ 12. Audit + Memory                              │
                    └─────────────────────────────────────────────────┘

         ⚠ SENTINELRUNTIME.PROCESS() IS NOT USED IN PRODUCTION ⚠
```

## Components

### Registered in Orchestrator (production)
| Component | File | Connected | Status |
|-----------|------|-----------|--------|
| RateLimiter | `sentinel/core/rate_limiter.py` | ✅ | Active |
| ContextEngine | `sentinel/core/context.py` | ✅ | Active |
| IntentEngine | `sentinel/core/intent.py` | ✅ | Active |
| Planner | `sentinel/core/planner.py` | ✅ | Active |
| ModelRouter | `sentinel/core/model_router.py` | ✅ | Active |
| SimulationEngine | `sentinel/core/simulation.py` | ✅ | Active |
| RiskClassifier | `sentinel/core/risk_classifier.py` | ✅ | Active |
| DecisionEngine | `sentinel/core/decision_engine.py` | ✅ | Active |
| ConsentService | `sentinel/core/consent_manager.py` | ✅ | Active |
| GroundingEngine | `sentinel/core/grounding.py` | ✅ | Active |
| ToolGateway | `sentinel/core/tool_gateway.py` | ✅ | Active (single gate) |
| AuditService | `sentinel/core/audit_service.py` | ✅ | Active |
| Memory | `sentinel/core/memory.py` | ✅ | Active |
| PerformanceIntelligence | `sentinel/core/performance_intelligence.py` | ❌ | Not wired in Orchestrator |
| FeedbackEngine | `sentinel/core/feedback_engine.py` | ❌ | Not wired in Orchestrator |
| ModelRanking | `sentinel/core/model_ranking.py` | ❌ | Not wired in Orchestrator |
| TimePredictor | `sentinel/core/time_predictor.py` | ❌ | Not wired in Orchestrator |
| ModelDiscovery | `sentinel/core/model_discovery.py` | ❌ | Not wired anywhere |
| IntelligenceEngine | `sentinel/intelligence/engine.py` | ❌ | Not wired in Orchestrator |
| ObservabilityEngine | `sentinel/observability/engine.py` | ❌ | Not wired in Orchestrator |

### Dead Components (exist but no production path uses them)
| Component | File | Notes |
|-----------|------|-------|
| `SentinelRuntime` | `sentinel/core/runtime.py` | Only used in e2e tests |
| `IntelligenceOrchestrator` | `sentinel/core/intelligence_orchestrator.py` | Not wired in Orchestrator |
| `SentinelRuntime._runtime_process()` | `orchestrator.py:355` | Only reachable if runtime= injected |

### Alternative Entry Points
| Method | File:Line | Risk |
|--------|-----------|------|
| `Orchestrator.process_multi_agent()` | `orchestrator.py:1862` | Bypasses Planner, DecisionEngine, Simulation |
| `Orchestrator.execute_direct()` | `orchestrator.py:1076` | Skips intent parsing |
| `Orchestrator.process_offline()` | `orchestrator.py:2005` | Queues, defers execution |
| `MultiModelCoordinator.process()` | `intelligence/multi_model_coordinator.py:80` | Model execution only, no tools |

## Critical Dependencies
- **ToolGateway** — every execution path converges here (mandatory gate)
- **DecisionEngine** — risk-based allow/deny for every plan
- **AuditService** — all actions logged

## Issues Found
1. **❌ CRITICAL: `SentinelRuntime` is dead code** — the documented "single entry point" (`runtime.py:233`) is never called in production. The actual entry point is `Orchestrator.process()`.
2. **❌ CRITICAL: Multiple parallel pipelines** — `process_multi_agent()` and `execute_direct()` bypass parts of the standard pipeline.
3. **⚠️ PerformanceIntelligence, FeedbackEngine, ModelRanking, ModelDiscovery** — exist in the codebase but totally disconnected from production Orchestrator.
4. **⚠️ Two parallel intelligence codebases** — `sentinel/core/` and `sentinel/intelligence/` have duplicate components with different APIs.
5. **✅ FIXED: `self._db` bug** — `runtime.py:281` referenced undefined `self._db`.
6. **✅ FIXED: Security bypass in `ToolExecutor`** — insecure fallback to direct gateway now rejects execution instead.

## Verdict
**NOT READY** — the orchestration layer is fragmented. A single `Orchestrator.process()` exists as the production entry point but has parallel alternative pipelines that bypass security/intent checks. `SentinelRuntime` should be either deleted or made the actual single entry point.
