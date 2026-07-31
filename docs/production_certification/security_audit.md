## Sentinel 1.0 — Security Audit

### FASE G: Security Bypass Analysis

#### Methodology

Each identified bypass is analyzed by attempting to demonstrate how a model or component
could circumvent security controls. Evidence is cited from code.

---

#### Finding G1: Tool Execution Bypasses PolicyEngine

**Severity: CRÍTICA**
**File:** `sentinel/core/model_router.py`, `_handle_tool_calls()` at lines 537-583
**Risk: ALTA**

**Analysis:**
When `ModelRouter.chat_with_tools()` executes tool calls, it invokes `_handle_tool_calls()`:

```python
def _handle_tool_calls(self, tool_calls, messages, timeout_limit=None):
    for tc in tool_calls:
        result = self._execute_tool_call(tc)
        messages.append({"role": "tool", ...})
```

And `_execute_tool_call()` (model_router.py:530-535):

```python
def _execute_tool_call(self, tc):
    tool_name = tc.function.name
    args = json.loads(tc.function.arguments)
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(self._tool_gateway.execute(tool_name, **args))
    finally:
        loop.close()
```

**Problem:** Tool execution bypasses `PolicyEngine`, `ConsentService`, and `DecisionEngine`.
The legacy `Orchestrator` has these checks in `_execute_single_step()` (orchestrator.py:1199-1400)
with conservative mode, risk classification, and user consent. But when tools are invoked
directly from `ModelRouter.chat_with_tools()`, none of these apply.

**Attack scenario:**
1. User sends a message crafted to trigger a dangerous tool call
2. ModelRouter passes it to the LLM provider
3. LLM responds with a tool call (e.g., `execute_command`, `delete_file`)
4. `_handle_tool_calls()` directly calls `ToolGateway.execute()`
5. **No policy check, no consent, no risk classification**
6. The tool executes without user approval

---

#### Finding G2: asyncio.run() Creates Event Loop Deadlock Risk

**Severity: ALTA**
**File:** `sentinel/core/model_router.py`, `_execute_tool_call()` at line 532
**Risk: MEDIA (in specific async contexts)**

```python
def _execute_tool_call(self, tc):
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(self._tool_gateway.execute(tool_name, **args))
    finally:
        loop.close()
```

**Problem:**
- `ToolGateway.execute()` is async but `_execute_tool_call()` is synchronous
- It creates a new event loop per tool call — expensive and dangerous
- If called from a thread that already has a running event loop (e.g., from an async
  endpoint handler), creating a new event loop may fail or create a deadlock
- Python 3.12+ deprecates `asyncio.new_event_loop()` on the main thread in some contexts

---

#### Finding G3: No Authorization on Tool Execution

**Severity: ALTA**
**File:** `sentinel/core/tool_gateway.py`
**Risk: ALTA**

**Analysis:**
`ToolGateway` registers tools and executes them by name. There is no built-in
authorization mechanism. Any code that can call `ToolGateway.execute()` can invoke
any registered tool.

**Evidence:** `ToolGateway` (tool_gateway.py) has:
- `register(tool)` — no permission check
- `execute(tool_name, **kwargs)` — no user/session context
- `list_tools()` — no filtering by user role

The gateway trusts the caller to have authorization. In the legacy `Orchestrator` path,
`_execute_single_step()` provides some protection via policy checks. But the `ModelRouter`
tool execution path bypasses these.

---

#### Finding G4: Circuit Breaker Can Mask Attacks

**Severity: MEDIA**
**File:** `sentinel/core/model_router.py`, circuit breaker at lines 1019-1029
**Risk: BAJA**

**Analysis:**
The circuit breaker tracks failures per provider. If an attacker causes repeated
provider failures, the circuit breaker opens and stops routing to that provider.
This is a valid resilience pattern, but there's no security distinction between
"provider is down" and "provider is being attacked."

---

#### Finding G5: No Input Validation on Tool Arguments

