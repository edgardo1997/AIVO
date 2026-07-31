# Security Certification

## Required Chain
```
Request -> Intent -> DecisionEngine -> RiskClassifier
  -> PolicyEngine -> ConsentService -> ToolExecutionGuard
  -> ToolGateway -> Executor -> Audit
```

## Adversarial Audit Results

### Bypass 1: ToolExecutionGuard NOT in Orchestrator (CRITICAL)
**Evidence:** `sentinel/core/orchestrator.py` contains NO reference to `ToolExecutionGuard`.
**Impact:** Orchestrator calls `self._tool_gateway.execute()` directly at line 1309, skipping:
- ArgumentValidator (path traversal, command injection checks)
- ToolRateLimiter (per-tool rate limiting)
- Explicit RiskClassifier at guard level
- Explicit ConsentService at guard level

**Mitigation:** ToolGateway has its own security (7 layers). But the guard layer is intentionally absent.

### Bypass 2: GroundingEngine calls ToolGateway directly
**File:** `sentinel/core/grounding.py:284`
```python
tool_result = await self._tool_gateway.execute(requirement.tool_id, tool_params, ...)
```
**Impact:** Grounding verification tools bypass all outer security.

### Bypass 3: SkillEngine calls ToolGateway directly
**File:** `sentinel/core/skill_engine.py:115`
```python
tr = await self._tool_gateway.execute(step.tool_id, step.params, step_context)
```
**Impact:** Skill-based execution bypasses security guard.

### Bypass 4: Rollback calls ToolGateway directly
**File:** `sentinel/core/orchestrator.py:1593`
```python
return await self._tool_gateway.execute(tool_id, params, context)
```
**Impact:** Rollback operations skip security.

### Bypass 5: 14 API endpoints without visible authentication
**Evidence:** Scanned `sidecar/routers/` — 14 of 34 endpoints lack `request_identity()` or auth tokens in the handler block.
**Files examined:** `v1/audit.py`, `v1/agents.py`, `v1/triggers.py`, `v1/profile.py`, `auth_jwt.py`, `events.py`, `system_live.py`, `consent.py`

### Bypass 6: /v1/confirm calls gateway directly
**File:** `sidecar/routers/v1/execute.py:42-43`
```python
gateway = request.app.state.tool_gateway
result = await gateway.confirm(confirmation_id, **body.dict())
```
**Impact:** User confirmation path calls gateway directly, bypassing Orchestrator entirely.

## Security Layer Comparison

| Security Layer | ToolExecutionGuard | Orchestrator Path | ToolGateway | /v1/confirm |
|----------------|-------------------|-------------------|-------------|-------------|
| Argument Validation | YES | NO | Partial | NO |
| Rate Limiting | YES | YES (global) | NO | NO |
| Risk Classification | YES | YES | NO | NO |
| Policy Evaluation | YES | YES | YES | NO |
| Consent | YES | YES | NO | Direct call |
| Identity | YES | YES | YES | YES |
| Audit | YES | YES | YES | NO |
| Grounding | NO | YES | YES | NO |
| Circuit Breaker | NO | NO | YES | NO |
| Quality Gate | NO | NO | YES | NO |

## Verdict: **FAIL** (4/10)

ToolGateway provides strong internal security (7 layers), but:
- ToolExecutionGuard is NOT used in the production Orchestrator path
- 4 additional direct ToolGateway calls bypass all outer security
- 14 API endpoints lack visible authentication
- /v1/confirm endpoint directly calls gateway bypassing Orchestrator
