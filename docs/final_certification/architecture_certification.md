# Architecture Certification

## Single Entry Point Requirement

**Requirement:** All requests must pass through `SentinelRuntime.process(request)`

**Evidence:**

| Check | Result | Evidence |
|-------|--------|----------|
| SentinelRuntime instantiated in production? | **FAIL** | Not found in `sidecar/modules/__init__.py` |
| Production entry point | `Orchestrator.process()` | `sentinel/core/orchestrator.py:306` |
| Alternative pipelines | **3 found** | `process_multi_agent()` (line 1862), `execute_direct()` (line 1076), `process_offline()` (line 2005) |
| Total process/execute methods | **408** | Every tool class has its own `execute()` |
| Direct ToolGateway bypasses | **6** | See security report |

## Pipeline Comparison

### Documented Path (SentinelRuntime)
```
RateLimit -> Context -> Intent -> Intelligence -> Plan
  -> Risk -> Simulation -> Decision -> Consent
  -> Model Select -> EXECUTION (via ToolGateway)
  -> Performance Metrics -> Memory -> Audit
```

### Actual Production Path (Orchestrator)
```
RateLimit -> Context -> Intent + Plan -> Model Select
  -> Simulation -> Risk -> Decision -> Consent
  -> Grounding -> EXECUTION (via ToolGateway DIRECTLY)
  -> Rollback -> Audit + Memory
```

**Key differences:**
- No `IntelligenceEngine` recommendation step
- Execution goes through ToolGateway WITHOUT ToolExecutionGuard
- No `PerformanceIntelligence` metrics recording
- No `TimePredictor` estimation
- No `ObservabilityEngine` tracing

## Component Connectivity

| Component | In SentinelRuntime? | In Orchestrator? | In Production? |
|-----------|---------------------|------------------|----------------|
| IntentEngine | YES | YES | YES |
| Planner | YES | YES | YES |
| DecisionEngine | YES | YES | YES |
| RiskClassifier | YES | YES | YES |
| PolicyEngine | YES | YES | YES |
| ConsentService | YES | YES | YES |
| ToolGateway | YES | YES | YES |
| AuditService | YES | YES | YES |
| Memory | YES | YES | YES |
| **ToolExecutionGuard** | **NO** | **NO** | **NO** |
| PerformanceIntelligence | YES | **NO** | **NO** |
| ModelRanking | YES | **NO** | **NO** |
| FeedbackEngine | YES | **NO** | **NO** |
| TimePredictor | YES | **NO** | **NO** |
| IntelligenceEngine | YES | **NO** | **NO** |
| ModelDiscovery | **NO** | **NO** | **NO** |
| ObservabilityEngine | YES | **NO** | **NO** |

## Verdict: **FAIL** (1/10)

The documented single entry point (`SentinelRuntime.process()`) is dead code. The production entry point (`Orchestrator.process()`) lacks half the intelligence components. Alternative parallel pipelines (`process_multi_agent`, `execute_direct`) bypass security layers.
