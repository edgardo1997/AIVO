## Sentinel 1.0 — Technical Debt Register

All identified technical debt items with estimated effort to remediate.

---

### Debt Items

| ID | Description | File(s) | Estimated Effort | Priority |
|---|---|---|---|---|
| TD-01 | Two orchestrators must be merged or one removed | orchestrator.py, intelligence_orchestrator.py | 2-3 weeks | CRITICAL |
| TD-02 | ModelRouter god class must be split (1664 lines → 4-5 classes) | model_router.py | 2-3 weeks | CRITICAL |
| TD-03 | Integrate Phase 9-10 components into runtime wiring | sidecar/main.py + all phase 9-10 files | 1-2 weeks | HIGH |
| TD-04 | Add persistent storage for ModelRegistry, PerformanceIntelligence, ModelRanking, FeedbackEngine | model_registry.py + perf files | 1-2 weeks | HIGH |
| TD-05 | Merge or eliminate duplicate intent engines | intent.py, intent_engine_v2.py | 1 week | HIGH |
| TD-06 | Add integration tests for full pipeline | test infrastructure | 2-3 weeks | HIGH |
| TD-07 | Security: add PolicyEngine gate to ModelRouter tool execution | model_router.py | 3-5 days | CRITICAL |
| TD-08 | Security: replace asyncio.new_event_loop() with async-compatible design | model_router.py | 2-3 days | HIGH |
| TD-09 | Security: add input validation for tool arguments | model_router.py | 2-3 days | HIGH |
| TD-10 | Security: add audit trail for ModelRouter tool execution | model_router.py | 1-2 days | HIGH |
| TD-11 | Security: encrypt API keys at rest | model_router.py | 2-3 days | MEDIUM |
| TD-12 | Add observability: metrics, tracing, health checks | sidecar/main.py + new files | 2-3 weeks | HIGH |
| TD-13 | Add e2e tests for 8 fundamental scenarios | tests/ | 1 week | HIGH |
| TD-14 | Add security penetration tests | tests/ | 1-2 weeks | CRITICAL |
| TD-15 | Add performance/load tests | tests/ | 1 week | HIGH |
| TD-16 | Remove/refactor FusionEngine (false promise of fusion) | fusion_engine.py | 2-3 days | MEDIUM |
| TD-17 | Fix rich-get-richer bias in ModelRanking scoring | model_ranking.py | 1 day | MEDIUM |
| TD-18 | Add periodic refresh to ModelDiscovery | model_discovery.py | 2-3 days | MEDIUM |
| TD-19 | Wire EventBus into runtime and add event emission from production paths | sidecar/main.py + model_router.py | 3-5 days | MEDIUM |
| TD-20 | Add conversation persistence to ConversationManager | conversation_manager.py | 1 week | HIGH |
| TD-21 | Standardize TaskType/IntentCategory mapping | model_router.py + intent_engine_v2.py | 3-5 days | MEDIUM |
| TD-22 | Add fallback chain to IntelligenceOrchestrator | intelligence_orchestrator.py | 2-3 days | MEDIUM |
| TD-23 | Remove hardcoded magic numbers from scoring | intelligence_orchestrator.py | 1 day | LOW |
| TD-24 | Reduce constructor parameter count in Orchestrator | orchestrator.py | 1-2 weeks | MEDIUM |
| TD-25 | Add type hints to all functions | Multiple files | 3-5 days | LOW |
| TD-26 | Add tool-level rate limiting to ToolGateway | tool_gateway.py | 2-3 days | MEDIUM |
| TD-27 | Implement proper parallel execution in ModelCoordinator | model_coordinator.py | 1 week | MEDIUM |

---

### Effort Summary

| Priority | Items | Estimated Total |
|---|---|---|
| CRITICAL (must fix before RC) | 5 | 8-12 weeks |
| HIGH (should fix before RC) | 10 | 10-18 weeks |
| MEDIUM (fix post-RC) | 8 | 5-7 weeks |
| LOW (fix post-1.0) | 2 | ~1 week |
| **TOTAL** | **25 items** | **24-38 weeks** |

---

### Debt-to-Code Ratio

| Metric | Value |
|---|---|
| Total code lines (all files audited) | ~12,000 |
| Dead code lines (unused in production) | ~2,500 (21%) |
| God class lines (Orchestrator + ModelRouter) | 3,699 (31%) |
| Test lines | ~2,000 |
| Test-to-code ratio | 1:6 |

**Assessment:** Technical debt is **CRITICAL**. 21% of the codebase is dead code
in production. 31% is concentrated in two god classes. The test-to-code ratio
of 1:6 is reasonable, but tests target the wrong components.
