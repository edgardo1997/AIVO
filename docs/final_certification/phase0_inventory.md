# FASE 0 — Complete Project Inventory

## 1. Directory Tree (Active + Dead)

### Active Production Packages
```
sentinel/
  core/           — 98 .py files — THE ENGINE (Orchestrator + all components)
  security/       — 5 files — ToolExecutionGuard, ArgumentValidator, RateLimiter
  routing/        — 5 files — ProviderSelector, FallbackManager, CapabilitySelector
  execution/      — 2 files — ToolExecutor
  providers/      — 3 files — ProviderManager, OpenAIProvider
  intelligence/   — 16 files — MultiModelCoordinator, Ranking, Feedback, Discovery
  observability/  — 12 files — Health, Metrics, Tracing, Logging, Recovery, Alerts
  storage/        — 7 files — 5 repositories + DB + migrations
  monitoring/     — Health checker
  conversation/   — Conversation handler
  tools/          — 40 files — ALL registered tool implementations
  models/         — Model metadata types

sidecar/
  main.py         — FastAPI app, startup, route registration
  modules/        — Orchestrator wiring + 15 route modules
  routers/        — v1 API (execute, audit, policies, agents, triggers, profile)
  services/       — Rate limiter
  tests/          — 3000+ tests

tests/
  e2e/            — 29 E2E tests (test SentinelRuntime, NOT Orchestrator)
  security/       — Security tests
```

### Dead/Dormant Packages (only __pycache__/ remains)
```
sentinel/
  activation_gateway/          adapters/              advisory/
  application_discovery_v2/    authority_safety_layer/ authorization_canary/
  authorization_manager/       automation/            canary_environment/
  canary_observation/          consent_manager/       contracts/
  contract_adapters/           controlled_runtime_activation/
  cutover_validation/          decision_long_term_evaluation/
  decision_shadow_validation/  evidence_integrity/    execution_boundary/
  execution_planner/           executor_sandbox/      final_control_plane_readiness/
  learning/                    limited_execution_v2/  local_model/
  operational_telemetry_hub/   persistent_control_boundary/
  policy_engine/               policy_v2_shadow/      promotion_validation/
  recommendation_engine/       release/               resilience/
  runtime_canary/              runtime_equivalence_validation/
  runtime_isolation/           runtime_replay_validation/
  runtime_trial/               runtime_v2_controlled/ sandbox_engine/
  shadow/                      shadow_decision_orchestrator/
  shadow_runtime_real/         simulation_engine/     stability_validation/
  tool_gateway/                v2_authority_migration/ v2_authority_readiness/
  v2_operational_evidence_storage/ v2_operational_observability/
  v2_trust_evaluation/         v2_unified_pipeline/
```
**42 dead directories** — phase artifacts from FASE 31-39 experiments. Only `__pycache__/` remains in each.

---

## 2. Component Map

### Tier 1 — Production Core (wired in Orchestrator)
| Component | File | State | Notes |
|-----------|------|-------|-------|
| Orchestrator | `core/orchestrator.py` | **PRODUCTION** | Main entry point (32 params, 40+ attrs) |
| IntentEngine | `core/intent.py` | PRODUCTION | Parses user intent |
| Planner | `core/planner.py` | PRODUCTION | Creates execution plans |
| DecisionEngine | `core/decision_engine.py` | PRODUCTION | Evaluates allow/deny/confirm |
| RiskClassifier | `core/risk_classifier.py` | PRODUCTION | Classifies risk |
| ToolGateway | `core/tool_gateway.py` | **PRODUCTION** | Universal execution gate (7 security layers) |
| ContextEngine | `core/context.py` | PRODUCTION | Collects system context |
| Memory | `core/memory.py` | PRODUCTION | SQLite-backed memory |
| AuditService | `core/audit_service.py` | PRODUCTION | SQLite-backed audit |
| ModelRouter | `core/model_router.py` | PRODUCTION | Model selection + routing |
| SkillEngine | `core/skill_engine.py` | PRODUCTION | Skill-based execution |
| GroundingEngine | `core/grounding.py` | PRODUCTION | Pre-execution validation |
| HardeningService | `core/hardening.py` | PRODUCTION | Error classification, retry |
| CostTracker | `core/cost_tracker.py` | **PRODUCTION (OLD)** | Uses old CostTracker |
| ModelFeedbackStore | `core/model_feedback.py` | **PRODUCTION (OLD)** | Uses old class |
| PerformanceTracker | `core/performance_tracker.py` | **PRODUCTION (OLD)** | Uses old PerformanceTracker |