**Severity: MEDIA**
**File:** `sentinel/core/model_router.py`, `_execute_tool_call()` at lines 530-535
**Risk: MEDIA**

```python
def _execute_tool_call(self, tc):
    tool_name = tc.function.name
    args = json.loads(tc.function.arguments)
    result = loop.run_until_complete(self._tool_gateway.execute(tool_name, **args))
```

**Problem:**
- `args` is directly deserialized from the LLM response and passed to the tool
- No validation that the arguments match the tool's expected schema
- If a tool has a `command` parameter, the LLM could inject arbitrary commands
- No sanitization of string arguments

---

#### Finding G6: API Key Storage Security Unknown

**Severity: MEDIA**
**File:** `sentinel/core/model_router.py`, `set_api_key()` at ~line 350
**Risk: MEDIA (depends on deployment)**

```python
def set_api_key(self, provider_id: str, key: str) -> None:
    self._api_keys[provider_id] = key
```

**Problem:**
- API keys are stored in plaintext in `_api_keys: Dict[str, str]`
- No encryption at rest
- No key rotation mechanism
- Keys are passed directly to OpenAI client constructors

---

#### Finding G7: No Authentication on Tool Registration

**Severity: ALTA**
**File:** `sentinel/core/tool_gateway.py`, `register()` at ~line 75
**Risk: ALTA (if attacker gains code execution)**

```python
def register(self, tool: Tool) -> None:
    self._tools[tool.name] = tool
```

Any code that can access the `ToolGateway` instance can register arbitrary tools.
Since `ToolGateway` is a global singleton in `sentinel/core/tool_gateway.py`:

```python
_SHARED_GATEWAY: Optional[ToolGateway] = None
def get_shared_gateway() -> ToolGateway: ...
```

If any plugin or module registers a malicious tool, it becomes available to the entire system.

---

#### Finding G8: No Audit Trail for Tool Execution (ModelRouter Path)

**Severity: ALTA**
**File:** `sentinel/core/model_router.py`, `_execute_tool_call()` at lines 530-535
**Risk: ALTA**

**Analysis:**
When tools are executed via the `ModelRouter` path (`_handle_tool_calls()`), there is no
audit record created. The legacy `Orchestrator` path records every execution via
`audit_service.record()`, but `ModelRouter._handle_tool_calls()` does not.

**Evidence:** `_execute_tool_call()` returns the result and appends it to messages,
but never calls any audit, logging, or recording function (besides debug logging).

---

#### Finding G9: Rate Limiting is Per-Endpoint, Not Per-User-Action

**Severity: BAJA**
**File:** `sidecar/main.py`, rate limiter at lines 265-301
**Risk: BAJA**

**Analysis:**
```python
RATE_LIMITS = {
    "/chat": (30, 60),  # 30 requests per 60 seconds
    "/execute": (20, 60),
}
```

Rate limiting is applied per URL path, not per user session or model invocation.
A user could make 30 chat requests in 60 seconds, each triggering 5 tool calls,
resulting in 150 tool executions. Tool-level rate limiting is implemented in
`Orchestrator._execute_single_step()` but not in `ModelRouter._handle_tool_calls()`.

---

### Security Audit Summary

| ID | Finding | Severity | Impact |
|---|---|---|---|
| G1 | Tool execution bypasses PolicyEngine via ModelRouter | CRÍTICA | Dangerous tools executed without approval |
| G2 | asyncio.new_event_loop() deadlock risk | ALTA | Production crashes under async load |
| G3 | No authorization on ToolGateway | ALTA | Any code can execute any tool |
| G4 | Circuit breaker no security distinction | MEDIA | Monitoring blind spot |
| G5 | No input validation on tool arguments | MEDIA | LLM-injected argument attacks |
| G6 | API keys in plaintext | MEDIA | Key exposure on host compromise |
| G7 | No auth on tool registration | ALTA | Malicious tool injection |
| G8 | No audit trail for ModelRouter tool execution | ALTA | Untracked tool usage |
| G9 | Rate limiting bypassable per tool call | BAJA | Resource exhaustion |
