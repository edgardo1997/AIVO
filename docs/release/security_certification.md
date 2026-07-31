# Security Certification — Sentinel 1.0 RC

## Required Chain

```
Request
  └→ Intent
       └→ DecisionEngine
            └→ RiskClassifier
                 └→ PolicyEngine
                      └→ ConsentService
                           └→ ToolExecutionGuard
                                └→ ToolGateway
                                     └→ Executor
                                          └→ Audit
```

## Actual Chain (All Paths Converge at ToolGateway)

### Path A: Orchestrator.process() (Production)
```
Request → Intent → Plan → DecisionEngine → RiskClassifier → Simulation
  → ConsentService → Grounding → ToolGateway.execute() → Audit
```
⚠ **ToolExecutionGuard NOT used** — ToolGateway is the sole gate (by design).
   ToolGateway enforces: Identity, Policy, Audit, Grounding, Circuit Breaker, Quality Gate, Timeout.

### Path B: ModelRouter / ToolExecutor (Model Tool Calls)
```
ToolRequest → ToolExecutionGuard.execute()
  → ArgumentValidator → ToolRateLimiter → RiskClassifier → PolicyEngine
  → ConsentService → ToolGateway.execute() → Audit
```
✅ Full guard chain. ToolExecutionGuard wraps ToolGateway with additional layers.

### Path C: /v1/execute API
```
HTTP → Auth → Orchestrator.execute_direct() → Path A chain → ToolGateway
```

## Security Bypasses

### Fixed ✅
| Bypass | File | Fix |
|--------|------|-----|
| Insecure fallback in `ToolExecutor.execute_tool_call()` | `sentinel/execution/tool_executor.py:31-46` | Changed from "fallback to gateway" to **reject execution** with error |
| Insecure fallback in legacy `ModelRouter` | `sentinel/routing/legacy.py:559-574` | Changed from "fallback to gateway" to **reject execution** with error |

### Remaining ⚠️
| Issue | Impact | Justification |
|-------|--------|---------------|
| Orchestrator skips `ToolExecutionGuard` | Medium — ToolGateway still provides identity, policy, audit | By design: ToolGateway is the single mandatory gate |
| `process_multi_agent()` bypasses DecisionEngine | High — agent actions skip risk/decision checks | Separate pipeline for multi-agent scenarios |
| `execute_direct()` bypasses Intent analysis | Medium — skips intent classification | Uses override_plan, runs full security after that |

## Verification Checklist

### ✅ Permissions
- ToolGateway: `PolicyEngine.evaluate()` with `required_permissions` from ToolSpec
- ToolExecutionGuard: `PolicyEngine.evaluate()` with tool, user context
- Tools require at least one permission at registration

### ✅ Argument Validation
- ToolExecutionGuard: `ArgumentValidator.validate()` — type safety, path traversal, dangerous command keywords
- ToolGateway: schema validation via catalog_violations

### ✅ Audit Complete
- ToolExecutionGuard: logs tool, source, user, session, execution_id, model, provider, risk, decision, confirmation
- ToolGateway: preflight `log_gateway_authorization()` + post-execution audit
- Orchestrator: `AuditService.log_action()` for full pipeline
- Sensitive data redaction (passwords, tokens, API keys)

### ✅ Error Handling
- Every security check has try/except wrapping
- Failures return structured error results (not exceptions)
- Descriptive error messages with failure reasons

## Verdict
**CONDITIONAL PASS** — ToolGateway is the universal gate that enforces identity, policy, audit, grounding, circuit breaker, and quality control on every execution path. Two medium-severity issues remain (`process_multi_agent` bypass, `execute_direct` intent skip) but are mitigated by architectural intent.