### Tier 2 — Modern Equivalents (NOT wired in Orchestrator)
| Component | File | State | Should Replace |
|-----------|------|-------|----------------|
| PerformanceIntelligence | `core/performance_intelligence.py` | **PARALLEL** | PerformanceTracker |
| ModelRanking | `core/model_ranking.py` | **PARALLEL** | (new capability) |
| FeedbackEngine | `core/feedback_engine.py` | **PARALLEL** | ModelFeedbackStore |
| TimePredictor | `core/time_predictor.py` | **PARALLEL** | (new capability) |
| ModelDiscovery | `core/model_discovery.py` | **PARALLEL** | (new capability) |
| IntelligenceEngine | `intelligence/engine.py` | **PARALLEL** | (new capability) |
| ObservabilityEngine | `observability/engine.py` | **PARALLEL** | ObservabilityService |

### Tier 3 — Intelligence Package (sentinel/intelligence/)
| Component | File | State | Notes |
|-----------|------|-------|-------|
| MultiModelCoordinator | `intelligence/multi_model_coordinator.py` | **PARALLEL** | Not wired |
| TaskPlanner | `intelligence/task_planner.py` | PARALLEL | Not wired |
| ConfidenceScorer | `intelligence/confidence_scorer.py` | PARALLEL | Not wired |
| EvaluationEngine | `intelligence/evaluation_engine.py` | PARALLEL | Not wired |
| ConflictResolver | `intelligence/conflict_resolver.py` | PARALLEL | Not wired |
| ConsensusEngine | `intelligence/consensus_engine.py` | PARALLEL | Not wired |
| PartialFailureHandler | `intelligence/partial_failure_handler.py` | PARALLEL | Not wired |
| RankingEngine | `intelligence/ranking.py` | **DUPLICATE** | Duplicates core/ModelRanking |
| FeedbackCycle | `intelligence/feedback.py` | **DUPLICATE** | Duplicates core/FeedbackEngine |
| TaskTimePredictor | `intelligence/time_predictor.py` | **DUPLICATE** | Duplicates core/TimePredictor |
| ModelDiscovery | `intelligence/model_discovery.py` | **DUPLICATE** | Duplicates core/ModelDiscovery |

### Tier 4 — Security
| Component | File | State | Notes |
|-----------|------|-------|-------|
| ToolExecutionGuard | `security/tool_guard.py` | **UNUSED** | NOT in Orchestrator |
| ArgumentValidator | `security/argument_validator.py` | UNUSED | Only used in ToolExecutionGuard |
| ToolRateLimiter | `security/tool_rate_limiter.py` | UNUSED | Only used in ToolExecutionGuard |

### Tier 5 — SentinelRuntime (DEAD CODE)
| Component | File | State | Notes |
|-----------|------|-------|-------|
| SentinelRuntime | `core/runtime.py` | **DEAD** | Only used in E2E tests |
| SentinelRequest | `core/runtime.py` | DEAD | Only for SentinelRuntime |
| SentinelResponse | `core/runtime.py` | DEAD | Only for SentinelRuntime |

---

## 3. Execution Flow (Production)

```
Client
  │
  ▼
sidecar/main.py — FastAPI
  │
  ├─ POST /api/sentinel/chat/stream
  │   └─ sentinel_bridge.py: sentinel_chat_stream()
  │       ├─ orch.classify_intent(message)
  │       └─ gateway.execute("process.execute", {...})
  │           └─ ToolGateway.execute()
  │               └─ ProcessTool.execute()
  │                   └─ Orchestrator.process()  ← REAL ENTRY POINT
  │                       └─ _process_impl()
  │                           ├─ RateLimit
  │                           ├─ Context → Deep Context → Profile → Memory
  │                           ├─ Intent + Plan (or override_plan for execute_direct)
  │                           ├─ ModelRouter.select()
  │                           └─ _run_pipeline()
  │                               ├─ Simulation
  │                               ├─ RiskClassifier
  │                               ├─ DecisionEngine
  │                               ├─ ConsentService
  │                               ├─ GroundingEngine (direct gateway call)
  │                               ├─ _execute_single_step()  (direct gateway call)
  │                               │   ├─ RetryHandler
  │                               │   ├─ FallbackHandler
  │                               │   ├─ ModelFeedbackStore (OLD)
  │                               │   ├─ CostTracker (OLD)
  │                               │   └─ PerformanceTracker (OLD)
  │                               ├─ RollbackManager (direct gateway call)
  │                               ├─ Memory + Audit
  │                               └─ Advisory + Presentation
  │
  ├─ POST /v1/execute
  │   └─ orch.execute_direct() → Orchestrator.process() (with override_plan)
  │
  └─ POST /v1/confirm
      └─ gateway.confirm() — DIRECT bypass (no Orchestrator)
```

---

## 4. Dependency Map

```
Orchestrator.process()
  ├── IntentEngine (required)
  ├── ToolGateway (required — DIRECT, no ToolExecutionGuard)
  ├── Planner
  ├── DecisionEngine
  ├── RiskClassifier
  ├── ModelRouter
  ├── ContextEngine
  ├── MemoryBackend
  ├── AuditService
  ├── SimulationEngine
  ├── ConsentService
  ├── GroundingEngine
  ├── SkillEngine
  ├── ModelFeedbackStore (OLD)
  ├── CostTracker (OLD)
  ├── PerformanceTracker (OLD)
  ├── HardeningService
  ├── AlertManager
  ├── AdvisoryService
  ├── PresentationLayer
  ├── EventBus
  ├── RateLimiter
  ├── RetryHandler
  ├── FallbackHandler
  └── RollbackManager

NOT CONNECTED:
  ├── PerformanceIntelligence (modern)
  ├── ModelRanking (modern)
  ├── FeedbackEngine (modern)
  ├── TimePredictor
  ├── ModelDiscovery
  ├── IntelligenceEngine
  ├── ObservabilityEngine
  ├── ToolExecutionGuard
  ├── MultiModelCoordinator
  └── Storage Repositories (metric, feedback, ranking)
```

---

## 5. Files to Eliminate (Candidates)

### Dead Phase Artifacts (42 directories)
All 42 directories listed in section 1 with only `__pycache__/`. These are phase artifacts from FASE 31-39 experiments. Candidates for deletion after verifying no imports reference them.

### Dead Code Files
| File | Reason | Risk |
|------|--------|------|
| `sentinel/core/runtime.py` | SentinelRuntime unused in production | LOW — only test fixtures import it |
| `sentinel/routing/legacy.py` | 1700-line backup of old ModelRouter | LOW — only referenced by tests |
| `sentinel/core/observability.py` | Old ObservabilityService | LOW — replaced by observability/ package |
| `sentinel/core/observability_center.py` | Not wired anywhere | LOW |
| `sentinel/core/intelligence_orchestrator.py` | Not wired anywhere | LOW |
| `sentinel/core/quality_gate.py` | Not imported | LOW |

### Duplicate Files (one should be deleted)
| Group | Keep | Delete |
|-------|------|--------|
| Ranking | `core/ModelRanking` | `intelligence/RankingEngine` |
| Feedback | `core/FeedbackEngine` | `intelligence/FeedbackCycle` |
| Time Prediction | `core/TimePredictor` | `intelligence/TaskTimePredictor` |
| Model Discovery | `core/ModelDiscovery` | `intelligence/ModelDiscovery` |

---

## Architecture Decision

**Decision: Orchestrator is the official core. SentinelRuntime will be eliminated after migration.**

Rationale:
- Orchestrator is already the production entry point with 32 components
- SentinelRuntime contains modern components but is dead code
- Migrating modern components INTO Orchestrator is cleaner than migrating Orchestrator's 32 components INTO SentinelRuntime
- SentinelRuntime will become a thin compatibility wrapper during migration, then be deleted

**Next: FASE 1 — Define Official Architecture**
